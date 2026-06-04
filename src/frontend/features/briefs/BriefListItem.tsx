/**
 * BriefListItem — single row in the briefs list.
 *
 * Displays: type badge, date, headline, confidence (colour-coded), delivery status.
 * Clicking the row navigates to /briefs/:brief_id.
 *
 * Confidence colour thresholds (Architecture D9):
 *   green  >= 70%
 *   amber  40-69%
 *   red    < 40%
 *
 * PLAN-F-026 TASK-005
 */
import React from 'react';
import type { BriefListItem as BriefListItemType } from './briefs.types';
import { BRIEF_TYPE_LABELS } from './briefs.types';

interface BriefListItemProps {
  brief: BriefListItemType;
  onClick: (briefId: string) => void;
}

function confidenceClass(confidence: number): string {
  if (confidence >= 0.7) return 'brief-list-item__confidence--green';
  if (confidence >= 0.4) return 'brief-list-item__confidence--amber';
  return 'brief-list-item__confidence--red';
}

function typeBadgeClass(type: BriefListItemType['type']): string {
  return `brief-list-item__type-badge brief-list-item__type-badge--${type.replace(/_/g, '-')}`;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' });
}

export function BriefListItem({ brief, onClick }: BriefListItemProps): React.ReactElement {
  const confidencePct = `${Math.round(brief.confidence * 100)}%`;

  return (
    <li
      className="brief-list-item"
      role="listitem"
      onClick={() => onClick(brief.brief_id)}
      style={{ cursor: 'pointer' }}
      data-testid={`brief-list-item-${brief.brief_id}`}
    >
      <span className={typeBadgeClass(brief.type)} data-testid="brief-type-badge">
        {BRIEF_TYPE_LABELS[brief.type]}
      </span>
      <span className="brief-list-item__date" data-testid="brief-date">
        {formatDate(brief.date)}
      </span>
      <span className="brief-list-item__headline" data-testid="brief-headline">
        {brief.headline}
      </span>
      <span
        className={`brief-list-item__confidence ${confidenceClass(brief.confidence)}`}
        data-testid="brief-confidence"
      >
        {confidencePct}
      </span>
      <span className="brief-list-item__status" data-testid="brief-delivery-status">
        {brief.delivery_status}
      </span>
    </li>
  );
}

export default BriefListItem;
