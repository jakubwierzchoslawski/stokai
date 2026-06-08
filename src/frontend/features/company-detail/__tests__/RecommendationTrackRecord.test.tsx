import { describe, it, expect, vi, beforeEach } from 'vitest';
/**
 * Tests for RecommendationTrackRecord component â€” TDD for TASK-005.
 *
 * PLAN-N-012 AC-001, AC-003
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { RecommendationTrackRecord } from '../RecommendationTrackRecord';

// Mock the hook
vi.mock('../hooks/useRecommendationTrackRecord', () => ({
  useRecommendationTrackRecord: vi.fn(),
  trackRecordQueryKey: vi.fn().mockReturnValue(['track-record', 'test-id']),
}));
import { useRecommendationTrackRecord as _useRecommendationTrackRecord } from '../hooks/useRecommendationTrackRecord';
const useRecommendationTrackRecord = vi.mocked(_useRecommendationTrackRecord);


function makeEntry(overrides: Partial<{
  rec_id: string;
  company_ticker: string;
  action_signal: string;
  confidence: number;
  sample_size: number;
  generated_at: string;
  actual_t1d: number | null;
  actual_t1w: number | null;
  accuracy: number | null;
  disclaimer_required: boolean;
}> = {}) {
  return {
    rec_id: overrides.rec_id ?? 'rec-uuid-1',
    company_ticker: overrides.company_ticker ?? 'AAPL',
    action_signal: overrides.action_signal ?? 'BUY_OPP',
    confidence: overrides.confidence ?? 0.8,
    sample_size: overrides.sample_size ?? 10,
    generated_at: overrides.generated_at ?? '2025-01-15T10:00:00Z',
    actual_t1d: overrides.actual_t1d ?? null,
    actual_t1w: overrides.actual_t1w ?? null,
    accuracy: overrides.accuracy ?? null,
    disclaimer_required: overrides.disclaimer_required ?? false,
  };
}

function makeResponse(overrides: {
  entries?: ReturnType<typeof makeEntry>[];
  direction_correct_t1d_pct?: number | null;
  direction_correct_t1w_pct?: number | null;
  total?: number;
} = {}) {
  const entries = overrides.entries ?? [];
  return {
    company_id: 'company-uuid-1',
    company_ticker: 'AAPL',
    entries,
    total: overrides.total ?? entries.length,
    direction_correct_t1d_pct: overrides.direction_correct_t1d_pct ?? null,
    direction_correct_t1w_pct: overrides.direction_correct_t1w_pct ?? null,
  };
}

describe('RecommendationTrackRecord', () => {
  const COMPANY_ID = 'company-uuid-1';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the summary row with correct T+1d percentage when actuals are present', () => {
    useRecommendationTrackRecord.mockReturnValue({
      data: makeResponse({
        entries: [makeEntry()],
        direction_correct_t1d_pct: 75.0,
        direction_correct_t1w_pct: 60.0,
      }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<RecommendationTrackRecord companyId={COMPANY_ID} />);

    expect(screen.getByTestId('direction-t1d')).toHaveTextContent('75.0%');
  });

  it('renders em dash for T+1d and T+1w when direction_correct_pct is null', () => {
    useRecommendationTrackRecord.mockReturnValue({
      data: makeResponse({
        entries: [],
        direction_correct_t1d_pct: null,
        direction_correct_t1w_pct: null,
      }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<RecommendationTrackRecord companyId={COMPANY_ID} />);

    // em dash is rendered as "â€”"
    const t1dEl = screen.getByTestId('direction-t1d');
    const t1wEl = screen.getByTestId('direction-t1w');
    expect(t1dEl.textContent).toBe('â€”');
    expect(t1wEl.textContent).toBe('â€”');
  });

  it('renders a table row for each TrackRecordEntry', () => {
    const entries = [
      makeEntry({ rec_id: 'r1' }),
      makeEntry({ rec_id: 'r2' }),
      makeEntry({ rec_id: 'r3' }),
    ];
    useRecommendationTrackRecord.mockReturnValue({
      data: makeResponse({ entries }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<RecommendationTrackRecord companyId={COMPANY_ID} />);

    const rows = screen.getAllByTestId('track-record-row');
    expect(rows).toHaveLength(3);
  });

  it('renders warning icon with disclaimer text when disclaimer_required is true', () => {
    useRecommendationTrackRecord.mockReturnValue({
      data: makeResponse({
        entries: [makeEntry({ disclaimer_required: true, sample_size: 2 })],
      }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<RecommendationTrackRecord companyId={COMPANY_ID} />);

    const icon = screen.getByTestId('disclaimer-icon');
    expect(icon).toBeTruthy();
    // Disclaimer text accessible via title attribute (AC-003)
    expect(icon.getAttribute('title')).toContain('fewer than 5');
  });

  it('does not render a warning icon when disclaimer_required is false', () => {
    useRecommendationTrackRecord.mockReturnValue({
      data: makeResponse({
        entries: [makeEntry({ disclaimer_required: false, sample_size: 10 })],
      }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<RecommendationTrackRecord companyId={COMPANY_ID} />);

    expect(screen.queryByTestId('disclaimer-icon')).toBeNull();
  });

  it('renders the empty state message when entries is empty', () => {
    useRecommendationTrackRecord.mockReturnValue({
      data: makeResponse({ entries: [] }),
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<RecommendationTrackRecord companyId={COMPANY_ID} />);

    expect(screen.getByTestId('track-record-empty')).toHaveTextContent(
      'No recommendations recorded yet for this company.'
    );
  });

  it('renders skeleton rows during loading', () => {
    useRecommendationTrackRecord.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    });

    render(<RecommendationTrackRecord companyId={COMPANY_ID} />);

    const skeletonRows = screen.getAllByTestId('skeleton-row');
    expect(skeletonRows.length).toBeGreaterThan(0);
  });

  it('renders error state when isError is true', () => {
    useRecommendationTrackRecord.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    });

    render(<RecommendationTrackRecord companyId={COMPANY_ID} />);

    expect(screen.getByTestId('track-record-error')).toBeTruthy();
    expect(screen.getByText(/Could not load track record/)).toBeTruthy();
  });
});
