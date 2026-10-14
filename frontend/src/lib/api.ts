import { createSSEParser } from "./sse";
import type {
  AccessConfig, AnalysisParams, AnalysisResponse, ChatResponse, CompareMemo, DocumentInfo, Health, ModelsCatalog,
  PageContent, ResearchEvent, ResearchResult, StrategyParams, StrategyResponse, TaskInfo,
} from "./types";
import { DEFAULT_ACCESS } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public retryAfter?: number) {
    super(message);
  }
}

/** FastAPI errors are `{detail: string | {code, message} | [{msg, loc}]}`. */
export function parseError(status: number, body: unknown, retryAfter?: string | null): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  const retry = retryAfter ? Number(retryAfter) : undefined;
  if (typeof detail === "string") return new ApiError(status, `http_${status}`, detail, retry);
  if (detail && typeof detail === "object" && !Array.isArray(detail) && "code" in detail) {
    const d = detail as { code: string; message?: string };
    return new ApiError(status, d.code, d.message ?? d.code, retry);
  }
  if (Array.isArray(detail)) {
    const msg = detail.map((e: { msg?: string; loc?: unknown[] }) => `${(e.loc ?? []).slice(1).join(".")}: ${e.msg}`).join("; ");
    return new ApiError(status, "validation_error", msg, retry);
  }
  return new ApiError(status, `http_${status}`, `Request failed (${status})`, retry);
}

/** BYOK key/provider/model headers (or the chosen free model). Nothing is sent for the default free tier. */
export function accessHeaders(a: AccessConfig): Record<string, string> {
  if (a.mode === "byok" && a.apiKey) {
    const h: Record<string, string> = { "X-LLM-Provider": a.provider, "X-LLM-Api-Key": a.apiKey };
    if (a.model) h["X-LLM-Model"] = a.model;
    return h;
  }
  if (a.mode === "free" && a.freeModel.includes(":")) {
    const [provider, ...rest] = a.freeModel.split(":");
    return { "X-LLM-Provider": provider, "X-LLM-Model": rest.join(":") };
  }
  return {};
}

export class ApiClient {
  sessionId: string | null = null;
  access: AccessConfig = DEFAULT_ACCESS;
  /** Called when the backend says the session is gone; must return a new session id. */
  onSessionExpired: (() => Promise<string>) | null = null;

  constructor(private baseUrl = API_URL, private fetchImpl: typeof fetch = (...a) => fetch(...a)) {}

  private headers(extra: Record<string, string> = {}, session = true): Record<string, string> {
    return {
      ...(session && this.sessionId ? { "X-Session-Id": this.sessionId } : {}),
      ...accessHeaders(this.access),
      ...extra,
    };
  }

  private async send<T>(path: string, init: RequestInit & { session?: boolean } = {}, retried = false): Promise<T> {
    const { session = true, headers, ...rest } = init;
    const res = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...rest, headers: this.headers(headers as Record<string, string>, session),
    });
    if (res.ok) return (res.status === 204 ? undefined : await res.json()) as T;
    const err = parseError(res.status, await res.json().catch(() => null), res.headers.get("Retry-After"));
    if (err.code === "invalid_session" && !retried && this.onSessionExpired) {
      this.sessionId = await this.onSessionExpired();
      return this.send<T>(path, init, true);
    }
    throw err;
  }

  private json<T>(path: string, body: unknown): Promise<T> {
    return this.send<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  createSession = () => this.send<{ session_id: string; expires_at: number }>("/sessions", { method: "POST", session: false });
  endSession = (id: string) => this.send<void>(`/sessions/${id}`, { method: "DELETE" });
  health = () => this.send<Health>("/health", { session: false });
  models = () => this.send<ModelsCatalog>("/models", { session: false });
  tasks = () => this.send<TaskInfo[]>("/tasks", { session: false });
  validateKey = () => this.send<{ ok: boolean }>("/models/validate", { method: "POST", session: false });

  listDocuments = () => this.send<DocumentInfo[]>("/documents");
  deleteDocument = (id: string) => this.send<void>(`/documents/${id}`, { method: "DELETE" });
  getPage = (id: string, page: number) => this.send<PageContent>(`/documents/${id}/pages/${page}`);
  uploadDocument(file: File, name?: string) {
    const form = new FormData();
    form.append("file", file);
    return this.send<DocumentInfo>(`/documents${name ? `?name=${encodeURIComponent(name)}` : ""}`, { method: "POST", body: form });
  }

  chat = (question: string, document_ids: string[], top_k?: number) =>
    this.json<ChatResponse>("/chat", { question, document_ids, ...(top_k ? { top_k } : {}) });
  analysis = (params: AnalysisParams) => this.json<AnalysisResponse>("/analysis", params);
  strategy = (params: StrategyParams) => this.json<StrategyResponse>("/strategy", params);
  compare = (document_id_a: string, document_id_b: string) => this.json<CompareMemo>("/compare", { document_id_a, document_id_b });
  research = (topic: string) => this.json<ResearchResult>("/research", { topic });

  /** POST + Server-Sent Events (EventSource can't send POST bodies or headers). */
  async researchStream(topic: string, onEvent: (e: ResearchEvent) => void, signal?: AbortSignal): Promise<void> {
    const res = await this.fetchImpl(`${this.baseUrl}/research/stream`, {
      method: "POST", signal, body: JSON.stringify({ topic }),
      headers: this.headers({ "Content-Type": "application/json", Accept: "text/event-stream" }, false),
    });
    if (!res.ok || !res.body) throw parseError(res.status, await res.json().catch(() => null), res.headers.get("Retry-After"));
    const parse = createSSEParser((m) => onEvent(JSON.parse(m.data) as ResearchEvent));
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parse(decoder.decode(value, { stream: true }));
    }
  }
}

export const client = new ApiClient();
