/**
 * CompanyDetailPage — route /company/:companyId
 *
 * Aggregates 5 data panels from the Company Detail API endpoint:
 *   1. Price chart (OHLCV)
 *   2. Fundamentals
 *   3. Score breakdown
 *   4. Active geo-events
 *   5. AI analysis history + track record
 *
 * Includes the AnalyzeNowButton for triggering on-demand analysis.
 *
 * PLAN-F-023 TASK-005
 */
import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useCompanyDetail } from './hooks/useCompanyDetail';
import { useScoreHistory } from './hooks/useScoreHistory';
import { PriceChartPanel } from './PriceChartPanel';
import { FundamentalsPanel } from './FundamentalsPanel';
import { ScoreBreakdownPanel } from './ScoreBreakdownPanel';
import { ActiveEventsPanel } from './ActiveEventsPanel';
import { AnalysisHistoryPanel } from './AnalysisHistoryPanel';
import { TrackRecordPanel } from './TrackRecordPanel';
import { AnalyzeNowButton } from './AnalyzeNowButton';

export function CompanyDetailPage(): React.ReactElement {
  const { companyId } = useParams<{ companyId: string }>();
  const navigate = useNavigate();
  const [profileId, setProfileId] = useState<string | undefined>(undefined);
  const [priceInterval, setPriceInterval] = useState<string>('1d');

  const {
    data: detail,
    isLoading: isDetailLoading,
    isError: isDetailError,
    error: detailError,
  } = useCompanyDetail({ companyId: companyId ?? '', profileId });

  const {
    data: priceBars,
    isLoading: isPriceLoading,
  } = useScoreHistory({ companyId: companyId ?? '', interval: priceInterval });

  function handleNavigate(url: string) {
    navigate(url);
  }

  function handleAnalysisReady(runId: string) {
    // Refetch after analysis completes
    void runId;
  }

  if (!companyId) {
    return <div role="alert">Company ID is required.</div>;
  }

  if (isDetailLoading) {
    return <div data-testid="company-detail-loading">Loading company details...</div>;
  }

  if (isDetailError) {
    return (
      <div role="alert" data-testid="company-detail-error">
        Error: {detailError?.message}
      </div>
    );
  }

  if (!detail) {
    return <div role="alert" data-testid="company-not-found">Company not found.</div>;
  }

  return (
    <main className="company-detail-page" data-testid="company-detail-page">
      <header className="company-detail-page__header">
        <div className="company-detail-page__identity">
          <h1 className="company-detail-page__name" data-testid="company-name">
            {detail.name}
          </h1>
          <span className="company-detail-page__ticker" data-testid="company-ticker">
            {detail.ticker}
          </span>
          <span className="company-detail-page__sector" data-testid="company-sector">
            {detail.sector}
          </span>
          {detail.market_cap !== null && (
            <span className="company-detail-page__market-cap" data-testid="company-market-cap">
              ${(detail.market_cap / 1e9).toFixed(2)}B
            </span>
          )}
        </div>

        <div className="company-detail-page__actions">
          <label htmlFor="price-interval-select" className="company-detail-page__interval-label">
            Interval:
          </label>
          <select
            id="price-interval-select"
            value={priceInterval}
            onChange={(e) => setPriceInterval(e.target.value)}
            className="company-detail-page__interval-select"
            data-testid="price-interval-select"
          >
            <option value="15m">15m</option>
            <option value="1h">1h</option>
            <option value="1d">1d</option>
          </select>

          <label htmlFor="profile-id-input" className="company-detail-page__profile-label">
            Profile:
          </label>
          <input
            id="profile-id-input"
            type="text"
            placeholder="Default profile"
            value={profileId ?? ''}
            onChange={(e) => setProfileId(e.target.value || undefined)}
            className="company-detail-page__profile-input"
            data-testid="profile-id-input"
          />

          <AnalyzeNowButton
            companyId={companyId}
            onReportReady={handleAnalysisReady}
          />
        </div>
      </header>

      <section className="company-detail-page__price-chart" aria-label="Price Chart">
        <PriceChartPanel bars={priceBars ?? []} isLoading={isPriceLoading} />
      </section>

      <section className="company-detail-page__fundamentals" aria-label="Fundamentals">
        <FundamentalsPanel fundamentals={detail.fundamentals} />
      </section>

      <section className="company-detail-page__scores" aria-label="Score Breakdown">
        <ScoreBreakdownPanel scores={detail.scores} />
      </section>

      <section className="company-detail-page__events" aria-label="Active Geo-Events">
        <ActiveEventsPanel
          events={detail.active_events}
          onNavigate={handleNavigate}
        />
      </section>

      <section className="company-detail-page__history" aria-label="Analysis History">
        <AnalysisHistoryPanel history={detail.analysis_history} />
      </section>

      <section className="company-detail-page__track-record" aria-label="Track Record">
        <TrackRecordPanel
          trackRecord={detail.track_record}
          directionalAccuracyT1d={detail.directional_accuracy_t1d}
        />
      </section>
    </main>
  );
}

export default CompanyDetailPage;
