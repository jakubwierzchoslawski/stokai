/**
 * AlertRuleFormModal — modal form for creating or editing an alert rule.
 *
 * In create mode: calls createRule on submit.
 * In edit mode (rule_id present): calls updateRule on submit, pre-populates fields.
 * Validates intensity_min in [1, 5] before submitting.
 *
 * PLAN-F-025 TASK-010
 */
import React, { useEffect, useState } from 'react';
import type { AlertRule } from '../../hooks/useAlertRules';
import type { CreateAlertRulePayload, UpdateAlertRulePayload } from '../../hooks/useMutateAlertRule';

export interface AlertRuleFormModalProps {
  initialRule?: AlertRule;
  onCreateRule: (payload: CreateAlertRulePayload) => void;
  onUpdateRule: (payload: UpdateAlertRulePayload) => void;
  onClose: () => void;
}

interface FormState {
  name: string;
  event_category_filter: string;
  intensity_min: string;
  ticker_list: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
  per_ticker_interval_hours: string;
  channels_email: boolean;
}

function toFormState(rule?: AlertRule): FormState {
  if (!rule) {
    return {
      name: '',
      event_category_filter: '',
      intensity_min: '2',
      ticker_list: '',
      quiet_hours_start: '',
      quiet_hours_end: '',
      per_ticker_interval_hours: '24',
      channels_email: true,
    };
  }
  return {
    name: rule.name,
    event_category_filter: rule.event_category_filter.join(', '),
    intensity_min: String(rule.intensity_min),
    ticker_list: rule.ticker_list.join(', '),
    quiet_hours_start: rule.quiet_hours_start ?? '',
    quiet_hours_end: rule.quiet_hours_end ?? '',
    per_ticker_interval_hours: String(rule.per_ticker_interval_hours),
    channels_email: rule.channels.includes('email'),
  };
}

export function AlertRuleFormModal({
  initialRule,
  onCreateRule,
  onUpdateRule,
  onClose,
}: AlertRuleFormModalProps): React.ReactElement {
  const [form, setForm] = useState<FormState>(() => toFormState(initialRule));
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    setForm(toFormState(initialRule));
  }, [initialRule?.rule_id]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      setForm((prev) => ({ ...prev, [name]: (e.target as HTMLInputElement).checked }));
    } else {
      setForm((prev) => ({ ...prev, [name]: value }));
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setValidationError(null);

    const intensityMin = parseInt(form.intensity_min, 10);
    if (isNaN(intensityMin) || intensityMin < 1 || intensityMin > 5) {
      setValidationError('intensity_min must be between 1 and 5');
      return;
    }

    const channels: string[] = form.channels_email ? ['email'] : [];
    const eventCategoryFilter = form.event_category_filter
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const tickerList = form.ticker_list
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    if (initialRule?.rule_id) {
      onUpdateRule({
        rule_id: initialRule.rule_id,
        name: form.name,
        event_category_filter: eventCategoryFilter,
        intensity_min: intensityMin,
        ticker_list: tickerList,
        quiet_hours_start: form.quiet_hours_start || null,
        quiet_hours_end: form.quiet_hours_end || null,
        per_ticker_interval_hours: parseInt(form.per_ticker_interval_hours, 10),
        channels,
      });
    } else {
      onCreateRule({
        name: form.name,
        event_category_filter: eventCategoryFilter,
        intensity_min: intensityMin,
        ticker_list: tickerList,
        quiet_hours_start: form.quiet_hours_start || null,
        quiet_hours_end: form.quiet_hours_end || null,
        per_ticker_interval_hours: parseInt(form.per_ticker_interval_hours, 10),
        channels,
      });
    }
  }

  const isEdit = Boolean(initialRule?.rule_id);

  return (
    <div
      className="alert-rule-form-modal"
      role="dialog"
      aria-modal="true"
      aria-label={isEdit ? 'Edit alert rule' : 'Create alert rule'}
      data-testid="alert-rule-form-modal"
    >
      <div className="alert-rule-form-modal__backdrop" onClick={onClose} />
      <div className="alert-rule-form-modal__content">
        <h2>{isEdit ? 'Edit Rule' : 'New Rule'}</h2>

        {validationError && (
          <p className="alert-rule-form-modal__error" data-testid="validation-error" role="alert">
            {validationError}
          </p>
        )}

        <form onSubmit={handleSubmit} data-testid="alert-rule-form">
          <label htmlFor="rule-name">Name *</label>
          <input
            id="rule-name"
            name="name"
            type="text"
            required
            value={form.name}
            onChange={handleChange}
            data-testid="field-name"
          />

          <label htmlFor="rule-categories">Event Category Filter (comma-separated)</label>
          <input
            id="rule-categories"
            name="event_category_filter"
            type="text"
            value={form.event_category_filter}
            onChange={handleChange}
            data-testid="field-event-category-filter"
          />

          <label htmlFor="rule-intensity">Intensity Min (1-5) *</label>
          <input
            id="rule-intensity"
            name="intensity_min"
            type="number"
            min={1}
            max={5}
            required
            value={form.intensity_min}
            onChange={handleChange}
            data-testid="field-intensity-min"
          />

          <label htmlFor="rule-tickers">Ticker List (comma-separated)</label>
          <input
            id="rule-tickers"
            name="ticker_list"
            type="text"
            value={form.ticker_list}
            onChange={handleChange}
            data-testid="field-ticker-list"
          />

          <label htmlFor="rule-qh-start">Quiet Hours Start (HH:MM)</label>
          <input
            id="rule-qh-start"
            name="quiet_hours_start"
            type="time"
            value={form.quiet_hours_start}
            onChange={handleChange}
            data-testid="field-quiet-hours-start"
          />

          <label htmlFor="rule-qh-end">Quiet Hours End (HH:MM)</label>
          <input
            id="rule-qh-end"
            name="quiet_hours_end"
            type="time"
            value={form.quiet_hours_end}
            onChange={handleChange}
            data-testid="field-quiet-hours-end"
          />

          <label htmlFor="rule-interval">Per-Ticker Interval (hours) *</label>
          <input
            id="rule-interval"
            name="per_ticker_interval_hours"
            type="number"
            min={1}
            required
            value={form.per_ticker_interval_hours}
            onChange={handleChange}
            data-testid="field-per-ticker-interval"
          />

          <fieldset>
            <legend>Channels</legend>
            <label>
              <input
                type="checkbox"
                name="channels_email"
                checked={form.channels_email}
                onChange={handleChange}
                data-testid="field-channel-email"
              />
              {' '}Email
            </label>
          </fieldset>

          <div className="alert-rule-form-modal__actions">
            <button type="submit" data-testid="submit-button">
              {isEdit ? 'Save Changes' : 'Create Rule'}
            </button>
            <button type="button" onClick={onClose} data-testid="cancel-button">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default AlertRuleFormModal;
