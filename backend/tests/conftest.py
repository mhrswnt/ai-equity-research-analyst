import sys
import types

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.core import access
from app.core.config import get_settings
from app.core.llm import current_access
from app.main import app
from app.services import compare, documents, sessions

PDF = b"%PDF-1.4 fake pdf bytes"


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Own data dir, clean rate limits and no leaked request access for every test."""
    s = get_settings()
    monkeypatch.setattr(s, "data_dir", tmp_path)
    s.sessions_dir.mkdir(parents=True, exist_ok=True)
    s.chroma_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(compare, "_extract_agent", None)
    access.reset_rate_limits()
    token = current_access.set(None)
    yield
    current_access.reset(token)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def sid():
    return sessions.create()["session_id"]


@pytest.fixture
def auth(sid):
    return {"X-Session-Id": sid}


BYOK_KEY = "sk-ant-testkey-1234567890"


@pytest.fixture
def byok():
    return {"X-LLM-Provider": "anthropic", "X-LLM-Api-Key": BYOK_KEY, "X-LLM-Model": "claude-sonnet-5-5"}


def make_request(headers: dict | None = None, client=("1.2.3.4", 5000)) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw, "client": client, "query_string": b""})


class Recorder:
    """Stand-in for provider classes: remembers constructor kwargs."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture
def fake_module(monkeypatch):
    def make(name: str, **attrs):
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod
    return make


@pytest.fixture
def block_import(monkeypatch):
    def block(name: str):
        monkeypatch.setitem(sys.modules, name, None)  # makes `import name` raise ImportError
    return block


class FakeLoader:
    pages = 3

    def __init__(self, path):
        self.path = path

    def load_and_split(self):
        return [Document(page_content=f"page {i}", metadata={"page": i}) for i in range(self.pages)]


class FakeChroma:
    collections: dict = {}
    retrievers: list = []

    def __init__(self, collection_name, persist_directory):
        self.name = collection_name

    @classmethod
    def from_documents(cls, docs, collection_name, persist_directory):
        cls.collections[collection_name] = docs
        return cls(collection_name, persist_directory)

    def delete_collection(self):
        self.collections.pop(self.name)

    def as_retriever(self, search_type, search_kwargs):
        self.retrievers.append((self.name, search_type, search_kwargs))
        return "retriever"


@pytest.fixture
def fake_store(monkeypatch):
    """Replace Chroma + PyPDFLoader in the documents service."""
    FakeChroma.collections, FakeChroma.retrievers, FakeLoader.pages = {}, [], 3
    monkeypatch.setattr(documents, "Chroma", FakeChroma)
    monkeypatch.setattr(documents, "PyPDFLoader", FakeLoader)
    return FakeChroma
