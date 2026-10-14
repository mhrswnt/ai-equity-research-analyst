from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import session_id
from app.core import tasks
from app.core.access import gate
from app.schemas.strategy import StrategyRequest, StrategyResponse
from app.services import documents, strategy

router = APIRouter(tags=["strategy"])


@router.post("/strategy", response_model=StrategyResponse, dependencies=[Depends(gate(tasks.level_of("strategy")))])
async def build_strategy(req: StrategyRequest, sid: str = Depends(session_id)):
    try:
        documents.get_document(sid, req.document_id)
    except KeyError:
        raise HTTPException(404, "Document not found")
    return await strategy.generate(sid, req.document_id, req.libraries, req.instruction, req.extract_query, req.top_k)
