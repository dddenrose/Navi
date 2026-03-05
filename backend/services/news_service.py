"""News Service — Google News RSS 財經新聞擷取."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

# Session with limited retries for fast failure
_news_session = requests.Session()
_news_session.mount("https://", HTTPAdapter(max_retries=Retry(total=0)))


@dataclass
class NewsArticle:
    """A single news article from Google News RSS."""

    title: str = ""
    link: str = ""
    source: str = ""
    published: str = ""
    published_dt: datetime | None = None


@dataclass
class NewsResult:
    """Collection of news articles for a query."""

    query: str = ""
    articles: list[NewsArticle] = field(default_factory=list)
    error: str = ""


def _clean_html(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_rss(xml_text: str) -> list[NewsArticle]:
    """Parse Google News RSS XML into NewsArticle list."""
    articles: list[NewsArticle] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("RSS XML parse error: %s", e)
        return articles

    # RSS 2.0 structure: rss > channel > item
    channel = root.find("channel")
    if channel is None:
        return articles

    for item in channel.findall("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_date_el = item.find("pubDate")
        source_el = item.find("source")

        title = _clean_html(title_el.text or "") if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        source = (source_el.text or "").strip() if source_el is not None else ""
        pub_str = (pub_date_el.text or "").strip() if pub_date_el is not None else ""

        published_dt = None
        published_display = pub_str
        if pub_str:
            try:
                published_dt = parsedate_to_datetime(pub_str)
                published_display = published_dt.strftime("%Y/%m/%d %H:%M")
            except Exception:
                pass

        articles.append(
            NewsArticle(
                title=title,
                link=link,
                source=source,
                published=published_display,
                published_dt=published_dt,
            )
        )

    return articles


def search_news(query: str, max_results: int = 8, lang: str = "zh-TW") -> NewsResult:
    """Search Google News RSS for articles matching the query.

    Args:
        query: Search query, e.g. "台積電", "NVDA earnings".
        max_results: Maximum number of articles to return.
        lang: Language/region, default "zh-TW" for Traditional Chinese.

    Returns:
        NewsResult with list of articles or error message.
    """
    result = NewsResult(query=query)

    # Build Google News RSS URL
    # Format: https://news.google.com/rss/search?q=台積電&hl=zh-TW&gl=TW&ceid=TW:zh-Hant
    encoded_query = quote(query)
    url = f"{_GOOGLE_NEWS_RSS}?q={encoded_query}&hl={lang}&gl=TW&ceid=TW:zh-Hant"

    try:
        resp = _news_session.get(
            url,
            timeout=(3, 5),
            headers={
                "User-Agent": "Navi/1.0 (Stock Analyzer)",
                "Accept": "application/rss+xml, application/xml, text/xml",
            },
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Google News RSS request failed for '%s': %s", query, e)
        result.error = f"新聞搜尋失敗：{e}"
        return result

    articles = _parse_rss(resp.text)
    result.articles = articles[:max_results]

    if not result.articles:
        result.error = f"未找到與「{query}」相關的新聞。"

    return result
