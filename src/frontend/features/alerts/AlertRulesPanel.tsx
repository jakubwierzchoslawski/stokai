/**
 * AlertRulesPanel — list of alert rules with create/edit/delete management.
 *
 * Renders AlertRuleCard for each rule.
 * "New Rule" button opens AlertRuleFormModal with no initial data.
 * Shows empty state when no rules exist.
 *
 * PLAN-F-025 TASK-010
 */
import React, { useState } from 'react';
import { useAlertRules } from '../../hooks/useAlertRules';
import { useMutateAlertRule } from '../../hooks/useMutateAlertRule';
import type { AlertRule } from '../../hooks/useAlertRules';
import { AlertRuleCard } from './AlertRuleCard';
import { AlertRuleFormModal } from './AlertRuleFormModal';

export function AlertRulesPanel(): React.ReactElement {
  const { data: rules = [], isLoading } = useAlertRules();
  const { createRule, updateRule, deleteRule } = useMutateAlertRule();
  const [modalRule, setModalRule] = useState<AlertRule | undefined>(undefined);
  const [isModalOpen, setIsModalOpen] = useState(false);

  function handleNewRule() {
    setModalRule(undefined);
    setIsModalOpen(true);
  }

  function handleEdit(rule: AlertRule) {
    setModalRule(rule);
    setIsModalOpen(true);
  }

  function handleCloseModal() {
    setIsModalOpen(false);
    setModalRule(undefined);
  }

  function handleToggleEnabled(rule_id: string, enabled: boolean) {
    updateRule.mutate({ rule_id, enabled });
  }

  function handleDelete(rule_id: string) {
    deleteRule.mutate(rule_id);
  }

  function handleCreate(payload: Parameters<typeof createRule.mutate>[0]) {
    createRule.mutate(payload, { onSuccess: handleCloseModal });
  }

  function handleUpdate(payload: Parameters<typeof updateRule.mutate>[0]) {
    updateRule.mutate(payload, { onSuccess: handleCloseModal });
  }

  return (
    <div className="alert-rules-panel" data-testid="alert-rules-panel">
      <div className="alert-rules-panel__header">
        <h2>Alert Rules</h2>
        <button
          className="alert-rules-panel__new-rule-btn"
          onClick={handleNewRule}
          data-testid="new-rule-button"
        >
          New Rule
        </button>
      </div>

      {isLoading && (
        <p data-testid="rules-loading">Loading rules…</p>
      )}

      {!isLoading && rules.length === 0 && (
        <p className="alert-rules-panel__empty" data-testid="rules-empty">
          No alert rules yet. Create one to get started.
        </p>
      )}

      {!isLoading && rules.length > 0 && (
        <div className="alert-rules-panel__list" data-testid="rules-list">
          {rules.map((rule) => (
            <AlertRuleCard
              key={rule.rule_id}
              rule={rule}
              onEdit={handleEdit}
              onToggleEnabled={handleToggleEnabled}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {isModalOpen && (
        <AlertRuleFormModal
          initialRule={modalRule}
          onCreateRule={handleCreate}
          onUpdateRule={handleUpdate}
          onClose={handleCloseModal}
        />
      )}
    </div>
  );
}

export default AlertRulesPanel;
