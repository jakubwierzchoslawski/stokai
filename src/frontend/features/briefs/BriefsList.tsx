/**
 * BriefsList — renders a list of brief entries with infinite scroll ("Load more").
 *
 * Items are rendered in the order returned by the API (reverse chronological).
 *
 * PLAN-F-026 TASK-005
 */
import React from 'react';
import type { BriefListItem as BriefListItemType } from './briefs.types';
import { BriefListItem } from './BriefListItem';

interface BriefsListProps {
  items: BriefListItemType[];
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onLoadMore: () => void;
  onBriefClick: (briefId: string) => void;
}

export function BriefsList({
  items,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
  onBriefClick,
}: BriefsListProps): React.ReactElement {
  return (
    <div className="briefs-list">
      {items.length === 0 ? (
        <p className="briefs-list__empty" data-testid="briefs-list-empty">
          No briefs found.
        </p>
      ) : (
        <ul className="briefs-list__items" role="list" data-testid="briefs-list-items">
          {items.map((brief) => (
            <BriefListItem key={brief.brief_id} brief={brief} onClick={onBriefClick} />
          ))}
        </ul>
      )}
      {hasNextPage && (
        <button
          className="briefs-list__load-more"
          onClick={onLoadMore}
          disabled={isFetchingNextPage}
          data-testid="briefs-load-more"
        >
          {isFetchingNextPage ? 'Loading...' : 'Load more'}
        </button>
      )}
    </div>
  );
}

export default BriefsList;
