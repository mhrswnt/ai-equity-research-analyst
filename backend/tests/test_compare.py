import pytest
from llama_cloud.core.api_error import ApiError

from app.core.config import get_settings
from app.schemas.compare import (ComparativeAnalysisOutput, FinancialModelOutput, InitialFinancialDataOutput,
                                 RawFinancials)
from app.services import compare


class FakeExtractClient:
    created = []
    existing = None
    error = None

    def get_agent(self, name):
        if self.error:
            raise self.error
        return self.existing

    def create_agent(self, name, data_schema, config):
        agent = object()
        self.created.append((name, data_schema, config))
        return agent


@pytest.fixture
def extract_client(monkeypatch):
    FakeExtractClient.created, FakeExtractClient.existing, FakeExtractClient.error = [], None, None
    monkeypatch.setattr(compare, "LlamaExtract", FakeExtractClient)
    monkeypatch.setattr(compare, "ExtractConfig", lambda extraction_mode: ("cfg", extraction_mode))
    return FakeExtractClient


def test_get_extract_agent_reuses_existing_and_caches(extract_client):
    extract_client.existing = "agent"
    assert compare.get_extract_agent() == "agent"
    extract_client.existing = "other"
    assert compare.get_extract_agent() == "agent" and extract_client.created == []


def test_get_extract_agent_creates_when_missing(extract_client):
    s = get_settings()
    assert compare.get_extract_agent() is not None
    assert extract_client.created == [(s.extract_agent_name, InitialFinancialDataOutput, ("cfg", s.extract_mode))]


def test_get_extract_agent_creates_on_404_and_raises_otherwise(extract_client):
    extract_client.error = ApiError(status_code=404, body="nf")
    assert compare.get_extract_agent() is not None and len(extract_client.created) == 1
    compare._extract_agent = None
    extract_client.error = ApiError(status_code=500, body="boom")
    with pytest.raises(ApiError):
        compare.get_extract_agent()


class FakeExtractAgent:
    async def aextract(self, path):
        name = "Dr Reddys" if path.endswith("a.pdf") else "Biocon"
        data = InitialFinancialDataOutput(
            company_name=name, ticker=name[:3].upper(), report_date="2026-03-31",
            raw_financials=RawFinancials(revenue=100.0, operating_income=20.0, eps=5.0))
        return type("Res", (), {"data": data.model_dump()})()


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def astructured_predict(self, cls, prompt, **kw):
        self.calls.append((cls, kw))
        if cls is FinancialModelOutput:
            return FinancialModelOutput(revenue_projection=110.0, growth_rate=10.0, valuation_estimate=900.0, summary="s")
        return ComparativeAnalysisOutput(comparative_analysis="A beats B", overall_recommendation="Buy A")


async def test_workflow_end_to_end_with_fakes():
    llm = FakeLLM()
    wf = compare.ComparativeAnalysisWorkflow(FakeExtractAgent(), get_settings().modeling_assumptions_path, llm, timeout=30)
    memo = (await wf.run(deck_path_a="a.pdf", deck_path_b="b.pdf"))["memo"]
    assert (memo.company_a_name, memo.company_b_name) == ("Dr Reddys", "Biocon")
    assert memo.company_a_model.growth_rate == 10.0 and memo.comparative_analysis.overall_recommendation == "Buy A"
    model_calls = [kw for cls, kw in llm.calls if cls is FinancialModelOutput]
    assert len(model_calls) == 2 and all("WACC" in kw["assumptions"] for kw in model_calls)


async def test_compare_resolves_documents_in_session(monkeypatch):
    docs = {("S", "da"): {"path": "/x/a.pdf"}, ("S", "db"): {"path": "/x/b.pdf"}}
    monkeypatch.setattr(compare.documents, "get_document", lambda sid, i: docs[(sid, i)])
    monkeypatch.setattr(compare, "get_extract_agent", lambda: FakeExtractAgent())
    seen = {}
    monkeypatch.setattr(compare, "get_llm", lambda role, fw: seen.update(role=role, fw=fw) or FakeLLM())
    memo = await compare.compare("S", "da", "db")
    assert memo.company_a_name == "Dr Reddys" and seen == {"role": "compare", "fw": "llamaindex"}
