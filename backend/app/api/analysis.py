from fastapi import APIRouter, HTTPException, Request

from app.core import tasks
from app.core.access import authorize
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services import analysis

router = APIRouter(tags=["analysis"])

_NEEDS = {"price_summary": ("ticker",), "technical": ("ticker",), "backtest": ("ticker",), "compare": ("tickers",),
          "custom": ("prompt",)}


@router.post("/analysis", response_model=AnalysisResponse)
async def run_analysis(req: AnalysisRequest, request: Request):
    missing = [f for f in _NEEDS[req.task] if not getattr(req, f)]
    if missing:
        raise HTTPException(422, f"task '{req.task}' requires: {', '.join(missing)}")
    if req.task == "custom":
        prompt = req.prompt
    else:  # validate the period/windows before spending the caller's rate-limit quota
        try:
            prompt = analysis.build_prompt(req.task, req.model_dump(exclude={"task", "prompt"}, exclude_none=True))
        except ValueError as e:
            raise HTTPException(422, str(e))
    authorize(request, tasks.analysis_level(req.task))  # level depends on the chosen task
    return AnalysisResponse(task=req.task, prompt=prompt, result=await analysis.run(prompt))
