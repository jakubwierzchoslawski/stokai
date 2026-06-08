import { describe, it, expect, vi, afterEach } from 'vitest';
/**
 * Tests for AnalyzeNowButton component.
 *
 * Tests:
 * - Shows "Analyze Now" text in default state
 * - Shows "Analyzing..." when loading
 * - Button is disabled when loading
 * - Clicking triggers the analysis
 * - Shows error when 409
 *
 * PLAN-F-023 TASK-006
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AnalyzeNowButton } from '../../../src/frontend/pages/CompanyDetail/AnalyzeNowButton';

const COMPANY_ID = 'c1c1c1c1-0000-0000-0000-000000000001';
const RUN_ID = 'run-xyz-999';

// â”€â”€ WebSocket mock â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closeCalled = false;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.closeCalled = true;
  }

  simulateMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent);
    }
  }
}

function setupFetch(options: { status?: number } = {}) {
  const { status = 202 } = options;
  MockWebSocket.instances = [];
  (global as unknown as { WebSocket: unknown }).WebSocket = MockWebSocket;

  global.fetch = vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    json: async () => ({
      data: { run_id: RUN_ID, company_id: COMPANY_ID, status: 'queued' },
      meta: {},
      error: null,
    }),
  } as Response);

  Object.defineProperty(window, 'location', {
    writable: true,
    value: { protocol: 'http:', host: 'localhost:3000' },
  });
}

afterEach(() => {
  vi.resetAllMocks();
  MockWebSocket.instances = [];
});

describe('AnalyzeNowButton', () => {
  it('renders "Analyze Now" text in default state', () => {
    setupFetch();
    render(<AnalyzeNowButton companyId={COMPANY_ID} />);
    expect(screen.getByTestId('analyze-now-btn')).toHaveTextContent('Analyze Now');
  });

  it('button is enabled in default state', () => {
    setupFetch();
    render(<AnalyzeNowButton companyId={COMPANY_ID} />);
    expect(screen.getByTestId('analyze-now-btn')).not.toBeDisabled();
  });

  it('shows "Analyzing..." when loading', async () => {
    setupFetch();
    render(<AnalyzeNowButton companyId={COMPANY_ID} />);

    fireEvent.click(screen.getByTestId('analyze-now-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('analyze-now-btn')).toHaveTextContent('Analyzing...');
    });
  });

  it('button is disabled when loading', async () => {
    setupFetch();
    render(<AnalyzeNowButton companyId={COMPANY_ID} />);

    fireEvent.click(screen.getByTestId('analyze-now-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('analyze-now-btn')).toBeDisabled();
    });
  });

  it('clicking triggers POST to analysis endpoint', async () => {
    setupFetch();
    render(<AnalyzeNowButton companyId={COMPANY_ID} />);

    fireEvent.click(screen.getByTestId('analyze-now-btn'));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        `/api/v1/companies/${COMPANY_ID}/analysis`,
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('shows error message on 409 without entering loading state', async () => {
    setupFetch({ status: 409 });
    render(<AnalyzeNowButton companyId={COMPANY_ID} />);

    fireEvent.click(screen.getByTestId('analyze-now-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('analyze-now-error')).toBeInTheDocument();
    });

    // Should not be in loading state
    expect(screen.getByTestId('analyze-now-btn')).toHaveTextContent('Analyze Now');
    expect(screen.getByTestId('analyze-now-btn')).not.toBeDisabled();
  });

  it('calls onReportReady when analysis COMPLETED', async () => {
    setupFetch();
    const onReportReady = vi.fn();
    render(<AnalyzeNowButton companyId={COMPANY_ID} onReportReady={onReportReady} />);

    fireEvent.click(screen.getByTestId('analyze-now-btn'));

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));

    // Simulate COMPLETED event
    fireEvent(document, new CustomEvent('test')); // trigger event loop
    MockWebSocket.instances[0].simulateMessage({ type: 'COMPLETED' });

    await waitFor(() => expect(onReportReady).toHaveBeenCalledWith(RUN_ID));
  });
});
