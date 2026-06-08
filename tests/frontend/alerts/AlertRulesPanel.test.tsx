import { describe, it, expect, vi, beforeEach } from 'vitest';
/**
 * Tests for AlertRulesPanel, AlertRuleCard, AlertRuleFormModal.
 *
 * PLAN-F-025 TASK-010
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AlertRulesPanel } from '../../../src/frontend/components/alerts/AlertRulesPanel';
import { AlertRuleCard } from '../../../src/frontend/components/alerts/AlertRuleCard';
import { AlertRuleFormModal } from '../../../src/frontend/components/alerts/AlertRuleFormModal';
import type { AlertRule } from '../../../src/frontend/hooks/useAlertRules';

// Mock hooks
vi.mock('../../../src/frontend/hooks/useAlertRules', () => ({
  useAlertRules: vi.fn(),
  ALERT_RULES_QUERY_KEY: ['alert-rules'],
}));

vi.mock('../../../src/frontend/hooks/useMutateAlertRule', () => ({
  useMutateAlertRule: vi.fn(),
}));

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(),
  useMutation: vi.fn(),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
}));


const makeRule = (overrides: Partial<AlertRule> = {}): AlertRule => ({
  rule_id: 'rule-1',
  user_id: 'user-1',
  name: 'Test Rule',
  enabled: true,
  event_category_filter: ['conflict'],
  intensity_min: 2,
  ticker_list: ['AAPL'],
  quiet_hours_start: null,
  quiet_hours_end: null,
  per_ticker_interval_hours: 24,
  channels: ['email'],
  ...overrides,
});

const noopMutations = {
  createRule: { mutate: vi.fn(), mutateAsync: vi.fn() },
  updateRule: { mutate: vi.fn(), mutateAsync: vi.fn() },
  deleteRule: { mutate: vi.fn(), mutateAsync: vi.fn() },
};

// â”€â”€ AlertRulesPanel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('AlertRulesPanel', () => {
  beforeEach(() => {
    useMutateAlertRule.mockReturnValue(noopMutations);
  });

  it('renders one AlertRuleCard per rule returned by useAlertRules', () => {
    useAlertRules.mockReturnValue({
      data: [makeRule({ rule_id: 'r1' }), makeRule({ rule_id: 'r2' })],
      isLoading: false,
    });
    render(<AlertRulesPanel />);
    expect(screen.getAllByTestId('alert-rule-card')).toHaveLength(2);
  });

  it('shows empty state when rule list is empty', () => {
    useAlertRules.mockReturnValue({ data: [], isLoading: false });
    render(<AlertRulesPanel />);
    expect(screen.getByTestId('rules-empty')).toBeInTheDocument();
  });
});

// â”€â”€ AlertRuleCard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('AlertRuleCard', () => {
  it('enabled toggle calls onToggleEnabled with { enabled: false } when toggling off enabled rule', () => {
    const onToggleEnabled = vi.fn();
    render(
      <AlertRuleCard
        rule={makeRule({ enabled: true })}
        onEdit={vi.fn()}
        onToggleEnabled={onToggleEnabled}
        onDelete={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId('enabled-toggle'));
    expect(onToggleEnabled).toHaveBeenCalledWith('rule-1', false);
  });

  it('Delete button shows confirmation text before calling deleteRule', () => {
    render(
      <AlertRuleCard
        rule={makeRule()}
        onEdit={vi.fn()}
        onToggleEnabled={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId('delete-button'));
    expect(screen.getByTestId('delete-confirm-text')).toBeInTheDocument();
  });

  it('Delete confirms and calls onDelete with the correct rule_id', () => {
    const onDelete = vi.fn();
    render(
      <AlertRuleCard
        rule={makeRule({ rule_id: 'rule-99' })}
        onEdit={vi.fn()}
        onToggleEnabled={vi.fn()}
        onDelete={onDelete}
      />
    );
    fireEvent.click(screen.getByTestId('delete-button'));
    fireEvent.click(screen.getByTestId('delete-confirm-yes'));
    expect(onDelete).toHaveBeenCalledWith('rule-99');
  });
});

// â”€â”€ AlertRuleFormModal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('AlertRuleFormModal', () => {
  it('submit with intensity_min=6 shows validation error and does not call createRule', () => {
    const onCreateRule = vi.fn();
    render(
      <AlertRuleFormModal
        onCreateRule={onCreateRule}
        onUpdateRule={vi.fn()}
        onClose={vi.fn()}
      />
    );
    fireEvent.change(screen.getByTestId('field-name'), { target: { value: 'Test' } });
    fireEvent.change(screen.getByTestId('field-intensity-min'), { target: { value: '6' } });
    // Use submit event on the form to bypass native HTML5 validation in jsdom
    fireEvent.submit(screen.getByTestId('alert-rule-form'));
    expect(screen.getByTestId('validation-error')).toBeInTheDocument();
    expect(onCreateRule).not.toHaveBeenCalled();
  });

  it('submit with valid data calls createRule with correct payload', () => {
    const onCreateRule = vi.fn();
    render(
      <AlertRuleFormModal
        onCreateRule={onCreateRule}
        onUpdateRule={vi.fn()}
        onClose={vi.fn()}
      />
    );
    fireEvent.change(screen.getByTestId('field-name'), { target: { value: 'My Rule' } });
    fireEvent.change(screen.getByTestId('field-intensity-min'), { target: { value: '3' } });
    fireEvent.click(screen.getByTestId('submit-button'));
    expect(onCreateRule).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'My Rule', intensity_min: 3 })
    );
  });

  it('in edit mode pre-populates all fields from the existing rule', () => {
    const rule = makeRule({
      name: 'Existing Rule',
      intensity_min: 4,
      ticker_list: ['MSFT', 'GOOG'],
    });
    render(
      <AlertRuleFormModal
        initialRule={rule}
        onCreateRule={vi.fn()}
        onUpdateRule={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId('field-name')).toHaveValue('Existing Rule');
    expect(screen.getByTestId('field-intensity-min')).toHaveValue(4);
    expect(screen.getByTestId('field-ticker-list')).toHaveValue('MSFT, GOOG');
  });

  it('in edit mode calls updateRule (not createRule) on submit', () => {
    const onCreateRule = vi.fn();
    const onUpdateRule = vi.fn();
    const rule = makeRule();
    render(
      <AlertRuleFormModal
        initialRule={rule}
        onCreateRule={onCreateRule}
        onUpdateRule={onUpdateRule}
        onClose={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId('submit-button'));
    expect(onUpdateRule).toHaveBeenCalled();
    expect(onCreateRule).not.toHaveBeenCalled();
  });
});
