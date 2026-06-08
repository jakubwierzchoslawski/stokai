import { env } from "../env";
import { getAccessToken } from "./client";

export interface StreamEvent {
  event: string;
  data: unknown;
  id?: string;
}

export interface StreamHandlers {
  onEvent: (e: StreamEvent) => void;
  onError: (err: Error) => void;
}

export interface StreamHandle {
  abort: () => void;
}

export function apiStream(path: string, h: StreamHandlers): StreamHandle {
  const ctrl = new AbortController();
  const url = env.apiBaseUrl.replace(/\/$/, "") + (path.startsWith("/") ? path : `/${path}`);

  const headers: Record<string, string> = { accept: "text/event-stream" };
  const token = getAccessToken();
  if (token) headers.authorization = `Bearer ${token}`;

  (async () => {
    try {
      const resp = await fetch(url, { headers, credentials: "include", signal: ctrl.signal });
      if (!resp.ok || !resp.body) {
        h.onError(new Error(`SSE failed: ${resp.status}`));
        return;
      }
      const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          // Flush any remaining buffered chunk as a final event.
          const trailing = buffer.trim();
          if (trailing.length > 0) {
            const evt = parseSseChunk(trailing);
            if (evt) h.onEvent(evt);
          }
          break;
        }
        buffer += value;
        let idx: number;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const chunk = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const evt = parseSseChunk(chunk);
          if (evt) h.onEvent(evt);
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        h.onError(err as Error);
      }
    }
  })();

  return { abort: () => ctrl.abort() };
}

function parseSseChunk(chunk: string): StreamEvent | null {
  const lines = chunk.split("\n");
  let event = "message";
  const dataLines: string[] = [];
  let id: string | undefined;
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    else if (line.startsWith("id:")) id = line.slice(3).trim();
  }
  if (dataLines.length === 0) return null;
  const raw = dataLines.join("\n");
  let data: unknown;
  try { data = JSON.parse(raw); } catch { data = raw; }
  return { event, data, id };
}
