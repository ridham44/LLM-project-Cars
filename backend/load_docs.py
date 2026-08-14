from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

import config
from intent_taxonomy import brand_for_filename

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".html", ".htm"}


def _load_txt_or_md(path: Path) -> list[Document]:
    return [Document(page_content=path.read_text(encoding="utf-8", errors="replace"), metadata={"source": str(path)})]


def _load_html(path: Path) -> list[Document]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = BeautifulSoup(raw, "html.parser").get_text(separator="\n")
    return [Document(page_content=text, metadata={"source": str(path)})]


def _load_docx(path: Path) -> list[Document]:
    docx_file = DocxDocument(str(path))
    text = "\n".join(p.text for p in docx_file.paragraphs if p.text.strip())
    return [Document(page_content=text, metadata={"source": str(path)})]


def _load_pdf(path: Path) -> list[Document]:
    return PyPDFLoader(str(path)).load()


_LOADERS = {
    ".txt": _load_txt_or_md,
    ".md": _load_txt_or_md,
    ".html": _load_html,
    ".htm": _load_html,
    ".docx": _load_docx,
    ".pdf": _load_pdf,
}


def load_file(path: Path) -> list[Document]:
    loader = _LOADERS.get(path.suffix.lower())
    if not loader:
        raise ValueError(f"Unsupported document type: {path.suffix}")
    documents = loader(path)

    # Stamp the marque so retrieval can scope a question to the documents it
    # is actually about (see retrieval.brand_of). Derived from the filename -
    # the loaders don't all set `source` the same way, and inferring it once
    # here beats re-deriving it on every search. Unknown is left unset rather
    # than guessed: retrieval treats unattributed documents as always in
    # scope, so a wrong guess would be worse than no answer.
    brand = brand_for_filename(path.name)
    if brand:
        for document in documents:
            document.metadata = {**(document.metadata or {}), "brand": brand}
    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP)
    return splitter.split_documents(documents)


def parse_and_chunk(path: Path) -> list[Document]:
    """Used both by the bulk startup ingestion below and by the
    /documents/upload endpoint (api.py), so both paths parse and chunk
    identically."""
    return split_documents(load_file(path))


def load_and_split_documents() -> list[Document]:
    documents = []
    for path in sorted(config.DOCUMENTS_DIR.iterdir()) if config.DOCUMENTS_DIR.exists() else []:
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            documents.extend(load_file(path))
    return split_documents(documents)


def build_vector_store():
    import retrieval

    chunks = load_and_split_documents()
    retriever = retrieval.get_retriever()
    retriever.add_documents(chunks)
    return retriever.vector_store


def main():
    has_docs = config.DOCUMENTS_DIR.exists() and any(
        p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS for p in config.DOCUMENTS_DIR.iterdir()
    )
    if not has_docs:
        raise SystemExit(
            f"No supported documents ({', '.join(sorted(SUPPORTED_EXTENSIONS))}) found in "
            f"{config.DOCUMENTS_DIR}. Run fake_docs.py first, or add your own files there."
        )

    vector_store = build_vector_store()
    count = vector_store._collection.count()
    print(f"Loaded documents into Chroma collection '{config.COLLECTION_NAME}' ({count} chunks) at {config.CHROMA_DIR}")


if __name__ == "__main__":
    main()
