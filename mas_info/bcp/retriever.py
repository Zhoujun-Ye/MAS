"""BrowseComp-Plus retrieval: official BM25 index and official snippet truncation.

Every condition shares one retriever and one index (guide §9).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path


class BM25:
    """Anserini SimpleSearcher, as in the official BM25 searcher.

    Calls are serialized: concurrent Lucene access through the JVM is unstable.
    """

    def __init__(self, index: Path, java_home: Path | None = None):
        if java_home:
            os.environ["JAVA_HOME"] = str(java_home)
        from pyserini.pyclass import autoclass

        self._searcher = autoclass("io.anserini.search.SimpleSearcher")(str(index))
        self._lock = threading.Lock()

    def search(self, query: str, k: int) -> list[dict]:
        with self._lock:
            hits = self._searcher.search(query, k)
            return [
                {
                    "docid": hit.docid,
                    "score": hit.score,
                    "text": json.loads(hit.lucene_document.get("raw"))["contents"],
                }
                for hit in hits
            ]

    def get_document(self, docid: str) -> dict | None:
        with self._lock:
            doc = self._searcher.doc(docid)
            if doc is None:
                return None
            return {"docid": docid, "text": json.loads(doc.get("raw"))["contents"]}


class Truncator:
    """Official snippet cut: the first N tokens of the Qwen/Qwen3-0.6B tokenizer."""

    def __init__(self, max_tokens: int, tokenizer: Path | None):
        self.max_tokens = max_tokens
        self._tokenizer = None
        if tokenizer is not None:
            if not Path(tokenizer).exists():
                raise FileNotFoundError(f"{tokenizer}: run scripts/prepare_bcp.py first")
            from tokenizers import Tokenizer

            self._tokenizer = Tokenizer.from_file(str(tokenizer))

    @property
    def kind(self) -> str:
        return "qwen3-0.6b" if self._tokenizer else "words"

    def __call__(self, text: str) -> str:
        if not self.max_tokens:
            return text
        if self._tokenizer is None:  # offline tests only
            words = text.split()
            return text if len(words) <= self.max_tokens else " ".join(words[: self.max_tokens])
        ids = self._tokenizer.encode(text, add_special_tokens=False).ids
        if len(ids) <= self.max_tokens:
            return text
        return self._tokenizer.decode(ids[: self.max_tokens], skip_special_tokens=True)
