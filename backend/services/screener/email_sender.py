"""Screener email sender — SendGrid + HTML template render.

Reads `screener_email_subscribers/{user_id}` Firestore collection, renders the
latest report into an HTML email, and sends via SendGrid.

Environment:
    SENDGRID_API_KEY           required for actual send
    EMAIL_FROM_ADDRESS         from header (e.g. notify@navi-stock.app)
    EMAIL_FROM_NAME            display name (default: "Navi 智能選股")
    SCREENER_UNSUBSCRIBE_SECRET HMAC secret for one-click unsubscribe links
    SCREENER_PUBLIC_BASE_URL   public URL prefix for unsubscribe links

If SENDGRID_API_KEY is missing the sender runs in DRY-RUN mode and only logs.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from html import escape
from pathlib import Path

from config import settings
from services.firestore_client import get_db
from services.screener.orchestrator import REPORTS_COLLECTION

logger = logging.getLogger(__name__)

SUBSCRIBERS_COLLECTION = "screener_email_subscribers"
TEMPLATE_PATH = Path(__file__).parent / "email_template.html"


@dataclass
class SendResult:
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    dry_run: bool = False


# ── Unsubscribe HMAC ────────────────────────────────────────────────────────


def _unsubscribe_secret() -> str:
    return getattr(settings, "screener_unsubscribe_secret", "") or "navi-default-unsub"


def make_unsubscribe_token(user_id: str) -> str:
    secret = _unsubscribe_secret().encode("utf-8")
    sig = hmac.new(secret, user_id.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"{user_id}.{sig}"


def verify_unsubscribe_token(token: str) -> str | None:
    """Return user_id if token valid, else None."""
    if not token or "." not in token:
        return None
    user_id, sig = token.rsplit(".", 1)
    expected = make_unsubscribe_token(user_id)
    if hmac.compare_digest(token, expected):
        return user_id
    return None


# ── Subscribers ─────────────────────────────────────────────────────────────


def get_subscriber(user_id: str) -> dict | None:
    db = get_db()
    snap = db.collection(SUBSCRIBERS_COLLECTION).document(user_id).get()
    return snap.to_dict() if snap.exists else None


def upsert_subscriber(user_id: str, payload: dict) -> dict:
    db = get_db()
    ref = db.collection(SUBSCRIBERS_COLLECTION).document(user_id)
    existing = ref.get().to_dict() or {}
    merged = {**existing, **payload, "user_id": user_id}
    ref.set(merged)
    return merged


def disable_subscriber(user_id: str) -> bool:
    db = get_db()
    ref = db.collection(SUBSCRIBERS_COLLECTION).document(user_id)
    if not ref.get().exists:
        return False
    ref.update({"enabled": False})
    return True


def list_active_subscribers(profile: str, frequency: str) -> list[dict]:
    db = get_db()
    out: list[dict] = []
    for snap in db.collection(SUBSCRIBERS_COLLECTION).stream():
        d = snap.to_dict() or {}
        if not d.get("enabled"):
            continue
        if profile not in (d.get("profiles") or ["momentum", "value"]):
            continue
        if frequency not in (d.get("frequencies") or ["weekly"]):
            continue
        if not d.get("email"):
            continue
        out.append(d)
    return out


# ── Render ──────────────────────────────────────────────────────────────────


def _load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _load_report(report_id: str) -> tuple[dict | None, dict[str, list[dict]]]:
    db = get_db()
    doc = db.collection(REPORTS_COLLECTION).document(report_id).get()
    if not doc.exists:
        return None, {}
    report = doc.to_dict() or {}
    picks_by_industry: dict[str, list[dict]] = {}
    for snap in (
        db.collection(REPORTS_COLLECTION).document(report_id).collection("picks").stream()
    ):
        p = snap.to_dict() or {}
        picks_by_industry.setdefault(p.get("industry", "未分類"), []).append(p)
    for group in picks_by_industry.values():
        group.sort(key=lambda x: x.get("rank_in_industry", 999))
    return report, picks_by_industry


def _render_pick_row(pick: dict) -> str:
    name = escape(str(pick.get("name", pick.get("ticker", ""))))
    code = escape(str(pick.get("ticker", "")).replace(".TW", "").replace(".TWO", ""))
    grade = str(pick.get("final_grade", ""))
    interp = pick.get("interpretation") or {}
    narrative = escape(str(interp.get("narrative", "")))[:280]
    warnings = interp.get("warnings") or []
    warnings_text = escape("；".join(warnings[:2])) if warnings else "—"

    valuation = pick.get("valuation") or {}
    upside = float(valuation.get("implied_upside_mid_pct") or 0)
    fv_mid = valuation.get("fair_value_mid")
    price = (pick.get("snapshot") or {}).get("price")

    upside_color = "#10b981" if upside >= 0 else "#ef4444"
    grade_bg = (
        "#10b981" if grade == "Strong Pick"
        else "#0ea5e9" if grade == "Pick"
        else "#f59e0b"
    )

    fv_text = f"${price if price is not None else '—'}"
    if fv_mid:
        fv_text += f" → ${fv_mid}"
    upside_html = (
        f'<div style="color:{upside_color};font-size:12px;font-weight:600;">'
        f'{"+" if upside >= 0 else ""}{upside:.1f}%</div>'
        if fv_mid else ""
    )

    return f"""
    <tr>
      <td style="padding:14px 12px;border-bottom:1px solid #e5e7eb;vertical-align:top;">
        <div style="font-weight:600;color:#111827;font-size:15px;">{name} <span style="color:#6b7280;font-weight:400;font-size:12px;">{code}</span></div>
        <div style="margin-top:6px;color:#374151;font-size:13px;line-height:1.5;">{narrative}…</div>
        <div style="margin-top:6px;color:#9ca3af;font-size:11px;">注意：{warnings_text}</div>
      </td>
      <td style="padding:14px 12px;border-bottom:1px solid #e5e7eb;text-align:right;vertical-align:top;white-space:nowrap;">
        <span style="display:inline-block;padding:2px 8px;border-radius:999px;background:{grade_bg};color:#fff;font-size:11px;font-weight:600;">{escape(grade)}</span>
        <div style="margin-top:8px;color:#111827;font-size:13px;">{fv_text}</div>
        {upside_html}
      </td>
    </tr>
    """


def render_email_html(
    report: dict,
    picks_by_industry: dict[str, list[dict]],
    *,
    user_id: str,
    profile: str,
    public_base_url: str,
) -> str:
    template = _load_template()
    rows_html: list[str] = []
    for industry in sorted(picks_by_industry.keys()):
        picks = picks_by_industry[industry]
        rows_html.append(
            f"""<tr><td colspan="2" style="padding:18px 12px 6px;color:#4f46e5;font-size:13px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">{escape(industry)}</td></tr>"""
        )
        for p in picks:
            rows_html.append(_render_pick_row(p))

    unsub_token = make_unsubscribe_token(user_id)
    unsub_url = f"{public_base_url.rstrip('/')}/api/screener/unsubscribe?token={unsub_token}"
    web_url = f"{public_base_url.rstrip('/')}/screener"

    profile_label = "Momentum Rider 動能" if profile == "momentum" else "Value Hunter 價值"
    return (
        template.replace("{{REPORT_ID}}", escape(report.get("report_id", "")))
        .replace("{{PROFILE_LABEL}}", profile_label)
        .replace("{{FINAL_COUNT}}", str(report.get("final_count", 0)))
        .replace(
            "{{INDUSTRIES_COUNT}}",
            str(len(report.get("industries_covered", []) or picks_by_industry)),
        )
        .replace("{{PICKS_TABLE}}", "\n".join(rows_html))
        .replace("{{UNSUBSCRIBE_URL}}", escape(unsub_url, quote=True))
        .replace("{{WEB_URL}}", escape(web_url, quote=True))
    )


# ── Send ────────────────────────────────────────────────────────────────────


def _public_base_url() -> str:
    return (
        getattr(settings, "screener_public_base_url", "")
        or "https://navi-stock-analyzer.web.app"
    )


def send_report_email(report_id: str, *, profile: str, frequency: str) -> SendResult:
    """Render the report and send to all active subscribers matching profile/frequency.

    DRY-RUN if SENDGRID_API_KEY is missing.
    """
    api_key = getattr(settings, "sendgrid_api_key", "")
    from_addr = getattr(settings, "email_from_address", "") or "notify@navi-stock.app"
    from_name = getattr(settings, "email_from_name", "") or "Navi 智能選股"
    base_url = _public_base_url()

    report, picks_by_industry = _load_report(report_id)
    if not report:
        logger.warning("send_report_email: report %s not found", report_id)
        return SendResult(skipped=0, failed=1)

    subscribers = list_active_subscribers(profile, frequency)
    logger.info(
        "Sending report %s to %d subscribers (profile=%s freq=%s)",
        report_id,
        len(subscribers),
        profile,
        frequency,
    )

    result = SendResult(dry_run=not api_key)
    if not subscribers:
        return result

    sg_client = None
    if api_key:
        try:
            from sendgrid import SendGridAPIClient  # type: ignore

            sg_client = SendGridAPIClient(api_key)
        except Exception as e:
            logger.exception("SendGrid client init failed: %s", e)
            sg_client = None
            result.dry_run = True

    subject = (
        f"[Navi 智能選股] {report.get('report_id')} · "
        f"{'動能' if profile == 'momentum' else '價值'}策略 · "
        f"{report.get('final_count', 0)} 檔精選"
    )

    for sub in subscribers:
        user_id = sub["user_id"]
        to_email = sub["email"]
        try:
            html = render_email_html(
                report,
                picks_by_industry,
                user_id=user_id,
                profile=profile,
                public_base_url=base_url,
            )
            if not sg_client:
                logger.info("[DRY-RUN] would email %s (%s)", to_email, user_id)
                result.skipped += 1
                continue

            from sendgrid.helpers.mail import Mail  # type: ignore

            message = Mail(
                from_email=(from_addr, from_name),
                to_emails=to_email,
                subject=subject,
                html_content=html,
            )
            resp = sg_client.send(message)
            if 200 <= resp.status_code < 300:
                result.sent += 1
            else:
                logger.warning(
                    "SendGrid %s returned %s: %s", to_email, resp.status_code, resp.body
                )
                result.failed += 1
        except Exception as e:
            logger.exception("send to %s failed: %s", to_email, e)
            result.failed += 1
    return result
