"""Navi CLI — Interactive Q&A with the RAG pipeline.

Usage:
    cd backend
    uv run python cli.py
"""

import asyncio
import sys
from pathlib import Path

# Ensure backend/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))


BANNER = """
╔══════════════════════════════════════════════╗
║  🧚 Navi — AI-Powered Stock Analyzer        ║
║  "Hey! Listen!"                              ║
║                                              ║
║  輸入你的投資問題，Navi 會為你分析。           ║
║  輸入 quit 或 exit 離開。                     ║
╚══════════════════════════════════════════════╝
"""


async def _stream_response(question: str, ticker: str | None = None) -> None:
    """Stream RAG response to stdout."""
    from services.rag_service import analyze

    print("\n🧚 Navi：", end="", flush=True)
    async for chunk in analyze(question, ticker=ticker):
        print(chunk, end="", flush=True)
    print("\n")


def _show_stats() -> None:
    """Show knowledge base statistics."""
    try:
        from services.embedding_service import get_collection_stats

        stats = get_collection_stats()
        print(f"📚 知識庫：{stats['total_documents']} 篇文件")
        if stats["categories"]:
            print(f"   分類：{', '.join(stats['categories'])}")
        print()
    except Exception as e:
        print(f"⚠️  無法取得知識庫統計：{e}")
        print("   請確認 GCP credentials 已設定且知識庫已匯入。\n")


def main() -> None:
    print(BANNER)
    _show_stats()

    while True:
        try:
            user_input = input("💬 你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再見！")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("👋 再見！")
            break

        # Parse optional ticker: "分析台積電 $TSM" or "$2330.TW 技術面"
        ticker = None
        words = user_input.split()
        for w in words:
            if w.startswith("$"):
                ticker = w[1:]
                break

        try:
            asyncio.run(_stream_response(user_input, ticker=ticker))
        except Exception as e:
            print(f"\n❌ 發生錯誤：{e}\n")


if __name__ == "__main__":
    main()
