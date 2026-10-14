from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import session_id
from app.core import tasks
from app.core.access import gate
from app.schemas.compare import CompareRequest, FinalEquityResearchMemoOutput
from app.services import compare, documents

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=FinalEquityResearchMemoOutput,
             dependencies=[Depends(gate(tasks.level_of("compare_memo")))])
async def run(req: CompareRequest, sid: str = Depends(session_id)):
    if req.document_id_a == req.document_id_b:
        raise HTTPException(422, "Choose two different documents to compare.")
    for doc_id in (req.document_id_a, req.document_id_b):
        try:
            documents.get_document(sid, doc_id)
        except KeyError:
            raise HTTPException(404, f"Document not found: {doc_id}")
    return await compare.compare(sid, req.document_id_a, req.document_id_b)
