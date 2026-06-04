/**
 * BriefDetailPage — full brief detail view.
 *
 * Header block: type label, date, confidence (large, colour-coded badge — NOT tooltip/footnote),
 * sample size.
 *
 * When brief.low_sample === true, renders an inline disclaimer BEFORE the HTML content.
 *
 * SafeHtmlRenderer sanitizes content_html via DOMPurify.
 *
 * PLAN-F-026 TASK-006
 */
import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useBriefDetail } from './hooks/useBriefDetail';
import { SafeHtmlRenderer } from './SafeHtmlRenderer';
import { FeedbackWidget } from './FeedbackWidget';
import { BRIEF_TYPE_LABELS } from './briefs.types';

const LOW_SAMPLE_DISCLAIMER =
  'Based on a small historical sample (fewer than 5 analogies) — treat this analysis with additional caution.';

function confidenceClass(confidence: number): string {
  if (confidence >= 0.7) return 'brief-detail__confidence--green';
  if (confidence >= 0.4) return 'brief-detail__confidence--amber';
  return 'brief-detail__confidence--red';
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-GB', { year: 'numeric', month: 'long', day: 'numeric' });
}

export function BriefDetailPage(): React.ReactElement {
  const { brief_id: briefId } = useParams<{ brief_id: string }>();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useBriefDetail(briefId ?? '');

  if (isLoading) {
    return <div data-testid="brief-detail-loading">Loading brief...</div>;
  }

  if (isError || !data) {
    return (
      <div data-testid="brief-detail-error" className="brief-detail__error">
        Failed to load brief. <button onClick={() => navigate(-1)}>Go back</button>
      </div>
    );
  }

  const brief = data.data;
  const confidencePct = `${Math.round(brief.confidence * 100)}%`;

  return (
    <article className="brief-detail" data-testid="brief-detail">
      {/* Header block — confidence must appear here prominently (AC-001) */}
      <header className="brief-detail__header" role="heading" aria-level={1}>
        <div className="brief-detail__meta">
          <span className="brief-detail__type-label" data-testid="brief-type-label">
            {BRIEF_TYPE_LABELS[brief.type]}
          </span>
          <span className="brief-detail__date" data-testid="brief-date">
            {formatDate(brief.date)}
          </span>
          <span className="brief-detail__sample-size" data-testid="brief-sample-size">
            Sample size: {brief.sample_size}
          </span>
        </div>

        <h1 className="brief-detail__headline" data-testid="brief-headline">
          {brief.headline}
        </h1>

        {/* Confidence displayed prominently in header — NOT in tooltip or footnote (AC-001) */}
        <div
          className={`brief-detail__confidence ${confidenceClass(brief.confidence)}`}
          data-testid="brief-confidence"
          aria-label={`Confidence: ${confidencePct}`}
        >
          <span className="brief-detail__confidence-label">Confidence</span>
          <span className="brief-detail__confidence-value">{confidencePct}</span>
        </div>
      </header>

      {/* Content body */}
      <section className="brief-detail__body" data-testid="brief-body">
        {/* Low sample disclaimer — inline before content, not in footer (AC-004) */}
        {brief.low_sample && (
          <div
            className="brief-detail__low-sample-disclaimer"
            role="alert"
            data-testid="low-sample-disclaimer"
          >
            {LOW_SAMPLE_DISCLAIMER}
          </div>
        )}

        <SafeHtmlRenderer
          html={brief.content_html}
          className="brief-detail__content"
        />
      </section>

      {/* Feedback widget — appears after content */}
      <section className="brief-detail__feedback" data-testid="feedback-section">
        <FeedbackWidget briefId={brief.brief_id} />
      </section>
    </article>
  );
}

export default BriefDetailPage;
