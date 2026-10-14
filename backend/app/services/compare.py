"""Comparative analysis: LlamaExtract parses two PDFs in parallel -> per-company financial model (using the modeling
assumptions file) -> joined comparison memo. LlamaIndex event-driven Workflow ported from the notebook."""
import asyncio

from llama_cloud.core.api_error import ApiError
from llama_cloud import ExtractConfig
from llama_cloud_services import LlamaExtract
from llama_index.core.prompts import ChatPromptTemplate
from llama_index.core.workflow import Context, Event, StartEvent, StopEvent, Workflow, step

from app.core.config import get_settings
from app.core.llm import get_llm
from app.schemas.compare import (ComparativeAnalysisOutput, FinalEquityResearchMemoOutput, FinancialModelOutput,
                                 InitialFinancialDataOutput)
from app.services import documents

_extract_agent = None


def get_extract_agent():
    """Get-or-create the LlamaCloud extraction agent (the notebook deleted/recreated it every run)."""
    global _extract_agent
    if _extract_agent is None:
        s = get_settings()
        client = LlamaExtract()
        try:
            _extract_agent = client.get_agent(name=s.extract_agent_name)
        except ApiError as e:
            if e.status_code != 404:
                raise
            _extract_agent = None
        if _extract_agent is None:
            _extract_agent = client.create_agent(
                name=s.extract_agent_name,
                data_schema=InitialFinancialDataOutput,
                config=ExtractConfig(extraction_mode=s.extract_mode),
            )
    return _extract_agent


class DeckAParseEvent(Event):
    deck_content: InitialFinancialDataOutput


class DeckBParseEvent(Event):
    deck_content: InitialFinancialDataOutput


class CompanyAModelEvent(Event):
    model_output: FinancialModelOutput


class CompanyBModelEvent(Event):
    model_output: FinancialModelOutput


MODEL_PROMPT = """You are an expert financial analyst.
Using the following raw financial data and modeling assumptions, 
produce a financial model summary.

Raw Financial Data:
{raw_data}

Financial Modeling Assumptions:
{assumptions}

Return your output as JSON with fields:
- revenue_projection (float): Projected revenue for next year in crores INR
- growth_rate (float): Expected revenue growth rate as percentage
- valuation_estimate (float): Estimated enterprise value in crores INR
- summary (str): Brief summary of the analysis
"""

COMPARE_PROMPT = """You are an expert investment analyst.
Compare the following financial models and provide an investment recommendation.

Company A Model:
{company_a_model}

Company B Model:
{company_b_model}

Return your output as JSON with fields:
- comparative_analysis (str): Detailed comparison of the two companies
- overall_recommendation (str): Investment recommendation with rationale
"""


class ComparativeAnalysisWorkflow(Workflow):
    def __init__(self, extract_agent, modeling_path, llm, **kwargs):
        super().__init__(**kwargs)
        self.extract_agent = extract_agent
        self.llm = llm
        with open(modeling_path, "r") as f:
            self.modeling_data = f.read()

    async def _parse_deck(self, deck_path) -> InitialFinancialDataOutput:
        result = await self.extract_agent.aextract(deck_path)
        return InitialFinancialDataOutput(**result.data)

    @step
    async def parse_deck_a(self, ctx: Context, ev: StartEvent) -> DeckAParseEvent:
        return DeckAParseEvent(deck_content=await self._parse_deck(ev.deck_path_a))

    @step
    async def parse_deck_b(self, ctx: Context, ev: StartEvent) -> DeckBParseEvent:
        return DeckBParseEvent(deck_content=await self._parse_deck(ev.deck_path_b))

    async def _generate_financial_model(self, data: InitialFinancialDataOutput) -> FinancialModelOutput:
        prompt = ChatPromptTemplate.from_messages([("user", MODEL_PROMPT)])
        return await self.llm.astructured_predict(
            FinancialModelOutput, prompt, raw_data=data.model_dump_json(), assumptions=self.modeling_data
        )

    @step
    async def refine_model_a(self, ctx: Context, ev: DeckAParseEvent) -> CompanyAModelEvent:
        await ctx.store.set("name_a", ev.deck_content.company_name)
        return CompanyAModelEvent(model_output=await self._generate_financial_model(ev.deck_content))

    @step
    async def refine_model_b(self, ctx: Context, ev: DeckBParseEvent) -> CompanyBModelEvent:
        await ctx.store.set("name_b", ev.deck_content.company_name)
        return CompanyBModelEvent(model_output=await self._generate_financial_model(ev.deck_content))

    @step
    async def compare_models(self, ctx: Context, ev: CompanyAModelEvent | CompanyBModelEvent) -> StopEvent | None:
        events = ctx.collect_events(ev, [CompanyAModelEvent, CompanyBModelEvent])
        if events is None:
            return None
        model_a, model_b = events[0].model_output, events[1].model_output
        prompt = ChatPromptTemplate.from_messages([("user", COMPARE_PROMPT)])
        analysis = await self.llm.astructured_predict(
            ComparativeAnalysisOutput, prompt,
            company_a_model=model_a.model_dump_json(), company_b_model=model_b.model_dump_json(),
        )
        final = FinalEquityResearchMemoOutput(
            company_a_name=await ctx.store.get("name_a", default=""),
            company_b_name=await ctx.store.get("name_b", default=""),
            company_a_model=model_a, company_b_model=model_b, comparative_analysis=analysis,
        )
        return StopEvent(result={"memo": final})


async def compare(sid: str, doc_id_a: str, doc_id_b: str) -> FinalEquityResearchMemoOutput:
    s = get_settings()
    path_a = documents.get_document(sid, doc_id_a)["path"]
    path_b = documents.get_document(sid, doc_id_b)["path"]
    extract_agent = await asyncio.to_thread(get_extract_agent)
    workflow = ComparativeAnalysisWorkflow(
        extract_agent=extract_agent,
        modeling_path=s.modeling_assumptions_path,
        llm=get_llm("compare", "llamaindex"),
        timeout=s.compare_timeout_s,
    )
    result = await workflow.run(deck_path_a=path_a, deck_path_b=path_b)
    return result["memo"]
