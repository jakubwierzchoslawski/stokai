/**
 * ScreenerPage — top-level route component for /screener.
 *
 * On mount, reads ?event_id from the URL search params (React Router).
 * When event_id is present:
 *   - Initialises ScreenerRequest with event_id set and sort by custom_score desc.
 *   - Shows a dismissible banner: "Filtered to companies affected by [event title]".
 *   - Clearing the banner removes event_id from the request and updates the URL.
 *
 * Owns the filter/sort state and passes callbacks to ScreenerFilterBar and
 * ScreenerTable.  Export CSV is delegated to screenerUtils.rowsToCsv.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ScreenerFilterBar } from "./ScreenerFilterBar";
import { ScreenerTable } from "./ScreenerTable";
import { useScreener } from "./useScreener";
import { rowsToCsv, downloadCsv } from "./screenerUtils";
import type { ScreenerColumn, ScreenerFilter, ScreenerRequest, SortDir } from "./screenerTypes";

const DEFAULT_SORT_COLUMN: ScreenerColumn = "custom_score";
const DEFAULT_SORT_DIR: SortDir = "desc";
const DEFAULT_PAGE_SIZE = 50;

export function ScreenerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const eventIdParam = searchParams.get("event_id");

  const [filters, setFilters] = useState<ScreenerFilter[]>([]);
  const [sortColumn, setSortColumn] = useState<ScreenerColumn>(DEFAULT_SORT_COLUMN);
  const [sortDir, setSortDir] = useState<SortDir>(DEFAULT_SORT_DIR);
  const [eventId, setEventId] = useState<string | undefined>(
    eventIdParam ?? undefined,
  );
  // eventTitle is not available from the URL alone — placeholder shown
  const eventTitle = eventId ? `event ${eventId}` : undefined;

  // Keep eventId in sync when URL changes externally
  useEffect(() => {
    setEventId(eventIdParam ?? undefined);
  }, [eventIdParam]);

  const request: ScreenerRequest = useMemo(
    () => ({
      filters,
      sort_column: sortColumn,
      sort_dir: sortDir,
      page_size: DEFAULT_PAGE_SIZE,
      event_id: eventId,
    }),
    [filters, sortColumn, sortDir, eventId],
  );

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
    error,
  } = useScreener(request);

  // Flatten all pages into a single row list
  const allRows = useMemo(
    () => data?.pages.flatMap((page) => page.data) ?? [],
    [data],
  );

  const handleSortChange = useCallback(
    (col: ScreenerColumn, dir: SortDir) => {
      setSortColumn(col);
      setSortDir(dir);
    },
    [],
  );

  const handleFiltersApply = useCallback((newFilters: ScreenerFilter[]) => {
    setFilters(newFilters);
  }, []);

  function dismissEventBanner() {
    setEventId(undefined);
    // Remove event_id from URL
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("event_id");
      return next;
    });
  }

  function handleExportCsv() {
    const csv = rowsToCsv(allRows);
    const today = new Date().toISOString().slice(0, 10);
    downloadCsv(csv, `stokai-screener-${today}.csv`);
  }

  return (
    <main className="screener-page">
      <div className="screener-page__header">
        <h1 className="screener-page__title">Company Screener</h1>
        <button
          className="screener-page__export-btn"
          onClick={handleExportCsv}
          disabled={allRows.length === 0}
          title="Exports currently loaded rows"
          aria-label="Export to CSV"
        >
          Export CSV
        </button>
      </div>

      {eventId && eventTitle && (
        <div
          className="screener-page__event-banner"
          role="status"
          aria-live="polite"
        >
          <span>Filtered to companies affected by {eventTitle}</span>
          <button
            className="screener-page__event-banner-dismiss"
            onClick={dismissEventBanner}
            aria-label="Dismiss event filter"
          >
            Dismiss
          </button>
        </div>
      )}

      <ScreenerFilterBar onApply={handleFiltersApply} />

      {isLoading && <p aria-live="polite">Loading…</p>}
      {isError && (
        <p role="alert" aria-live="assertive">
          Error: {error?.message}
        </p>
      )}

      {!isLoading && (
        <ScreenerTable
          rows={allRows}
          sortColumn={sortColumn}
          sortDir={sortDir}
          onSortChange={handleSortChange}
          hasNextPage={hasNextPage}
          isFetchingNextPage={isFetchingNextPage}
          onLoadMore={() => fetchNextPage()}
        />
      )}
    </main>
  );
}

export default ScreenerPage;
