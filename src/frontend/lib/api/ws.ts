import { env } from "../env";
import { getAccessToken } from "./client";

export interface SocketHandlers {
  onMessage: (msg: unknown) => void;
  onClose: (ev: CloseEvent) => void;
  onError?: (ev: Event) => void;
}

export interface SocketHandle {
  close: () => void;
}

export function apiSocket(path: string, h: SocketHandlers): SocketHandle {
  const base =
    env.wsBaseUrl ||
    (typeof window !== "undefined"
      ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
      : "");
  const token = getAccessToken();
  const separator = path.includes("?") ? "&" : "?";
  const url =
    base + (path.startsWith("/") ? path : `/${path}`) +
    (token ? `${separator}token=${encodeURIComponent(token)}` : "");

  const ws = new WebSocket(url);

  ws.onmessage = (event: MessageEvent) => {
    try {
      h.onMessage(JSON.parse(event.data as string));
    } catch {
      h.onMessage(event.data);
    }
  };
  ws.onclose = (event: CloseEvent) => h.onClose(event);
  if (h.onError) ws.onerror = (event: Event) => h.onError?.(event);

  return { close: () => ws.close() };
}
