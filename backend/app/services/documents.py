"""Session-scoped PDF ingestion: validate -> PyPDFLoader -> split -> Chroma (one collection per document).
Single ingestion path for the app. Everything is namespaced by session id and deleted with the session."""
import hashlib
import json
import shutil
import threading
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader

from app.core.config import get_settings

_lock = threading.Lock()


class UploadError(Exception):
    """Invalid upload; carries the HTTP status and a machine-readable code for the API layer."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _registry_path(sid: str) -> Path:
    return get_settings().session_dir(sid) / "documents.json"


def _load_registry(sid: str) -> dict:
    p = _registry_path(sid)
    return json.loads(p.read_text()) if p.exists() else {}


def _save_registry(sid: str, reg: dict) -> None:
    _registry_path(sid).write_text(json.dumps(reg, indent=2))


def _collection(sid: str, doc_id: str) -> str:
    return f"s{sid}_{doc_id}"


def _store(collection: str) -> Chroma:
    return Chroma(collection_name=collection, persist_directory=str(get_settings().chroma_dir))


def ingest_pdf(sid: str, filename: str, content: bytes, name: str | None = None) -> dict:
    """Validate, save and index a PDF in the session. Same bytes twice return the existing document."""
    s = get_settings()
    if not content.startswith(b"%PDF-"):
        raise UploadError(400, "invalid_pdf", "File is not a PDF.")
    if len(content) > s.max_upload_mb * 1024 * 1024:
        raise UploadError(413, "file_too_large", f"PDF exceeds the {s.max_upload_mb} MB limit.")
    doc_id = hashlib.sha256(content).hexdigest()[:12]
    with _lock:
        reg = _load_registry(sid)
        if doc_id in reg:
            return reg[doc_id]
        if len(reg) >= s.max_docs_per_session:
            raise UploadError(409, "too_many_documents", f"A session can hold at most {s.max_docs_per_session} documents.")
        uploads = s.session_dir(sid) / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        path = uploads / f"{doc_id}.pdf"
        path.write_bytes(content)
        try:
            pages = PyPDFLoader(str(path)).load_and_split()
        except Exception as e:  # corrupt, encrypted, ...
            path.unlink()
            raise UploadError(422, "unreadable_pdf", "The PDF could not be read (corrupt or password-protected).") from e
        if not pages or len(pages) > s.max_pages:
            path.unlink()
            raise UploadError(422, "bad_page_count", f"PDF must have between 1 and {s.max_pages} pages.")
        collection = _collection(sid, doc_id)
        Chroma.from_documents(pages, collection_name=collection, persist_directory=str(s.chroma_dir))
        entry = {
            "id": doc_id,
            "name": (name or Path(filename).stem)[:100],
            "filename": Path(filename).name[:255],
            "path": str(path),
            "collection": collection,
            "pages": len(pages),
        }
        reg[doc_id] = entry
        _save_registry(sid, reg)
        return entry


def list_documents(sid: str) -> list[dict]:
    return list(_load_registry(sid).values())


def get_document(sid: str, doc_id: str) -> dict:
    """Raises KeyError unless the document belongs to this session."""
    reg = _load_registry(sid)
    if doc_id not in reg:
        raise KeyError(doc_id)
    return reg[doc_id]


def get_page(sid: str, doc_id: str, page: int) -> dict:
    """Return a single page's text/metadata (notebook: `hdfc_pages[13]`)."""
    doc = get_document(sid, doc_id)
    pages = PyPDFLoader(doc["path"]).load_and_split()
    if not 0 <= page < len(pages):
        raise IndexError(page)
    return {"page": page, "content": pages[page].page_content, "metadata": pages[page].metadata}


def delete_document(sid: str, doc_id: str) -> None:
    with _lock:
        reg = _load_registry(sid)
        doc = reg.pop(doc_id)
        _store(doc["collection"]).delete_collection()
        Path(doc["path"]).unlink(missing_ok=True)
        _save_registry(sid, reg)


def get_retriever(sid: str, doc_id: str, k: int | None = None):
    """Single retriever factory (similarity, top-k) used by chat and strategy."""
    doc = get_document(sid, doc_id)
    return _store(doc["collection"]).as_retriever(
        search_type="similarity", search_kwargs={"k": k or get_settings().rag_top_k}
    )


def purge_session(sid: str) -> None:
    """Delete every vector collection, PDF and registry entry of a session."""
    with _lock:
        for doc in _load_registry(sid).values():
            _store(doc["collection"]).delete_collection()
        shutil.rmtree(get_settings().session_dir(sid), ignore_errors=True)
