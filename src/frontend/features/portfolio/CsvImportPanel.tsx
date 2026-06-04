/**
 * features/portfolio/CsvImportPanel — CSV import UI for portfolio positions.
 *
 * - File input accepting .csv only, max 1MB hint.
 * - POST /api/v1/portfolios/import (multipart/form-data).
 * - Success (all valid): shows "All rows imported" toast/message.
 * - Partial errors: shows per-row error list + "Download failed rows" CSV.
 * - Import button disabled during upload.
 * - After successful import: calls invalidatePortfolioContext().
 *
 * AC-003: CSV upload → valid rows create positions, invalid rows show per-row errors.
 * PLAN-F-024 TASK-010
 */
import React, { useRef, useState } from 'react';

import { usePortfolioContext } from '../../hooks/usePortfolioContext';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface CsvRowError {
  row_number: number;
  ticker: string;
  error: string;
}

export interface CsvImportResult {
  positions_created: number;
  errors: CsvRowError[];
}

export interface CsvImportPanelProps {
  portfolioId: string;
}

const MAX_FILE_BYTES = 1 * 1024 * 1024; // 1 MB

// ── Helpers ────────────────────────────────────────────────────────────────────

function buildFailedRowsCsv(errors: CsvRowError[]): string {
  const header = 'row_number,ticker,error';
  const rows = errors.map(
    (e) => `${e.row_number},${e.ticker},"${e.error.replace(/"/g, '""')}"`
  );
  return [header, ...rows].join('\n');
}

function downloadCsv(content: string, filename: string): void {
  const blob = new Blob([content], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Component ──────────────────────────────────────────────────────────────────

type ImportStatus = 'idle' | 'uploading' | 'success' | 'partial' | 'error';

export function CsvImportPanel({ portfolioId }: CsvImportPanelProps): React.ReactElement {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<ImportStatus>('idle');
  const [result, setResult] = useState<CsvImportResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const invalidatePortfolioContext = usePortfolioContext();

  async function handleImport(): Promise<void> {
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      setErrorMessage('Please select a CSV file.');
      return;
    }

    if (file.size > MAX_FILE_BYTES) {
      setErrorMessage('File exceeds 1 MB limit. Please split the file and retry.');
      return;
    }

    setStatus('uploading');
    setErrorMessage('');
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('portfolio_id', portfolioId);

      const resp = await fetch('/api/v1/portfolios/import', {
        method: 'POST',
        body: formData,
        credentials: 'include',
      });

      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        const msg = body?.error?.message ?? 'Import failed. Please try again.';
        setErrorMessage(msg);
        setStatus('error');
        return;
      }

      const body = await resp.json();
      const importResult: CsvImportResult = body.data;
      setResult(importResult);

      if (importResult.errors.length === 0) {
        setStatus('success');
      } else {
        setStatus('partial');
      }

      // Invalidate portfolio context to refresh position lists and map overlay
      invalidatePortfolioContext();
    } catch (err) {
      setErrorMessage('Network error. Please try again.');
      setStatus('error');
    }
  }

  return (
    <div data-testid="csv-import-panel">
      <label htmlFor="csv-file-input">
        Upload positions CSV (max 1 MB, .csv only)
      </label>
      <input
        id="csv-file-input"
        ref={fileInputRef}
        type="file"
        accept=".csv"
        data-testid="csv-file-input"
        disabled={status === 'uploading'}
      />

      <button
        type="button"
        data-testid="csv-import-button"
        disabled={status === 'uploading'}
        onClick={handleImport}
      >
        {status === 'uploading' ? 'Importing...' : 'Import'}
      </button>

      {/* Success state */}
      {status === 'success' && result && (
        <div data-testid="csv-import-success">
          All rows imported ({result.positions_created} position
          {result.positions_created === 1 ? '' : 's'} created).
        </div>
      )}

      {/* Partial success state */}
      {status === 'partial' && result && (
        <div data-testid="csv-import-partial">
          <p>
            {result.positions_created} row
            {result.positions_created === 1 ? '' : 's'} imported.{' '}
            {result.errors.length} row
            {result.errors.length === 1 ? '' : 's'} had errors:
          </p>
          <ul data-testid="csv-error-list">
            {result.errors.map((e) => (
              <li key={e.row_number} data-testid={`csv-error-row-${e.row_number}`}>
                Row {e.row_number} ({e.ticker}): {e.error}
              </li>
            ))}
          </ul>
          <button
            type="button"
            data-testid="download-failed-rows"
            onClick={() =>
              downloadCsv(buildFailedRowsCsv(result.errors), 'failed-rows.csv')
            }
          >
            Download failed rows
          </button>
        </div>
      )}

      {/* Error state */}
      {(status === 'error' || errorMessage) && (
        <div data-testid="csv-import-error" role="alert">
          {errorMessage}
        </div>
      )}
    </div>
  );
}

export default CsvImportPanel;
