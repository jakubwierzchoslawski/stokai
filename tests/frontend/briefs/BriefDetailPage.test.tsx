/**
 * Tests for BriefDetailPage and SafeHtmlRenderer (PLAN-F-026 TASK-006).
 *
 * TDD — written before implementation.
 * Covers AC-001 (confidence in header, not tooltip) and AC-004 (low_sample disclaimer).
 */
import React from 'react';
import { render, screen } from '@testing-library/react';

// ── Mock react-router-dom ─────────────────────────────────────────────────────
jest.mock('react-router-dom', () => ({
  useParams: () => ({ brief_id: 'test-brief-id-123' }),
  useNavigate: () => jest.fn(),
}));

// ── Mock useBriefDetail ───────────────────────────────────────────────────────
jest.mock('../../../src/frontend/features/briefs/hooks/useBriefDetail', () => ({
  useBriefDetail: jest.fn(),
}));

// ── Mock FeedbackWidget ───────────────────────────────────────────────────────
jest.mock('../../../src/frontend/features/briefs/FeedbackWidget', () => ({
  FeedbackWidget: () => <div data-testid="feedback-widget-mock" />,
}));

import { useBriefDetail } from '../../../src/frontend/features/briefs/hooks/useBriefDetail';
import { BriefDetailPage } from '../../../src/frontend/features/briefs/BriefDetailPage';
import { SafeHtmlRenderer } from '../../../src/frontend/features/briefs/SafeHtmlRenderer';

const mockUseBriefDetail = useBriefDetail as jest.Mock;

function makeMockBrief(overrides: Record<string, unknown> = {}) {
  return {
    brief_id: 'test-brief-id-123',
    type: 'morning_brief' as const,
    date: '2026-06-01T08:00:00Z',
    headline: 'Global Markets Update',
    confidence: 0.82,
    sample_size: 10,
    low_sample: false,
    content_html: '<p>This is the brief content.</p>',
    delivery_status: 'COMPLETED',
    ...overrides,
  };
}

// ── BriefDetailPage tests ─────────────────────────────────────────────────────

describe('BriefDetailPage', () => {
  it('test_confidence_rendered_in_header_not_tooltip', () => {
    // AC-001: confidence must appear prominently in header, not in tooltip
    mockUseBriefDetail.mockReturnValue({
      data: { data: makeMockBrief({ confidence: 0.82 }) },
      isLoading: false,
      isError: false,
    });

    render(<BriefDetailPage />);

    // Confidence value must be present
    const confidenceEl = screen.getByTestId('brief-confidence');
    expect(confidenceEl).toBeInTheDocument();
    expect(confidenceEl).toHaveTextContent('82%');

    // Must NOT have a title attribute (tooltip pattern)
    expect(confidenceEl).not.toHaveAttribute('title');

    // Must be inside the header section
    const header = document.querySelector('.brief-detail__header');
    expect(header).not.toBeNull();
    expect(header!.contains(confidenceEl)).toBe(true);
  });

  it('test_low_sample_disclaimer_visible_in_body_when_low_sample_true', () => {
    // AC-004: disclaimer must appear in body when low_sample is true
    mockUseBriefDetail.mockReturnValue({
      data: { data: makeMockBrief({ low_sample: true, sample_size: 3 }) },
      isLoading: false,
      isError: false,
    });

    render(<BriefDetailPage />);

    const disclaimer = screen.getByTestId('low-sample-disclaimer');
    expect(disclaimer).toBeInTheDocument();
    expect(disclaimer).toHaveTextContent('small historical sample');

    // Disclaimer must appear before the feedback widget
    const body = screen.getByTestId('brief-body');
    const feedbackSection = screen.getByTestId('feedback-section');
    expect(body).toBeInTheDocument();
    expect(feedbackSection).toBeInTheDocument();
    // Disclaimer is inside body, which comes before feedback section in DOM
    expect(body.contains(disclaimer)).toBe(true);
  });

  it('test_low_sample_disclaimer_absent_when_low_sample_false', () => {
    // AC-004: disclaimer must NOT appear when low_sample is false
    mockUseBriefDetail.mockReturnValue({
      data: { data: makeMockBrief({ low_sample: false, sample_size: 10 }) },
      isLoading: false,
      isError: false,
    });

    render(<BriefDetailPage />);

    expect(screen.queryByTestId('low-sample-disclaimer')).not.toBeInTheDocument();
  });
});

// ── SafeHtmlRenderer tests ────────────────────────────────────────────────────

describe('SafeHtmlRenderer', () => {
  it('test_safe_html_renderer_strips_script_tags', () => {
    const htmlWithScript = '<p>Safe content</p><script>alert(1)</script>';

    render(<SafeHtmlRenderer html={htmlWithScript} />);

    const container = screen.getByTestId('safe-html-renderer');
    // Script tag must not be in the rendered DOM
    const scripts = container.querySelectorAll('script');
    expect(scripts.length).toBe(0);
    // Paragraph content should still be present
    expect(container.textContent).toContain('Safe content');
  });
});
