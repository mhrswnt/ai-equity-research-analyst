from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import session_id
from app.core import tasks
from app.core.access import gate
from app.core.config import get_settings
from app.schemas.documents import ChatRequest, ChatResponse, DocumentOut
from app.services import documents, rag

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=DocumentOut)
async def upload(file: UploadFile = File(...), name: str | None = None, sid: str = Depends(session_id)):
    limit = get_settings().max_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)  # never buffer more than limit+1 bytes
    if len(content) > limit:
        raise HTTPException(413, {"code": "file_too_large", "message": f"PDF exceeds the {get_settings().max_upload_mb} MB limit."})
    try:
        return documents.ingest_pdf(sid, file.filename, content, name)
    except documents.UploadError as e:
        raise HTTPException(e.status, {"code": e.code, "message": e.message})


@router.get("/documents", response_model=list[DocumentOut])
def list_all(sid: str = Depends(session_id)):
    return documents.list_documents(sid)


@router.get("/documents/{doc_id}/pages/{page}")
def page(doc_id: str, page: int, sid: str = Depends(session_id)):
    try:
        return documents.get_page(sid, doc_id, page)
    except KeyError:
        raise HTTPException(404, "Document not found")
    except IndexError:
        raise HTTPException(404, "Page out of range")


@router.delete("/documents/{doc_id}", status_code=204)
def delete(doc_id: str, sid: str = Depends(session_id)):
    try:
        documents.delete_document(sid, doc_id)
    except KeyError:
        raise HTTPException(404, "Document not found")


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(gate(tasks.level_of("qa")))])
def chat(req: ChatRequest, sid: str = Depends(session_id)):
    try:
        return rag.answer(sid, req.question, req.document_ids, req.top_k)
    except KeyError as e:
        raise HTTPException(404, f"Document not found: {e.args[0]}")
