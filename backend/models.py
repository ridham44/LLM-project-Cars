from typing import Optional

from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    research: str
    quick: str
    analysis: str
    context: str


class SearchRequest(BaseModel):
    question: str


class ResearchRequest(BaseModel):
    question: str
    # Identifies the browser conversation so follow-ups ("cross-check that",
    # "what about its transmission") can resolve against the previous turn -
    # see context_store.py. No "mode"/model/research_type: the backend
    # decides intent, complexity, retrieval and model routing itself.
    session_id: Optional[str] = None


class DocumentUploadResponse(BaseModel):
    status: str
    filename: str
    chunks_added: Optional[int] = None
    detail: Optional[str] = None


class SearchResponse(BaseModel):
    results: str


class ModelStatus(BaseModel):
    name: str
    available: Optional[bool] = None


class OllamaStatus(BaseModel):
    reachable: bool


class KnowledgeBaseStatus(BaseModel):
    documents: Optional[int] = None
    chunks: Optional[int] = None
    ready: bool = False


class HealthResponse(BaseModel):
    status: str
    ollama: Optional[OllamaStatus] = None
    models: Optional[dict[str, ModelStatus]] = None
    knowledge_base: Optional[KnowledgeBaseStatus] = None
    # Local NLP layer states (spaCy / intent encoder / cross-encoder). Free-form
    # so nlp_local.status() can grow a field without a schema change here.
    nlp: Optional[dict[str, str]] = None
