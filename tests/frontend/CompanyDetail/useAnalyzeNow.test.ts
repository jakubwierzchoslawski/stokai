/**
 * Unit tests for useAnalyzeNow hook.
 *
 * Tests:
 * - triggers POST to correct endpoint
 * - isLoading=true after trigger (before WS COMPLETED)
 * - subscribes to WebSocket with run_id
 * - calls onReportReady on COMPLETED message
 * - isLoading=false after COMPLETED
 * - 409 sets error without loading
 * - cleanup on unmount
 *
 * PLAN-F-023 TASK-006
 */
import { renderHook, act, waitFor } from '@testing-library/react';
import { useAnalyzeNow } from '../../../src/frontend/pages/CompanyDetail/hooks/useAnalyzeNow';

const COMPANY_ID = 'c1c1c1c1-0000-0000-0000-000000000001';
const RUN_ID = 'run-abc-123';

// ── WebSocket mock ─────────────────────────────────────────────────────────────

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  readyState = WebSocket.CONNECTING;
  closeCalled = false;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.closeCalled = true;
  }

  // Helper to simulate incoming message
  simulateMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent);
    }
  }
}

function setupMocks(options: {
  status?: number;
  responseBody?: unknown;
} = {}) {
  const { status = 202, responseBody = { data: { run_id: RUN_ID }, meta: {}, error: null } } = options;

  MockWebSocket.instances = [];
  (global as unknown as { WebSocket: unknown }).WebSocket = MockWebSocket;

  global.fetch = jest.fn().mockResolvedValue({
    ok: status < 400,
    status,
    json: async () => responseBody,
  } as Response);

  // Mock window.location
  Object.defineProperty(window, 'location', {
    writable: true,
    value: { protocol: 'http:', host: 'localhost:3000' },
  });
}

afterEach(() => {
  jest.resetAllMocks();
  MockWebSocket.instances = [];
});

describe('useAnalyzeNow', () => {
  it('triggers POST to the analysis endpoint', async () => {
    setupMocks();
    const { result } = renderHook(() =>
      useAnalyzeNow({ companyId: COMPANY_ID }),
    );

    await act(async () => {
      await result.current.trigger();
    });

    expect(global.fetch).toHaveBeenCalledWith(
      `/api/v1/companies/${COMPANY_ID}/analysis`,
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('sets isLoading=true after trigger', async () => {
    setupMocks();
    const { result } = renderHook(() =>
      useAnalyzeNow({ companyId: COMPANY_ID }),
    );

    await act(async () => {
      await result.current.trigger();
    });

    expect(result.current.isLoading).toBe(true);
  });

  it('subscribes to WebSocket with the run_id', async () => {
    setupMocks();
    const { result } = renderHook(() =>
      useAnalyzeNow({ companyId: COMPANY_ID }),
    );

    await act(async () => {
      await result.current.trigger();
    });

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain(RUN_ID);
  });

  it('calls onReportReady on COMPLETED message', async () => {
    setupMocks();
    const onReportReady = jest.fn();
    const { result } = renderHook(() =>
      useAnalyzeNow({ companyId: COMPANY_ID, onReportReady }),
    );

    await act(async () => {
      await result.current.trigger();
    });

    act(() => {
      MockWebSocket.instances[0].simulateMessage({ type: 'COMPLETED' });
    });

    expect(onReportReady).toHaveBeenCalledWith(RUN_ID);
  });

  it('sets isLoading=false after COMPLETED message', async () => {
    setupMocks();
    const { result } = renderHook(() =>
      useAnalyzeNow({ companyId: COMPANY_ID }),
    );

    await act(async () => {
      await result.current.trigger();
    });

    expect(result.current.isLoading).toBe(true);

    act(() => {
      MockWebSocket.instances[0].simulateMessage({ type: 'COMPLETED' });
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  it('sets error without isLoading=true on 409 response', async () => {
    setupMocks({ status: 409 });
    const { result } = renderHook(() =>
      useAnalyzeNow({ companyId: COMPANY_ID }),
    );

    await act(async () => {
      await result.current.trigger();
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeTruthy();
  });

  it('closes WebSocket on unmount', async () => {
    setupMocks();
    const { result, unmount } = renderHook(() =>
      useAnalyzeNow({ companyId: COMPANY_ID }),
    );

    await act(async () => {
      await result.current.trigger();
    });

    const ws = MockWebSocket.instances[0];
    expect(ws.closeCalled).toBe(false);

    unmount();
    expect(ws.closeCalled).toBe(true);
  });

  it('stores run_id after successful trigger', async () => {
    setupMocks();
    const { result } = renderHook(() =>
      useAnalyzeNow({ companyId: COMPANY_ID }),
    );

    await act(async () => {
      await result.current.trigger();
    });

    expect(result.current.runId).toBe(RUN_ID);
  });
});
