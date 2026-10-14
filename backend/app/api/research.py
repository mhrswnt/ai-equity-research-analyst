import json

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.core import tasks
from app.core.access import gate
from app.schemas.research import ResearchRequest, ResearchResponse
from app.services import research

router = APIRouter(tags=["research"], dependencies=[Depends(gate(tasks.level_of("research")))])


@router.post("/research", response_model=ResearchResponse)
async def run(req: ResearchRequest):
    return await research.run_research(req.topic)


@router.post("/research/stream")
async def stream(req: ResearchRequest):
    async def events():
        async for ev in research.stream_research(req.topic):
            yield {"event": ev["type"], "data": json.dumps(ev)}
    return EventSourceResponse(events())
