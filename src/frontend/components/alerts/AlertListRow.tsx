/**
 * AlertListRow — renders a single alert item in the Alerts Center list.
 *
 * Columns: timestamp, event title (link), action signal badge, confidence %,
 * channel badge, status badge, optional report link.
 *
 * PLAN-F-025 TASK-009
 */
import React from 'react';
import type { AlertListItem } from '../../hooks/useAlerts';

const ACTION_SIGNAL_COLORS: Record<string, string> = {
  HOLD: '#6b7280',
  WATCH: '#3b82f6',
  BUY_OPP: '#10b981',
  REDUCE_RISK: '#f59e0b',
  HEDGE: '#8b5cf6',
  CONTRARIAN: '#ec4899',
};

const MAX_TITLE_LENGTH = 60;

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return `${text.slice(0, maxLen - 1)}…`;
}

function formatLocalTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

interface AlertListRowProps {
  item: AlertListItem;
}

export function AlertListRow({ item }: AlertListRowProps): React.ReactElement {
  const signalColor = ACTION_SIGNAL_COLORS[item.action_signal] ?? '#6b7280';

  return (
    <tr className="alert-list-row" data-testid="alert-list-row">
      <td className="alert-list-row__timestamp">
        {formatLocalTime(item.occurred_at)}
      </td>
      <td className="alert-list-row__title">
        <a
          href={item.event_link}
          className="alert-list-row__event-link"
          title={item.event_title}
          data-testid="event-link"
        >
          {truncate(item.event_title, MAX_TITLE_LENGTH)}
        </a>
      </td>
      <td className="alert-list-row__signal">
        <span
          className="alert-list-row__signal-badge"
          style={{ backgroundColor: signalColor }}
          data-testid="action-signal-badge"
        >
          {item.action_signal}
        </span>
      </td>
      <td className="alert-list-row__confidence">
        {(item.confidence * 100).toFixed(0)}%
      </td>
      <td className="alert-list-row__channel">
        <span className="alert-list-row__channel-badge">{item.channel}</span>
      </td>
      <td className="alert-list-row__status">
        <span className={`alert-list-row__status-badge alert-list-row__status-badge--${item.status}`}>
          {item.status}
        </span>
      </td>
      <td className="alert-list-row__report">
        {item.report_link !== null && (
          <a
            href={item.report_link}
            className="alert-list-row__report-link"
            data-testid="report-link"
          >
            Report
          </a>
        )}
      </td>
    </tr>
  );
}

export default AlertListRow;
