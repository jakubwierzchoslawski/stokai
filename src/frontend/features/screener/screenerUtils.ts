/**
 * screenerUtils — pure utility functions for the Company Screener.
 *
 * rowsToCsv: Serialises ScreenerRow[] to an RFC 4180-compliant CSV string.
 * downloadCsv: Triggers a client-side download of a CSV string as a file.
 *
 * CSV column order mirrors the table display order in ScreenerTable.tsx.
 * Numeric formatting:
 *   custom_score / score_delta / current_price → 2 decimal places
 *   market_cap                                 → 0 decimal places
 * active_event_categories → joined with ";" in the cell value.
 *
 * RFC 4180 quoting: fields containing commas, double-quotes, or newlines are
 * wrapped in double-quotes; embedded double-quotes are escaped as "".
 */
import type { ScreenerRow } from "./screenerTypes";

// ---------------------------------------------------------------------------
// CSV headers — must match ScreenerTable column labels
// ---------------------------------------------------------------------------

const CSV_HEADERS = [
  "Ticker",
  "Name",
  "Sector",
  "Market Cap",
  "Custom Score",
  "Score Delta",
  "Price",
  "Active Events",
  "Event Categories",
] as const;

// ---------------------------------------------------------------------------
// RFC 4180 helpers
// ---------------------------------------------------------------------------

/**
 * Escape a single CSV field value per RFC 4180.
 * Wraps in double-quotes if the value contains a comma, double-quote, or newline.
 * Embedded double-quotes are doubled ("").
 */
function escapeCsvField(value: string): string {
  const needsQuoting = value.includes(",") || value.includes('"') || value.includes("\n") || value.includes("\r");
  if (!needsQuoting) {
    return value;
  }
  const escaped = value.replace(/"/g, '""');
  return `"${escaped}"`;
}

// ---------------------------------------------------------------------------
// Row serialiser
// ---------------------------------------------------------------------------

/**
 * Serialise a list of ScreenerRow objects to an RFC 4180 CSV string.
 *
 * The output includes a header row followed by one data row per ScreenerRow.
 * CRLF (\r\n) line endings per RFC 4180.
 */
export function rowsToCsv(rows: ScreenerRow[]): string {
  const lines: string[] = [];

  // Header row
  lines.push(CSV_HEADERS.map(escapeCsvField).join(","));

  // Data rows
  for (const row of rows) {
    const fields = [
      row.ticker,
      row.name,
      row.sector,
      Math.round(row.market_cap).toFixed(0),
      row.custom_score.toFixed(2),
      row.score_delta.toFixed(2),
      row.current_price.toFixed(2),
      String(row.active_events_count),
      row.active_event_categories.join(";"),
    ];
    lines.push(fields.map(escapeCsvField).join(","));
  }

  return lines.join("\r\n");
}

// ---------------------------------------------------------------------------
// Download trigger
// ---------------------------------------------------------------------------

/**
 * Trigger a client-side CSV download.
 *
 * Creates a temporary <a download> element, sets the href to a Blob URL,
 * programmatically clicks it, then revokes the URL.
 *
 * @param csv     - The CSV string to download.
 * @param filename - The suggested filename for the download.
 */
export function downloadCsv(csv: string, filename: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
