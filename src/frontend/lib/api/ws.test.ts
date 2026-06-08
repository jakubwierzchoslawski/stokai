import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiSocket } from "./ws";
import { setAccessToken, clearAccessToken } from "./client";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  close(_code?: number) { this.onclose?.(new CloseEvent("close", { code: _code ?? 1000 })); }
  send(_: string) {}
}

beforeEach(() => {
  MockWebSocket.instances = [];
  clearAccessToken();
  vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
});

describe("apiSocket", () => {
  it("appends token query param when access token is set", () => {
    setAccessToken("tok_ws");
    apiSocket("/events/feed", { onMessage: () => {}, onClose: () => {} });
    expect(MockWebSocket.instances[0].url).toContain("token=tok_ws");
  });

  it("calls onMessage with parsed JSON frames", () => {
    const messages: unknown[] = [];
    apiSocket("/events/feed", {
      onMessage: (m) => messages.push(m),
      onClose: () => {},
    });
    const ws = MockWebSocket.instances[0];
    ws.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "ping" }) }));
    expect(messages).toEqual([{ type: "ping" }]);
  });
});
