"""Local read-only full-text retrieval over a prepared public document corpus."""

import argparse
import json
from pathlib import Path
import re
import sqlite3

INDEX_VERSION = "local-document-fts5-v1"


def text_pages(path):
    if path.suffix.lower() in {".txt", ".md"}:
        yield 1, path.read_text(encoding="utf-8", errors="replace")
    elif path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        for number, page in enumerate(PdfReader(path).pages, 1):
            yield number, page.extract_text() or ""


def build(corpus, index):
    """FTS is an explicit local adaptation, not a reproduction of dense embeddings."""
    corpus, index = Path(corpus).resolve(strict=True), Path(index)
    if index.exists():
        raise FileExistsError(index)
    if any(corpus.rglob("*.pdf")):
        import pypdf  # Fail before building, rather than mark every PDF as a parse error.
    temporary = index.with_suffix(".building")
    if temporary.exists():
        raise FileExistsError(temporary)
    rows, errors, empty = 0, [], []
    with sqlite3.connect(temporary) as db:
        db.execute("CREATE VIRTUAL TABLE documents USING fts5(path UNINDEXED, page UNINDEXED, text)")
        db.execute("CREATE TABLE metadata (version TEXT)")
        db.execute("INSERT INTO metadata VALUES (?)", (INDEX_VERSION,))
        for path in sorted(corpus.rglob("*")):
            if path.is_symlink():
                raise ValueError("Corpus symlinks are forbidden")
            if not path.is_file() or path.suffix.lower() not in {".pdf", ".txt", ".md"}:
                continue
            name, written = str(path.relative_to(corpus)), 0
            try:
                for page, text in text_pages(path):
                    # Fixed chunks bound returned evidence without losing long pages.
                    for offset in range(0, len(text), 6000):
                        chunk = text[offset:offset + 6000].strip()
                        if chunk:
                            db.execute("INSERT INTO documents VALUES (?, ?, ?)", (name, page, chunk))
                            rows += 1
                            written += 1
            except Exception as error:
                errors.append(dict(path=name, error_type=type(error).__name__))
            if not written:
                empty.append(name)
        db.execute("INSERT INTO documents(documents) VALUES ('optimize')")
    if not rows:
        raise ValueError("No searchable text was extracted from corpus")
    temporary.replace(index)
    return dict(version=INDEX_VERSION, chunks=rows, extraction_errors=errors, empty_documents=empty,
                image_ocr=False, audio_video="published transcripts only; raw media remains available",
                retrieval="SQLite FTS5 lexical; no embeddings or model calls", paid_calls=0)


def search(index, query, limit=8):
    words = re.findall(r"\w+", query, re.UNICODE)
    if not words or len(words) > 32 or not 1 <= limit <= 20:
        raise ValueError("Use 1-32 search terms and 1-20 results")
    expression = " OR ".join('"' + word + '"' for word in words)
    uri = Path(index).resolve(strict=True).as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT version FROM metadata").fetchone() != (INDEX_VERSION,):
            raise ValueError("Unsupported document index")
        rows = db.execute("SELECT path, page, snippet(documents, 2, '', '', ' ... ', 64) "
                          "FROM documents WHERE documents MATCH ? ORDER BY rank LIMIT ?", (expression, limit)).fetchall()
    return [dict(path="/corpus/" + path, page=page, excerpt=text) for path, page, text in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=Path("/corpus-search.sqlite"))
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv)
    print(json.dumps(search(args.index, args.query, args.limit), ensure_ascii=False))


if __name__ == "__main__":
    main()
