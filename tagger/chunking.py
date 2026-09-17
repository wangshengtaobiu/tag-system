"""Book chunking shared by every stage.

The pipeline used to query the index with the book stem plus the first 2000
characters only. Measured on real books, that misses ~40% of the tags that
chunk-level recall surfaces, because anything introduced deeper in the book is
unreachable.

The title is NOT merged into a chunk. It used to be prepended to chunk 0, which
looked harmless but poisoned that chunk's embedding: the title matches hundreds
of tag descriptions, so chunk 0 became the "best" hit for 15% of all candidates
(uniform would be ~3-4%) and up to 119/120 candidates for a book whose title is
descriptive. Since the chunk with the most candidate votes is what the judge is
shown, the judge then read the book's opening -- usually setup -- and rejected
everything. The title is queried separately instead; see stage1_recall.

The chunker must stay deterministic and shared: a candidate reports the index of
the chunk that recalled it, and the judge is later shown the chunk at that index.
If the two sides chunked differently the index would point at the wrong text.
"""

from pathlib import Path


def chunk_text(text: str, chunk_chars: int = 2000) -> list[str]:
    """Split a book into consecutive chunks of plain text."""
    if not text:
        return []
    return [text[i:i + chunk_chars] for i in range(0, len(text), chunk_chars)]


def chunk_book(book_path: str, chunk_chars: int = 2000,
               text: str | None = None) -> list[str]:
    """Chunk a book from disk (or from already-loaded text)."""
    if text is None:
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                text = Path(book_path).read_text(encoding=enc)
                break
            except (UnicodeDecodeError, UnicodeError, FileNotFoundError):
                continue
        else:
            text = ""
    return chunk_text(text, chunk_chars)
