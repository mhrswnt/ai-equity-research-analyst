import { describe, expect, it, vi } from "vitest";
import { ApiClient, accessHeaders, parseError } from "./api";
import { createSSEParser } from "./sse";
import { DEFAULT_ACCESS } from "./types";

describe("parseError", () => {
  it("reads {code, message} details and Retry-After", () => {
    const e = parseError(429, { detail: { code: "rate_limited", message: "slow down" } }, "42");
    expect([e.status, e.code, e.message, e.retryAfter]).toEqual([429, "rate_limited", "slow down", 42]);
  });
  it("handles string, validation-list and empty bodies", () => {
    expect(parseError(404, { detail: "Document not found" }).message).toBe("Document not found");
    expect(parseError(422, { detail: [{ loc: ["body", "tickers"], msg: "field required" }] }).message).toBe("tickers: field required");
    expect(parseError(500, null).code).toBe("http_500");
  });
});

describe("accessHeaders", () => {
  it("sends nothing for the default free tier", () => expect(accessHeaders(DEFAULT_ACCESS)).toEqual({}));
  it("sends the chosen free model without a key", () => {
    expect(accessHeaders({ ...DEFAULT_ACCESS, freeModel: "groq:qwen/qwen3.8-27b" })).toEqual({
      "X-LLM-Provider": "groq", "X-LLM-Model": "qwen/qwen3.8-27b",
    });
  });
  it("sends the BYOK key headers", () => {
    const h = accessHeaders({ ...DEFAULT_ACCESS, mode: "byok", apiKey: "k", provider: "anthropic", model: "m" });
    expect(h).toEqual({ "X-LLM-Provider": "anthropic", "X-LLM-Api-Key": "k", "X-LLM-Model": "m" });
    expect(accessHeaders({ ...DEFAULT_ACCESS, mode: "byok", apiKey: "" })).toEqual({});
  });
});

describe("createSSEParser", () => {
  it("parses \\r\\n frames split across chunks, comments and multi-line data", () => {
    const got: unknown[] = [];
    const feed = createSSEParser((m) => got.push(m));
    feed(": ping\r\n\r\nevent: agent\r\ndata: {\"a\"");
    feed(":1}\r");
    feed("\n\r\nevent: result\ndata: l1\ndata: l2\n\n");
    expect(got).toEqual([{ event: "agent", data: '{"a":1}' }, { event: "result", data: "l1\nl2" }]);
  });
});

describe("ApiClient", () => {
  const ok = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });

  it("sends session + access headers and renews an expired session once", async () => {
    const calls: Array<Record<string, string>> = [];
    const fetchImpl = vi.fn(async (_url: string, init: RequestInit) => {
      calls.push(init.headers as Record<string, string>);
      return calls.length === 1 ? ok({ detail: { code: "invalid_session", message: "x" } }, 401) : ok([]);
    });
    const c = new ApiClient("http://api", fetchImpl as unknown as typeof fetch);
    c.sessionId = "old";
    c.access = { ...DEFAULT_ACCESS, mode: "byok", apiKey: "secret-key", provider: "groq" };
    c.onSessionExpired = async () => "new";
    expect(await c.listDocuments()).toEqual([]);
    expect(calls[0]["X-Session-Id"]).toBe("old");
    expect(calls[1]["X-Session-Id"]).toBe("new");
    expect(calls[1]["X-LLM-Api-Key"]).toBe("secret-key");
  });

  it("throws ApiError and does not loop on repeated 401", async () => {
    const fetchImpl = vi.fn(async () => ok({ detail: { code: "invalid_session", message: "gone" } }, 401));
    const c = new ApiClient("http://api", fetchImpl as unknown as typeof fetch);
    c.onSessionExpired = async () => "s2";
    await expect(c.listDocuments()).rejects.toMatchObject({ status: 401, code: "invalid_session" });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("streams research events from an SSE body", async () => {
    const body = new ReadableStream({
      start(ctrl) {
        const enc = new TextEncoder();
        ctrl.enqueue(enc.encode('event: agent\r\ndata: {"type":"agent","agent":"ResearchAgent"}\r\n\r\n'));
        ctrl.enqueue(enc.encode('event: result\r\ndata: {"type":"result","report_content":"R","review":"V","research_notes":{}}\r\n\r\n'));
        ctrl.close();
      },
    });
    const fetchImpl = vi.fn(async () => new Response(body, { status: 200 }));
    const c = new ApiClient("http://api", fetchImpl as unknown as typeof fetch);
    const events: string[] = [];
    await c.researchStream("topic", (e) => events.push(e.type));
    expect(events).toEqual(["agent", "result"]);
  });

  it("rejects a failed stream with the backend error", async () => {
    const fetchImpl = vi.fn(async () => ok({ detail: { code: "byok_required", message: "need key" } }, 402));
    const c = new ApiClient("http://api", fetchImpl as unknown as typeof fetch);
    await expect(c.researchStream("t", () => {})).rejects.toMatchObject({ code: "byok_required" });
  });
});
