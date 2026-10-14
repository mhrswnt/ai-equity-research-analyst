"use client";
import { ApiError } from "@/lib/api";
import { useApp } from "@/lib/store";

export function ErrorNotice({ error }: { error: Error | null }) {
  const { openAccess } = useApp();
  if (!error) return null;
  const api = error instanceof ApiError ? error : null;
  const needsKey = api?.code === "byok_required";
  return (
    <div className={`notice${needsKey ? " info" : ""}`} role="alert">
      <span>
        {needsKey ? "This task needs a stronger model: add your own API key. " : ""}
        {api?.code === "rate_limited" && api.retryAfter ? `${api.message} Try again in ~${Math.ceil(api.retryAfter / 60)} min.` : error.message}
      </span>
      {(needsKey || api?.code === "model_not_free" || api?.code === "invalid_key") && (
        <button className="btn sm" onClick={() => openAccess(true)}>Model access</button>
      )}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <span className="muted small"><span className="spinner" /> {label}</span>;
}
