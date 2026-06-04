/**
 * BriefsPage — route container for the Briefs section.
 *
 * Renders a type-filter toolbar and the BriefsList with cursor pagination.
 * Navigates to /briefs/:brief_id on row click.
 *
 * PLAN-F-026 TASK-005
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBriefs } from './hooks/useBriefs';
import { BriefsList } from './BriefsList';
import type { BriefType } from './briefs.types';
import { BRIEF_TYPE_LABELS } from './briefs.types';

type FilterOption = BriefType | null;

const FILTER_OPTIONS: Array<{ value: FilterOption; label: string }> = [
  { value: null, label: 'All' },
  { value: 'morning_brief', label: BRIEF_TYPE_LABELS.morning_brief },
  { value: 'watchlist_scan', label: BRIEF_TYPE_LABELS.watchlist_scan },
  { value: 'earnings_brief', label: BRIEF_TYPE_LABELS.earnings_brief },
  { value: 'event_deep_dive', label: BRIEF_TYPE_LABELS.event_deep_dive },
];

export function BriefsPage(): React.ReactElement {
  const navigate = useNavigate();
  const [selectedType, setSelectedType] = useState<FilterOption>(null);

  const { data, isLoading, isError, hasNextPage, isFetchingNextPage, fetchNextPage } =
    useBriefs({ briefType: selectedType });

  const allItems = data?.pages.flatMap((page) => page.data.items) ?? [];

  function handleBriefClick(briefId: string): void {
    navigate(`/briefs/${briefId}`);
  }

  return (
    <div className="briefs-page">
      <header className="briefs-page__header">
        <h1>Briefs</h1>
      </header>

      <nav className="briefs-page__filter-toolbar" aria-label="Filter by brief type">
        {FILTER_OPTIONS.map(({ value, label }) => (
          <button
            key={value ?? 'all'}
            className={`briefs-page__filter-btn${selectedType === value ? ' briefs-page__filter-btn--active' : ''}`}
            onClick={() => setSelectedType(value)}
            aria-pressed={selectedType === value}
            data-testid={`filter-btn-${value ?? 'all'}`}
          >
            {label}
          </button>
        ))}
      </nav>

      <main className="briefs-page__content">
        {isLoading && (
          <p data-testid="briefs-loading">Loading briefs...</p>
        )}
        {isError && (
          <p data-testid="briefs-error" className="briefs-page__error">
            Failed to load briefs. Please try again.
          </p>
        )}
        {!isLoading && !isError && (
          <BriefsList
            items={allItems}
            hasNextPage={hasNextPage}
            isFetchingNextPage={isFetchingNextPage}
            onLoadMore={() => fetchNextPage()}
            onBriefClick={handleBriefClick}
          />
        )}
      </main>
    </div>
  );
}

export default BriefsPage;
