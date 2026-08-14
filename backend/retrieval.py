"""Hybrid retrieval: vector search (Chroma/nomic-embed-text) + keyword search
(BM25) merged with Reciprocal Rank Fusion, then reordered by a LOCAL
cross-encoder.

    query -> nomic embedding -> vector search  \\
                                                >- RRF -> cross-encoder -> top k
             BM25 keyword search               /

Document embeddings are computed ONCE at ingestion and persisted in Chroma
(config.CHROMA_DIR); nothing here re-embeds the corpus per question. The BM25
index is built once per process from the stored chunks and rebuilt only when
the chunk count changes.

Vector-only search misses exact technical tokens (model numbers, engine
names, units) that don't cluster well in embedding space but that BM25's
term-frequency scoring rewards directly - important for the spec-sheet-style
documents this system searches. Fusing both signals by rank (RRF) avoids
having to reconcile Chroma's raw distance scale with BM25's raw score scale.
"""

import logging
import re
import threading
from collections import defaultdict

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from rank_bm25 import BM25Okapi

import config
import nlp_local
from intent_taxonomy import brand_for_filename

logger = logging.getLogger("research")

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# How many extra candidates to pull before marque filtering. Filtering after
# the fact would otherwise starve a scoped search: ask for 25 Bugatti chunks
# and get 4, because the other 21 slots went to the Ferrari financials that
# dominate this corpus by page count.
_SCOPE_OVERFETCH = 5


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def brand_of(metadata: dict | None) -> str | None:
    """Marque a chunk belongs to. Prefers the `brand` stamped at ingestion
    (load_docs.py) and falls back to inferring it from the filename, so an
    index built before that stamp existed still scopes correctly instead of
    needing a re-embed of the whole corpus."""
    meta = metadata or {}
    stamped = meta.get("brand")
    if stamped:
        return stamped
    return brand_for_filename(str(meta.get("source", "")))


def _in_scope(metadata: dict | None, brands: set[str] | None) -> bool:
    if not brands:
        return True
    brand = brand_of(metadata)
    # Unattributed documents stay in scope - excluding a chunk we simply
    # couldn't classify would hide real evidence with no way for the user to
    # tell. Only a document positively identified as another marque is cut.
    return brand is None or brand in brands


class LocalEmbeddings:
    """LangChain embeddings interface over the in-process ONNX encoder.

    Retrieval used to embed queries through Ollama's nomic-embed-text, and that
    coupling had a measured failure mode: Ollama evicts the embedding model to
    make room for an answer model, so the NEXT question's vector search has to
    reload it. Observed live as "Candidate Search: 33.17s" on a question
    immediately after one that had loaded the verify model - retrieval paying a
    model reload it has no reason to care about.

    Embedding locally decouples them completely. Retrieval no longer competes
    with generation for VRAM or for Ollama's queue, and a query embeds in ~20ms
    instead of a variable 0.3-33s.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = nlp_local.embed(list(texts))
        if vectors is None:
            raise RuntimeError("local embedding encoder unavailable")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def _embedding_function():
    """The local encoder when available, Ollama otherwise."""
    if nlp_local.encoder() is not None:
        return LocalEmbeddings(), nlp_local.INTENT_ENCODER
    logger.warning("local encoder unavailable - falling back to Ollama embeddings for retrieval")
    return OllamaEmbeddings(model=config.EMBEDDING_MODEL, base_url=config.OLLAMA_BASE_URL), config.EMBEDDING_MODEL


def collection_name_for(encoder: str) -> str:
    """Collection name is namespaced by encoder.

    Vectors from different encoders are not comparable and have different
    dimensions (MiniLM 384, nomic 768), so they cannot share a collection.
    Namespacing means switching encoders builds a NEW index instead of
    corrupting the existing one or throwing a dimension error - and switching
    back finds the old index still intact."""
    tag = encoder.split("/")[-1].replace(":", "-").replace(".", "-").lower()
    return f"{config.COLLECTION_NAME}_{tag}"


class HybridRetriever:
    def __init__(self):
        self.embeddings, self.encoder_name = _embedding_function()
        self.collection_name = collection_name_for(self.encoder_name)
        self.vector_store = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=str(config.CHROMA_DIR),
        )
        self._bm25 = None
        self._bm25_texts: list[str] = []
        self._bm25_metadatas: list[dict] = []
        self._bm25_count_at_build = -1
        self._lock = threading.Lock()

    # -- BM25 index maintenance -------------------------------------------
    def _collection_count(self) -> int:
        try:
            return self.vector_store._collection.count()
        except Exception:
            return 0

    def _ensure_bm25(self):
        with self._lock:
            current_count = self._collection_count()
            if self._bm25 is not None and current_count == self._bm25_count_at_build:
                return
            if current_count == 0:
                self._bm25 = None
                self._bm25_texts, self._bm25_metadatas = [], []
                self._bm25_count_at_build = 0
                return
            data = self.vector_store._collection.get(include=["documents", "metadatas"])
            self._bm25_texts = data["documents"]
            self._bm25_metadatas = data["metadatas"]
            self._bm25 = BM25Okapi([_tokenize(t) for t in self._bm25_texts])
            self._bm25_count_at_build = current_count

    # -- Candidate generation ----------------------------------------------
    def vector_candidates(self, query: str, k: int, brands: set[str] | None = None) -> list[Document]:
        try:
            results = self.vector_store.similarity_search_with_score(query, k=k * _SCOPE_OVERFETCH if brands else k)
        except Exception:
            return []
        return [doc for doc, _score in results if _in_scope(doc.metadata, brands)][:k]

    def keyword_candidates(self, query: str, k: int, brands: set[str] | None = None) -> list[Document]:
        self._ensure_bm25()
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        docs = []
        for i in ranked_idx:
            if scores[i] <= 0:
                break
            metadata = dict(self._bm25_metadatas[i] or {})
            if not _in_scope(metadata, brands):
                continue
            docs.append(Document(page_content=self._bm25_texts[i], metadata=metadata))
            if len(docs) >= k:
                break
        return docs

    @staticmethod
    def _doc_key(doc: Document) -> str:
        meta = doc.metadata or {}
        return f"{meta.get('source', '')}|{meta.get('page', '')}|{hash(doc.page_content)}"

    def hybrid_search(self, query: str, k: int, brands=None) -> list[Document]:
        """Returns up to `k` Documents, each carrying metadata['relevance']
        in [0, 1] (1.0 = ranked first by every contributing signal).

        `brands` scopes the search to the marques the question is about (see
        intent.py's classification): a Chiron question searches the Bugatti
        documents, a Chiron-vs-Ferrari question searches both. Pass None to
        search everything."""
        scope = set(brands) if brands else None
        ranked_lists = [
            docs
            for docs in (
                self.vector_candidates(query, config.TOP_K_VECTOR, scope),
                self.keyword_candidates(query, config.TOP_K_KEYWORD, scope),
            )
            if docs
        ]
        if not ranked_lists:
            return []

        fused_scores: dict[str, float] = defaultdict(float)
        doc_by_key: dict[str, Document] = {}
        for doc_list in ranked_lists:
            for rank, doc in enumerate(doc_list, start=1):
                key = self._doc_key(doc)
                fused_scores[key] += 1.0 / (config.RRF_K + rank)
                doc_by_key.setdefault(key, doc)

        max_possible = len(ranked_lists) / (config.RRF_K + 1)
        ordered_keys = sorted(fused_scores, key=fused_scores.get, reverse=True)[:k]

        results = []
        for key in ordered_keys:
            doc = doc_by_key[key]
            relevance = round(fused_scores[key] / max_possible, 4) if max_possible else 0.0
            results.append(Document(page_content=doc.page_content, metadata={**(doc.metadata or {}), "relevance": relevance}))
        return results

    # -- Ingestion -----------------------------------------------------------
    def add_documents(self, chunks: list[Document]):
        """Adds newly ingested chunks to the vector store. The BM25 index
        picks them up lazily - _ensure_bm25() notices the chunk count changed
        on the next search - so no separate rebuild call is needed."""
        if not chunks:
            return
        self.vector_store.add_documents(chunks)

    def knowledge_base_status(self) -> dict:
        count = self._collection_count()
        if count == 0:
            return {"documents": 0, "chunks": 0, "ready": False}
        try:
            metadatas = self.vector_store._collection.get(include=["metadatas"]).get("metadatas", [])
            documents = len({m.get("source") for m in metadatas if m and m.get("source")})
        except Exception:
            documents = None
        return {"documents": documents, "chunks": count, "ready": True}


def rerank(question: str, docs: list[Document], target_k: int) -> tuple[list[Document], str]:
    """Reorders the fused candidate pool with a LOCAL cross-encoder and keeps
    the top `target_k`. Returns (docs, method) where method is one of
    "cross-encoder" / "fusion" - so the report can state which ranking
    actually produced the evidence instead of implying a rerank that didn't
    happen.

    A cross-encoder scores (query, passage) jointly, which is why it can fix an
    ordering that bi-encoder similarity got roughly right. It runs in-process
    on onnxruntime in a few hundred milliseconds.

    This replaced an LLM rerank pass that called the fast model with all 25
    candidates in the prompt. That pass ran INSIDE the retrieval step and is
    what made a follow-up's "Document Retrieval" cost 52.9s - and it broke the
    one-model-per-request rule besides."""
    if len(docs) <= target_k:
        return docs[:target_k], "fusion"

    scores = nlp_local.rerank(question, [doc.page_content[:512] for doc in docs])
    if not scores or len(scores) != len(docs):
        return docs[:target_k], "fusion"

    order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:target_k]
    return [docs[i] for i in order], "cross-encoder"


_retriever_lock = threading.Lock()
_retriever: HybridRetriever | None = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        with _retriever_lock:
            if _retriever is None:
                _retriever = HybridRetriever()
    return _retriever
