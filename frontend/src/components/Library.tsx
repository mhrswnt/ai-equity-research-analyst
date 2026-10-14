"use client";
import { useRef, useState } from "react";
import { useApp } from "@/lib/store";
import { useRun } from "@/lib/useRun";
import { ErrorNotice } from "./ErrorNotice";

/** Upload + document list. `mode="multi"` shows checkboxes (scope); `"single"` behaves like radios. */
export function Library({ mode = "multi", max }: { mode?: "multi" | "single"; max?: number }) {
  const { documents, selected, toggleSelected, setSelected, upload, removeDocument } = useApp();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const up = useRun(upload);

  const pick = (id: string) => {
    if (mode === "single") setSelected([id]);
    else if (!selected.includes(id) && max && selected.length >= max) setSelected([...selected.slice(1), id]);
    else toggleSelected(id);
  };

  return (
    <div>
      <div className={`dropzone${over ? " over" : ""}`} onClick={() => input.current?.click()}
           onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
           onDrop={(e) => { e.preventDefault(); setOver(false); up.run(e.dataTransfer.files); }}>
        {up.loading ? <span><span className="spinner" /> Indexing...</span> : <>Drop PDFs, filings, transcripts<br /><span className="small mono">or browse</span></>}
        <input ref={input} type="file" accept="application/pdf" multiple hidden onChange={(e) => e.target.files && up.run(e.target.files)} />
      </div>
      <ErrorNotice error={up.error} />
      <div className="eyebrow" style={{ margin: "6px 0" }}>Library · {selected.length} in scope</div>
      {documents.length === 0 && <p className="muted small">No documents yet. Uploads live only for this session.</p>}
      {documents.map((d) => (
        <div key={d.id} className={`doc${selected.includes(d.id) ? " on" : ""}`} onClick={() => pick(d.id)}>
          <span className="check" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="t">{d.name}</div>
            <div className="muted small mono">{d.pages} pp</div>
          </div>
          <button className="btn sm" title="Remove" onClick={(e) => { e.stopPropagation(); removeDocument(d.id); }}>×</button>
        </div>
      ))}
    </div>
  );
}
