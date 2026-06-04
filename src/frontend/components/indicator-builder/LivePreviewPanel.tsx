/**
 * LivePreviewPanel — right panel of the Indicator Builder.
 *
 * - Table with 5 sample companies (raw_value, score, geo_adjusted).
 * - Updates within 500ms of formula edits (useLivePreview with 500ms debounce).
 * - Shows loading spinner while in-flight.
 * - Shows scores when data arrives.
 */
import React from "react";
import { useLivePreview, CompanyPreviewRow } from "./hooks/useLivePreview";

interface LivePreviewPanelProps {
  formula: string;
}

export const LivePreviewPanel: React.FC<LivePreviewPanelProps> = ({
  formula,
}) => {
  const { previews, isLoading, error } = useLivePreview(formula, {
    debounceMs: 500,
  });

  return (
    <div className="live-preview-panel" role="region" aria-label="Live Score Preview">
      <h3 className="live-preview-panel__title">Live Preview</h3>
      <p className="live-preview-panel__subtitle">
        Sample scores for 5 companies (updates within 500ms)
      </p>

      {isLoading && (
        <div
          className="live-preview-panel__loading"
          role="status"
          aria-label="Loading preview scores"
        >
          <span className="live-preview-panel__spinner" aria-hidden="true" />
          <span>Computing scores...</span>
        </div>
      )}

      {error && (
        <div className="live-preview-panel__error" role="alert">
          {error}
        </div>
      )}

      {!isLoading && previews.length > 0 && (
        <table className="live-preview-panel__table">
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">Raw Value</th>
              <th scope="col">Score (0–100)</th>
              <th scope="col">Geo Adjusted</th>
            </tr>
          </thead>
          <tbody>
            {previews.map((row) => (
              <tr key={row.company_id}>
                <td>{row.company_name}</td>
                <td>
                  {row.raw_value !== null
                    ? row.raw_value.toFixed(2)
                    : "—"}
                </td>
                <td>
                  {row.score !== null ? (
                    <span className="live-preview-panel__score">
                      {row.score.toFixed(1)}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  {row.geo_adjusted !== null
                    ? row.geo_adjusted.toFixed(1)
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!isLoading && previews.length === 0 && !error && formula.trim() && (
        <p className="live-preview-panel__empty">
          Enter a valid formula to see preview scores.
        </p>
      )}

      {!formula.trim() && (
        <p className="live-preview-panel__empty">
          Enter a formula in the editor to see live scores.
        </p>
      )}
    </div>
  );
};

export default LivePreviewPanel;
