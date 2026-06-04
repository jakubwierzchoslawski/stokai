/**
 * AlertRuleCard — displays a single alert rule with edit/delete controls.
 *
 * Toggle enabled status calls updateRule on click.
 * Delete shows inline confirmation before calling deleteRule.
 *
 * PLAN-F-025 TASK-010
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
    <div
      className="alert-rule-card"
      data-testid="alert-rule-card"
      data-rule-id={rule.rule_id}
    >
      <div className="alert-rule-card__header">
        <h3 className="alert-rule-card__name">{rule.name}</h3>
        <label className="alert-rule-card__toggle" aria-label={`${rule.enabled ? 'Disable' : 'Enable'} rule ${rule.name}`}>
          <input
            type="checkbox"
            checked={rule.enabled}
            onChange={handleToggle}
            data-testid="enabled-toggle"
          />
          {rule.enabled ? 'Enabled' : 'Disabled'}
        </label>
      </div>

      <div className="alert-rule-card__details">
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
        <button
          onClick={() => onEdit(rule)}
          className="alert-rule-card__edit-btn"
          data-testid="edit-button"
        >
          Edit
        </button>

        {!confirmingDelete ? (
          <button
            onClick={handleDeleteRequest}
            className="alert-rule-card__delete-btn"
            data-testid="delete-button"
          >
            Delete
          </button>
        ) : (
          <span className="alert-rule-card__delete-confirm" data-testid="delete-confirm">
            <span data-testid="delete-confirm-text">Are you sure?</span>
            <button onClick={handleDeleteConfirm} data-testid="delete-confirm-yes">Yes</button>
            <button onClick={handleDeleteCancel} data-testid="delete-confirm-no">No</button>
          </span>
        )}
      </div>
    </div>
  );
}

export default AlertRuleCard;
