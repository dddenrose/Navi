"""Knowledge base ingestion pipeline.

Scans knowledge_base/ for Markdown files, chunks them, generates embeddings,
and stores them in Firestore Vector Search.

Usage:
    cd backend
    uv run python data_pipeline/ingest_knowledge.py
"""

import hashlib
import sys
from pathlib import Path

# Ensure backend/ is on sys.path when running as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings
from services.embedding_service import store_document
from services.firestore_client import get_db

KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"

# Chunk settings optimised for Chinese technical documents
CHUNK_SIZE = 800
CHUNK_OVERLAP = 200

# Map directory names to category labels
CATEGORY_MAP = {
    "technical_analysis": "technical_analysis",
    "fundamental_analysis": "fundamental_analysis",
    "investment_theory": "investment_theory",
    "papers": "papers",
}

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n## ", "\n### ", "\n---", "\n\n", "\n", "。", "，", " "],
)


def _content_hash(text: str) -> str:
    """Return a short SHA-256 hash of text for deduplication."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _detect_category(file_path: Path) -> str:
    """Detect the knowledge category from directory name."""
    for part in file_path.parts:
        if part in CATEGORY_MAP:
            return CATEGORY_MAP[part]
    return "unknown"


def _extract_title(content: str, file_path: Path) -> str:
    """Extract the title from the first H1 heading, or fall back to filename."""
    for line in content.splitlines():
        if line.startswith("# "):
            return line.lstrip("# ").strip()
    return file_path.stem


def _check_existing(source_file: str, chunk_index: int) -> bool:
    """Check if a chunk already exists in Firestore (idempotency)."""
    db = get_db()
    collection = settings.firestore_collection_knowledge
    query = (
        db.collection(collection)
        .where("metadata.source_file", "==", source_file)
        .where("metadata.chunk_index", "==", chunk_index)
        .limit(1)
    )
    return len(query.get()) > 0


def ingest_file(file_path: Path, *, force: bool = False) -> int:
    """Ingest a single Markdown file into Firestore.

    Returns the number of chunks stored.
    """
    content = file_path.read_text(encoding="utf-8")
    category = _detect_category(file_path)
    title = _extract_title(content, file_path)
    source_file = str(file_path.relative_to(KNOWLEDGE_BASE_DIR))

    chunks = text_splitter.split_text(content)
    stored = 0

    for i, chunk in enumerate(chunks):
        if not force and _check_existing(source_file, i):
            print(f"  ⏭️  Skip (exists): {source_file} chunk {i}")
            continue

        metadata = {
            "source_file": source_file,
            "category": category,
            "title": title,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "content_hash": _content_hash(chunk),
        }

        doc_id = store_document(chunk, metadata)
        stored += 1
        print(f"  ✅ Stored: {source_file} chunk {i}/{len(chunks) - 1} → {doc_id}")

    return stored


def ingest_all(*, force: bool = False) -> None:
    """Scan knowledge_base/ and ingest all Markdown files."""
    md_files = sorted(KNOWLEDGE_BASE_DIR.rglob("*.md"))

    if not md_files:
        print("❌ No Markdown files found in knowledge_base/")
        return

    print(f"📚 Found {len(md_files)} knowledge files")
    print(f"   Chunk size: {CHUNK_SIZE}, overlap: {CHUNK_OVERLAP}")
    print(f"   Collection: {settings.firestore_collection_knowledge}")
    print()

    total_files = 0
    total_chunks = 0

    for file_path in md_files:
        rel_path = file_path.relative_to(KNOWLEDGE_BASE_DIR)
        print(f"📄 Processing: {rel_path}")
        stored = ingest_file(file_path, force=force)
        total_files += 1
        total_chunks += stored
        print()

    print("=" * 50)
    print(f"✅ Ingestion complete!")
    print(f"   Files processed: {total_files}")
    print(f"   Chunks stored:   {total_chunks}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    if force:
        print("⚠️  Force mode: re-ingesting all chunks\n")
    ingest_all(force=force)
