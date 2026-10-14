export interface SSEMessage {
  event: string;
  data: string;
}

/** Incremental Server-Sent-Events parser. Handles \r\n (sse-starlette), split chunks, comments and multi-line data. */
export function createSSEParser(onMessage: (m: SSEMessage) => void): (chunk: string) => void {
  let buffer = "";
  return (chunk: string) => {
    buffer += chunk;
    let held = "";
    if (buffer.endsWith("\r")) {
      held = "\r"; // may be the first half of \r\n; wait for the next chunk
      buffer = buffer.slice(0, -1);
    }
    buffer = buffer.replace(/\r\n|\r/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = (blocks.pop() ?? "") + held;
    for (const block of blocks) {
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (!line || line.startsWith(":")) continue;
        const idx = line.indexOf(":");
        const field = idx === -1 ? line : line.slice(0, idx);
        const value = idx === -1 ? "" : line.slice(idx + 1).replace(/^ /, "");
        if (field === "event") event = value;
        else if (field === "data") data.push(value);
      }
      if (data.length) onMessage({ event, data: data.join("\n") });
    }
  };
}
