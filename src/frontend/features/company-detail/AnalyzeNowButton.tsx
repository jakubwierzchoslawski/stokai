/**
 * AnalyzeNowButton — triggers on-demand AI analysis for a company.
 *
 * States:
 *   - Default: "Analyze Now" button enabled
 *   - Loading: "Analyzing..." button disabled
 *   - Error: error message shown below button
 *
 * PLAN-F-023 TASK-006
 */
import React from 'react';
import { useAnalyzeNow } from './hooks/useAnalyzeNow';

export interface AnalyzeNowButtonProps {
  companyId: string;
  onReportReady?: (runId: string) => void;
}

export function AnalyzeNowButton({
  companyId,
  onReportReady,
}: AnalyzeNowButtonProps): React.ReactElement {
  const { trigger, isLoading, error } = useAnalyzeNow({
    companyId,
    onReportReady,
  });

  function handleClick() {
    trigger().catch((err: unknown) => {
      console.error('Analysis trigger failed:', err);
    });
  }

  return (
    <div className="analyze-now" data-testid="analyze-now">
      <button
        className="analyze-now__btn"
        onClick={handleClick}
        disabled={isLoading}
        aria-busy={isLoading}
        aria-label={isLoading ? 'Analysis in progress' : 'Analyze Now'}
        data-testid="analyze-now-btn"
      >
        {isLoading ? 'Analyzing...' : 'Analyze Now'}
      </button>
      {error && (
        <p
          className="analyze-now__error"
          role="alert"
          data-testid="analyze-now-error"
        >
          {error}
        </p>
      )}
    </div>
  );
}
