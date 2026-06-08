/**
 * AntiFatigueSettingsPanel — editable panel for anti-fatigue global settings.
 *
 * Renders within Rules tab below alert rule list.
 * Fields: daily push limit, overall quiet hours, deduplication window.
 * Save sends PATCH with changed fields only.
 *
 * PLAN-F-025 TASK-011
 */
import React, { useEffect, useState } from 'react';
import { useAntiFatigueSettings } from '../../hooks/useAntiFatigueSettings';
import type { AntiFatigueSettings, UpdateAntiFatiguePayload } from '../../hooks/useAntiFatigueSettings';

type FormState = {
  daily_push_limit: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
  dedup_window_minutes: string;
};

function settingsToForm(s: AntiFatigueSettings): FormState {
  return {
    daily_push_limit: String(s.daily_push_limit),
    quiet_hours_start: s.quiet_hours_start ?? '',
    quiet_hours_end: s.quiet_hours_end ?? '',
    dedup_window_minutes: String(s.dedup_window_minutes),
  };
}

export function AntiFatigueSettingsPanel(): React.ReactElement {
  const { data, isLoading, updateSettings } = useAntiFatigueSettings();
  const [form, setForm] = useState<FormState>({
    daily_push_limit: '',
    quiet_hours_start: '',
    quiet_hours_end: '',
    dedup_window_minutes: '',
  });
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (data) setForm(settingsToForm(data));
  }, [data]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSuccessMsg(null);
    setErrorMsg(null);

    const payload: UpdateAntiFatiguePayload = {};
    if (form.daily_push_limit) {
      payload.daily_push_limit = parseInt(form.daily_push_limit, 10);
    }
    if (form.quiet_hours_start) {
      payload.quiet_hours_start = form.quiet_hours_start;
    }
    if (form.quiet_hours_end) {
      payload.quiet_hours_end = form.quiet_hours_end;
    }
    if (form.dedup_window_minutes) {
      payload.dedup_window_minutes = parseInt(form.dedup_window_minutes, 10);
    }

    try {
      await updateSettings.mutateAsync(payload);
      setSuccessMsg('Settings saved.');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Save failed.');
    }
  }

  if (isLoading) {
    return <p data-testid="anti-fatigue-loading">Loading settings…</p>;
  }

  return (
    <div className="anti-fatigue-settings-panel" data-testid="anti-fatigue-settings-panel">
      <h3>Anti-Fatigue Settings</h3>

      {successMsg && (
        <p className="anti-fatigue-settings-panel__success" role="status" data-testid="success-toast">
          {successMsg}
        </p>
      )}
      {errorMsg && (
        <p className="anti-fatigue-settings-panel__error" role="alert" data-testid="error-message">
          {errorMsg}
        </p>
      )}

      <form onSubmit={handleSave} data-testid="anti-fatigue-form">
        <label htmlFor="af-daily-limit">Daily Push Limit</label>
        <input
          id="af-daily-limit"
          name="daily_push_limit"
          type="number"
          min={1}
          value={form.daily_push_limit}
          onChange={handleChange}
          data-testid="field-daily-push-limit"
        />

        <label htmlFor="af-qh-start">Overall Quiet Hours Start</label>
        <input
          id="af-qh-start"
          name="quiet_hours_start"
          type="time"
          value={form.quiet_hours_start}
          onChange={handleChange}
          data-testid="field-quiet-hours-start"
        />

        <label htmlFor="af-qh-end">Overall Quiet Hours End</label>
        <input
          id="af-qh-end"
          name="quiet_hours_end"
          type="time"
          value={form.quiet_hours_end}
          onChange={handleChange}
          data-testid="field-quiet-hours-end"
        />

        <label htmlFor="af-dedup">Deduplication Window (minutes)</label>
        <input
          id="af-dedup"
          name="dedup_window_minutes"
          type="number"
          min={1}
          value={form.dedup_window_minutes}
          onChange={handleChange}
          data-testid="field-dedup-window"
        />

        <button type="submit" data-testid="save-button">
          Save
        </button>
      </form>
    </div>
  );
}

export default AntiFatigueSettingsPanel;
