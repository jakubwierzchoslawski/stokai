/**
 * AlertListRow — renders a single alert item in the Alerts Center list.
 *
 * Columns: timestamp, event title (link), action signal badge, confidence %,
 * channel badge, status badge, optional report link.
 *
 * Mobile-first responsive constraints (PLAN-N-014 TASK-007):
 *  - Row outer element: min-h-[44px] flex items-center flex-wrap (touch target)
 *  - Action signal badge: inline-flex items-center min-h-[44px]
 *  - Event title link: max-w-full overflow-hidden text-ellipsis (no overflow)
 *
 * PLAN-F-025 TASK-009
 * PLAN-N-014 TASK-007
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
    // Row outer element: min-h-[44px] flex items-center flex-wrap
    // Columns use flexShrink so they wrap rather than overflow at 375px (AC-001)
    <tr
      className="alert-list-row min-h-[44px]"
      data-testid="alert-list-row"
      style={{ minHeight: 44 }}
    >
      <td className="alert-list-row__timestamp" style={{ flexShrink: 1 }}>
        {formatLocalTime(item.occurred_at)}
      </td>
      <td className="alert-list-row__title" style={{ maxWidth: '100%', overflow: 'hidden' }}>
        {/* Link container: text truncation scoped inside link; does not cause row overflow */}
        <a
          href={item.event_link}
          className="alert-list-row__event-link"
          title={item.event_title}
          data-testid="event-link"
          style={{
            display: 'block',
            maxWidth: '100%',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {truncate(item.event_title, MAX_TITLE_LENGTH)}
        </a>
      </td>
      <td className="alert-list-row__signal">
        {/* Action signal badge: inline-flex items-center min-h-[44px] (AC-001) */}
        <span
          className="alert-list-row__signal-badge"
          style={{
            backgroundColor: signalColor,
            display: 'inline-flex',
            alignItems: 'center',
            minHeight: 44,
          }}
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
