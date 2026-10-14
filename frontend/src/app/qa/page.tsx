"use client";
import { useRef, useState } from "react";
import { ErrorNotice, Spinner } from "@/components/ErrorNotice";
import { Library } from "@/components/Library";
import { Markdown } from "@/components/Markdown";
import { client } from "@/lib/api";
import { useApp } from "@/lib/store";
import { useRun } from "@/lib/useRun";
import type { ChatSource } from "@/lib/types";

interface Turn { question: string; answer?: string; sources: ChatSource[]; error?: Error }

const SUGGESTIONS = ["Summarize the key financial highlights", "How did revenue and net profit change year on year?", "Any guidance or outlook changes?", "Compare operating margins"];

/** Deduplicate chunk-level sources by document + page; numbering follows first appearance. */
function citations(sources: ChatSource[]) {
  const seen = new Map<string, ChatSource & { texts: string[] }>();
  for (const s of sources) {
    const key = `${s.document_id}:${s.page}`;
    const hit = seen.get(key);
    if (hit) hit.texts.push(s.excerpt);
    else seen.set(key, { ...s, texts: [s.excerpt] });
  }
  return [...seen.values()];
}

export default function QA() {
  const { selected, documents, log } = useApp();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [active, setActive] = useState<{ turn: number; idx: number } | null>(null);
  const [fullPage, setFullPage] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const page = useRun(client.getPage);

  async function submit(q = question) {
    if (!q.trim() || !selected.length) return;
    setQuestion("");
    const idx = turns.length;
    setTurns((t) => [...t, { question: q, sources: [] }]);
    setFullPage(null);
    setBusy(true);
    try {
      const res = await client.chat(q, selected);
      setTurns((t) => t.map((x, i) => (i === idx ? { ...x, answer: res.answer, sources: res.sources } : x)));
      log("Document Q&A", q.length > 70 ? `${q.slice(0, 70)}…` : q);
      if (res.sources.length) setActive({ turn: idx, idx: 0 });
    } catch (e) {
      setTurns((t) => t.map((x, i) => (i === idx ? { ...x, error: e as Error } : x)));
    } finally {
      setBusy(false);
    }
    setTimeout(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  const cites = active ? citations(turns[active.turn]?.sources ?? []) : [];
  const src = active ? cites[active.idx] : null;

  return (
    <div className="qa">
      <section className="lib"><Library /></section>
      <section className="chat">
        <div className="messages">
          {turns.length === 0 && <p className="muted">Select documents on the left and ask a question. Answers cite the pages they came from.</p>}
          {turns.map((t, i) => {
            const c = citations(t.sources);
            return (
              <div key={i} style={{ display: "contents" }}>
                <div className="bubble-user">{t.question}</div>
                <div className="answer">
                  <div className="eyebrow">Analyst</div>
                  {t.answer ? <Markdown>{t.answer}</Markdown> : t.error ? <ErrorNotice error={t.error} /> : <Spinner label="Searching filings…" />}
                  {c.length > 0 && (
                    <div className="chips" style={{ marginTop: 12 }}>
                      {c.map((s, j) => (
                        <button key={j} className={`cite${active?.turn === i && active.idx === j ? " on" : ""}`} onClick={() => { setActive({ turn: i, idx: j }); setFullPage(null); }}>
                          [{j + 1}] {s.document ?? s.tool} · p. {s.page_number ?? "?"}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          <div ref={bottom} />
        </div>
        <div className="composer">
          <div className="suggest">{SUGGESTIONS.map((s) => <button key={s} onClick={() => setQuestion(s)}>{s}</button>)}</div>
          <form className="box" onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={selected.length ? "Ask across the selected filings…" : "Select at least one document first"} />
            <button className="btn primary" disabled={busy || !selected.length || !question.trim()}>{busy ? "…" : "Ask"}</button>
          </form>
          {documents.length > 0 && !selected.length && <span className="muted small">Tick a document in the library to include it in scope.</span>}
        </div>
      </section>
      <section className="src">
        <div className="eyebrow">Source {src ? `[${active!.idx + 1}]` : ""}</div>
        {!src && <p className="muted small">Click a citation to see the retrieved passage.</p>}
        {src && (
          <>
            <p style={{ margin: "6px 0 14px" }}>{src.document} — page {src.page_number ?? "?"}</p>
            <div className="paper">{fullPage ?? src.texts.join("\n\n…\n\n")}</div>
            {src.document_id && src.page !== null && (
              <button className="btn sm" style={{ marginTop: 12 }} disabled={page.loading}
                      onClick={async () => { const p = await page.run(src.document_id!, src.page!); if (p) setFullPage(p.content); }}>
                {page.loading ? "Loading…" : fullPage ? "Showing full page" : "Open full page"}
              </button>
            )}
            <ErrorNotice error={page.error} />
          </>
        )}
      </section>
    </div>
  );
}
