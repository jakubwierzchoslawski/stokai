/**
 * AlertRuleCard — displays a single alert rule with edit/delete controls.
 *
 * Toggle enabled status calls updateRule on click.
 * Delete shows inline confirmation before calling deleteRule.
 *
 * Mobile-first responsive constraints (PLAN-N-014 TASK-007):
 *  - Enable/disable toggle: min-h-[44px]
 *  - Edit and Delete buttons: min-h-[44px]
 *  - Card container: max-w-full; metadata stacks vertically at base (flex-col)
 *
 * PLAN-F-025 TASK-010
 * PLAN-N-014 TASK-007
 */
import React, { useState } from 'react';
import type { AlertRule } from '../../hooks/useAlertRules';

export interface AlertRuleCardProps {
  rule: AlertRule;
  onEdit: (rule: AlertRule) => void;
  onToggleEnabled: (rule_id: string, enabled: boolean) => void;
  onDelete: (rule_id: string) => void;
}

export function AlertRuleCard({
  rule,
  onEdit,
  onToggleEnabled,
  onDelete,
}: AlertRuleCardProps): React.ReactElement {
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  function handleToggle() {
    onToggleEnabled(rule.rule_id, !rule.enabled);
  }

  function handleDeleteRequest() {
    setConfirmingDelete(true);
  }

  function handleDeleteConfirm() {
    onDelete(rule.rule_id);
    setConfirmingDelete(false);
  }

  function handleDeleteCancel() {
    setConfirmingDelete(false);
  }

  return (
    // Card container: max-w-full prevents overflow at 375px (AC-001)
    <div
      className="alert-rule-card"
      data-testid="alert-rule-card"
      data-rule-id={rule.rule_id}
      style={{ maxWidth: '100%' }}
    >
      <div className="alert-rule-card__header">
        <h3 className="alert-rule-card__name">{rule.name}</h3>
        {/* Enable/disable toggle: min-h-[44px] for touch target (AC-001) */}
        <label
          className="alert-rule-card__toggle min-h-[44px]"
          aria-label={`${rule.enabled ? 'Disable' : 'Enable'} rule ${rule.name}`}
          style={{ minHeight: 44, display: 'inline-flex', alignItems: 'center', gap: 8 }}
        >
          <input
            type="checkbox"
            checked={rule.enabled}
            onChange={handleToggle}
            data-testid="enabled-toggle"
          />
          {rule.enabled ? 'Enabled' : 'Disabled'}
        </label>
      </div>

      {/* Metadata stacks vertically at base (flex-col) — wraps at 375px (AC-001) */}
      <div
        className="alert-rule-card__details"
        style={{ display: 'flex', flexDirection: 'column', gap: 4 }}
      >
        <span className="alert-rule-card__intensity">
          Min intensity: <strong>{rule.intensity_min}</strong>
        </span>
        <div className="alert-rule-card__channels">
          {rule.channels.map((ch) => (
            <span key={ch} className="alert-rule-card__channel-badge" data-testid="channel-badge">
              {ch}
            </span>
          ))}
        </div>
      </div>

      <div className="alert-rule-card__actions">
        {/* Edit button: min-h-[44px] for touch target (AC-001) */}
        <button
          onClick={() => onEdit(rule)}
          className="alert-rule-card__edit-btn min-h-[44px]"
          data-testid="edit-button"
          style={{ minHeight: 44 }}
        >
          Edit
        </button>

        {!confirmingDelete ? (
          /* Delete button: min-h-[44px] for touch target (AC-001) */
          <button
            onClick={handleDeleteRequest}
            className="alert-rule-card__delete-btn min-h-[44px]"
            data-testid="delete-button"
            style={{ minHeight: 44 }}
          >
            Delete
          </button>
        ) : (
          <span className="alert-rule-card__delete-confirm" data-testid="delete-confirm">
            <span data-testid="delete-confirm-text">Are you sure?</span>
            <button
              onClick={handleDeleteConfirm}
              data-testid="delete-confirm-yes"
              style={{ minHeight: 44 }}
            >
              Yes
            </button>
            <button
              onClick={handleDeleteCancel}
              data-testid="delete-confirm-no"
              style={{ minHeight: 44 }}
            >
              No
            </button>
          </span>
        )}
      </div>
    </div>
  );
}

export default AlertRuleCard;
