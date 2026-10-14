import json
import time

import pytest

from app.core.config import get_settings
from app.services import documents, sessions
from tests.conftest import PDF, FakeLoader


def test_create_touch_delete(sid):
    s = get_settings()
    assert s.session_dir(sid).is_dir() and sessions.SESSION_ID_RE.match(sid)
    assert sessions.touch(sid) is True
    sessions.delete(sid)
    assert not s.session_dir(sid).exists() and sessions.touch(sid) is False


@pytest.mark.parametrize("bad", ["", "../etc", "short", "G" * 32, "a" * 31, "a" * 33, "a" * 32])
def test_invalid_or_unknown_ids(bad):
    assert sessions.touch(bad) is False
    sessions.delete(bad)  # must not raise or touch the filesystem


def test_expiry_deletes_session(sid, monkeypatch):
    meta = get_settings().session_dir(sid) / "session.json"
    data = json.loads(meta.read_text())
    meta.write_text(json.dumps({**data, "last_seen": time.time() - 3 * 3600}))
    assert sessions.touch(sid) is False and not get_settings().session_dir(sid).exists()


def test_touch_refreshes_last_seen(sid):
    meta = get_settings().session_dir(sid) / "session.json"
    meta.write_text(json.dumps({"created": 1.0, "last_seen": time.time() - 60}))
    assert sessions.touch(sid)
    data = json.loads(meta.read_text())
    assert data["created"] == 1.0 and data["last_seen"] > time.time() - 5


def test_sweep_expired(sid):
    s = get_settings()
    old = sessions.create()["session_id"]
    (s.session_dir(old) / "session.json").write_text(json.dumps({"created": 0, "last_seen": 0}))
    half = "b" * 32
    s.session_dir(half).mkdir()                      # crashed mid-create: no session.json
    (s.sessions_dir / "stray.txt").write_text("x")   # not a session
    (s.sessions_dir / "not-a-session-dir").mkdir()   # ignored
    assert sessions.sweep_expired() == 2
    assert s.session_dir(sid).exists() and not s.session_dir(old).exists() and not s.session_dir(half).exists()
    assert (s.sessions_dir / "not-a-session-dir").exists()


# ---------------- documents ----------------
def test_ingest_is_idempotent_per_session_and_isolated(fake_store, sid):
    other = sessions.create()["session_id"]
    a = documents.ingest_pdf(sid, "HDFC Bank.pdf", PDF)
    assert documents.ingest_pdf(sid, "again.pdf", PDF) == a
    b = documents.ingest_pdf(other, "x.pdf", PDF, name="Custom")  # same bytes, other session: separate doc
    assert a["collection"] != b["collection"] and a["name"] == "HDFC Bank" and b["name"] == "Custom"
    assert a["pages"] == 3 and len(documents.list_documents(sid)) == 1
    assert get_settings().session_dir(sid).joinpath("uploads", f"{a['id']}.pdf").read_bytes() == PDF
    assert documents.get_document(sid, a["id"]) == a
    third = sessions.create()["session_id"]
    with pytest.raises(KeyError):
        documents.get_document(third, a["id"])


def test_upload_validation(fake_store, sid, monkeypatch):
    s = get_settings()
    for bad in (b"", b"<html>not a pdf", b"MZ\x90 exe"):
        with pytest.raises(documents.UploadError) as e:
            documents.ingest_pdf(sid, "x.pdf", bad)
        assert (e.value.status, e.value.code) == (400, "invalid_pdf")
    monkeypatch.setattr(s, "max_upload_mb", 0)
    with pytest.raises(documents.UploadError) as e:
        documents.ingest_pdf(sid, "x.pdf", PDF)
    assert (e.value.status, e.value.code) == (413, "file_too_large")


def test_document_cap_and_name_limits(fake_store, sid, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_docs_per_session", 1)
    d = documents.ingest_pdf(sid, "n" * 400 + ".pdf", PDF, name="N" * 300)
    assert len(d["name"]) == 100 and len(d["filename"]) <= 255
    assert documents.ingest_pdf(sid, "dup.pdf", PDF) == d  # re-upload does not count against the cap
    with pytest.raises(documents.UploadError) as e:
        documents.ingest_pdf(sid, "other.pdf", PDF + b"2")
    assert (e.value.status, e.value.code) == (409, "too_many_documents")


def test_unreadable_and_bad_page_counts_leave_nothing_behind(fake_store, sid, monkeypatch):
    uploads = get_settings().session_dir(sid) / "uploads"

    class Broken:
        def __init__(self, path):
            pass

        def load_and_split(self):
            raise ValueError("encrypted")

    monkeypatch.setattr(documents, "PyPDFLoader", Broken)
    with pytest.raises(documents.UploadError) as e:
        documents.ingest_pdf(sid, "x.pdf", PDF)
    assert (e.value.status, e.value.code) == (422, "unreadable_pdf")

    monkeypatch.setattr(documents, "PyPDFLoader", FakeLoader)
    FakeLoader.pages = 0
    with pytest.raises(documents.UploadError) as e:
        documents.ingest_pdf(sid, "x.pdf", PDF)
    assert e.value.code == "bad_page_count"
    FakeLoader.pages = 5
    monkeypatch.setattr(get_settings(), "max_pages", 4)
    with pytest.raises(documents.UploadError):
        documents.ingest_pdf(sid, "x.pdf", PDF)
    assert list(uploads.iterdir()) == [] and documents.list_documents(sid) == [] and fake_store.collections == {}


def test_pages_delete_and_retriever(fake_store, sid):
    d = documents.ingest_pdf(sid, "a.pdf", PDF)
    assert documents.get_page(sid, d["id"], 1)["content"] == "page 1"
    for bad in (-1, 3):
        with pytest.raises(IndexError):
            documents.get_page(sid, d["id"], bad)
    assert documents.get_retriever(sid, d["id"]) == "retriever"
    documents.get_retriever(sid, d["id"], 9)
    assert fake_store.retrievers[0][2] == {"k": get_settings().rag_top_k} and fake_store.retrievers[1][2] == {"k": 9}
    documents.delete_document(sid, d["id"])
    assert documents.list_documents(sid) == [] and fake_store.collections == {}
    with pytest.raises(KeyError):
        documents.delete_document(sid, d["id"])


def test_purge_session_removes_vectors_and_files(fake_store, sid):
    other = sessions.create()["session_id"]
    documents.ingest_pdf(sid, "a.pdf", PDF)
    keep = documents.ingest_pdf(other, "a.pdf", PDF)
    documents.purge_session(sid)
    assert not get_settings().session_dir(sid).exists()
    assert list(fake_store.collections) == [keep["collection"]]
    sessions.delete(other)
    assert fake_store.collections == {}
