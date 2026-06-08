/**
 * AddSourceModal — modal form for creating a new data source.
 *
 * Fields: display_name (required, max 120), interface_type (enum select),
 * credentials_ref (required, must match ^(env|vault):[A-Z0-9_]+$),
 * config (JSON textarea), cost_tier, priority.
 *
 * POSTs to /api/v1/admin/sources on submit.
 * Closes and invalidates the sources query on success.
 *
 * PLAN-F-028 TASK-008
 */
import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { SOURCES_QUERY_KEY } from "./hooks/useSources";

const INTERFACE_TYPES = [
  "PriceProvider",
  "FundamentalsProvider",
  "NewsProvider",
  "FilingsProvider",
  "MacroProvider",
  "SocialProvider",
];

const COST_TIERS = ["free", "low", "medium", "high"];

const CREDENTIALS_REF_RE = /^(env|vault):[A-Z0-9_]+$/;

interface FormState {
  display_name: string;
  interface_type: string;
  credentials_ref: string;
  config: string;
  cost_tier: string;
  priority: number;
}

interface FormErrors {
  display_name?: string;
  credentials_ref?: string;
  config?: string;
}

export interface AddSourceModalProps {
  isOpen: boolean;
  onClose: () => void;
}

async function createSource(body: Record<string, unknown>): Promise<unknown> {
  return api<unknown>("/v1/admin/sources", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

function validate(form: FormState): FormErrors {
  const errors: FormErrors = {};

  if (!form.display_name.trim()) {
    errors.display_name = "Display name is required.";
  } else if (form.display_name.length > 120) {
    errors.display_name = "Display name must be 120 characters or fewer.";
  }

  if (!CREDENTIALS_REF_RE.test(form.credentials_ref)) {
    errors.credentials_ref =
      "Must match ^(env|vault):[A-Z0-9_]+$ (e.g. env:MY_API_KEY).";
  }

  if (form.config.trim()) {
    try {
      JSON.parse(form.config);
    } catch {
      errors.config = "Config must be valid JSON.";
    }
  }

  return errors;
}

export const AddSourceModal: React.FC<AddSourceModalProps> = ({ isOpen, onClose }) => {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>({
    display_name: "",
    interface_type: INTERFACE_TYPES[0]!,
    credentials_ref: "",
    config: "{}",
    cost_tier: COST_TIERS[0]!,
    priority: 0,
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: createSource,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SOURCES_QUERY_KEY });
      onClose();
    },
    onError: (err: Error) => {
      setServerError(err.message);
    },
  });

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: name === "priority" ? Number(value) : value }));
    // Clear field-level error on change
    setErrors((prev) => ({ ...prev, [name]: undefined }));
    setServerError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const validationErrors = validate(form);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    let parsedConfig: Record<string, unknown> = {};
    if (form.config.trim()) {
      try {
        parsedConfig = JSON.parse(form.config);
      } catch {
        setErrors({ config: "Config must be valid JSON." });
        return;
      }
    }

    mutation.mutate({
      display_name: form.display_name.trim(),
      interface_type: form.interface_type,
      credentials_ref: form.credentials_ref,
      config: parsedConfig,
      cost_tier: form.cost_tier,
      priority: form.priority,
    });
  };

  if (!isOpen) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-source-title"
      data-testid="add-source-modal"
    >
      <div className="modal-content">
        <header className="modal-header">
          <h2 id="add-source-title">Add Data Source</h2>
          <button
            type="button"
            className="modal-close"
            aria-label="Close modal"
            onClick={onClose}
            data-testid="modal-close"
          >
            &times;
          </button>
        </header>

        {serverError && (
          <div className="modal-server-error" role="alert" data-testid="server-error">
            {serverError}
          </div>
        )}

        <form className="add-source-form" onSubmit={handleSubmit} noValidate data-testid="add-source-form">
          {/* display_name */}
          <div className="form-group">
            <label htmlFor="display_name">Display Name *</label>
            <input
              id="display_name"
              name="display_name"
              type="text"
              maxLength={120}
              required
              value={form.display_name}
              onChange={handleChange}
              aria-describedby={errors.display_name ? "display_name-error" : undefined}
              aria-invalid={!!errors.display_name}
            />
            {errors.display_name && (
              <span id="display_name-error" className="form-error" role="alert">
                {errors.display_name}
              </span>
            )}
          </div>

          {/* interface_type */}
          <div className="form-group">
            <label htmlFor="interface_type">Interface Type *</label>
            <select
              id="interface_type"
              name="interface_type"
              value={form.interface_type}
              onChange={handleChange}
            >
              {INTERFACE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          {/* credentials_ref */}
          <div className="form-group">
            <label htmlFor="credentials_ref">Credentials Ref *</label>
            <input
              id="credentials_ref"
              name="credentials_ref"
              type="text"
              required
              placeholder="env:MY_API_KEY"
              value={form.credentials_ref}
              onChange={handleChange}
              aria-describedby={errors.credentials_ref ? "credentials_ref-error" : undefined}
              aria-invalid={!!errors.credentials_ref}
            />
            {errors.credentials_ref && (
              <span id="credentials_ref-error" className="form-error" role="alert">
                {errors.credentials_ref}
              </span>
            )}
          </div>

          {/* config */}
          <div className="form-group">
            <label htmlFor="config">Config (JSON)</label>
            <textarea
              id="config"
              name="config"
              rows={4}
              value={form.config}
              onChange={handleChange}
              aria-describedby={errors.config ? "config-error" : undefined}
              aria-invalid={!!errors.config}
            />
            {errors.config && (
              <span id="config-error" className="form-error" role="alert">
                {errors.config}
              </span>
            )}
          </div>

          {/* cost_tier */}
          <div className="form-group">
            <label htmlFor="cost_tier">Cost Tier</label>
            <select
              id="cost_tier"
              name="cost_tier"
              value={form.cost_tier}
              onChange={handleChange}
            >
              {COST_TIERS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          {/* priority */}
          <div className="form-group">
            <label htmlFor="priority">Priority</label>
            <input
              id="priority"
              name="priority"
              type="number"
              min={0}
              value={form.priority}
              onChange={handleChange}
            />
          </div>

          <footer className="modal-footer">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn--primary"
              disabled={mutation.isPending}
              data-testid="submit-btn"
            >
              {mutation.isPending ? "Creating…" : "Create Source"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
};

export default AddSourceModal;
