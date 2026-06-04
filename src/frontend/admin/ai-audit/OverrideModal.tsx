/**
 * OverrideModal — modal for submitting an admin override to an AI decision.
 *
 * Content:
 *   - Original decision summary (agent role, model, confidence, truncated output)
 *   - Text area for corrected output (required, min 10 chars)
 *   - Text input for override reason (required, min 20 chars)
 *   - Submit and Cancel buttons
 *
 * On success: displays proposed_prompt_adjustment in a read-only box.
 * On error: displays error message without closing.
 *
 * PLAN-F-029 TASK-008
 */
import React, { useState } from 'react';
import { useAdminOverride } from './hooks/useAdminOverride';
import { type AIDecisionDetail } from './DecisionDetailDrawer';

interface Props {
  decision: AIDecisionDetail;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function OverrideModal({ decision, isOpen, onClose, onSuccess }: Props) {
  const [correctedOutput, setCorrectedOutput] = useState('');
  const [overrideReason, setOverrideReason] = useState('');
  const [proposedAdjustment, setProposedAdjustment] = useState<string | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);

  const mutation = useAdminOverride();

  if (!isOpen) return null;

  const isSubmitDisabled =
    correctedOutput.trim().length < 10 ||
    overrideReason.trim().length < 20 ||
    mutation.isPending;

  function handleSubmit() {
    mutation.mutate(
      {
        decision_id: decision.decision_id,
        corrected_output: correctedOutput,
        override_reason: overrideReason,
      },
      {
        onSuccess: (data) => {
          setProposedAdjustment(data.proposed_prompt_adjustment);
        },
      }
    );
  }

  function handleAcknowledge() {
    setProposedAdjustment(null);
    setCorrectedOutput('');
    setOverrideReason('');
    onSuccess();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      data-testid="override-modal"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold">Override AI Decision</h2>

        {/* Decision summary */}
        <div className="bg-gray-50 rounded p-3 text-sm space-y-1">
          <p>
            <span className="font-medium">Agent:</span> {decision.agent_role}
          </p>
          <p>
            <span className="font-medium">Model:</span> {decision.model}
          </p>
          <p>
            <span className="font-medium">Confidence:</span>{' '}
            {(decision.confidence * 100).toFixed(1)}%
          </p>
          <p className="truncate">
            <span className="font-medium">Original output:</span> {decision.output_text.slice(0, 200)}
          </p>
        </div>

        {/* Corrected output */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Corrected output <span className="text-red-500">*</span>
          </label>
          <textarea
            value={correctedOutput}
            onChange={(e) => setCorrectedOutput(e.target.value)}
            rows={4}
            placeholder="Enter the correct output (min 10 characters)"
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            data-testid="corrected-output"
          />
          {correctedOutput.trim().length > 0 && correctedOutput.trim().length < 10 && (
            <p className="text-xs text-red-500 mt-1">Minimum 10 characters required</p>
          )}
        </div>

        {/* Override reason */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Override reason <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            placeholder="Reason for override (min 20 characters)"
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            data-testid="override-reason"
          />
          {overrideReason.trim().length > 0 && overrideReason.trim().length < 20 && (
            <p className="text-xs text-red-500 mt-1">Minimum 20 characters required</p>
          )}
        </div>

        {/* Error message */}
        {mutation.isError && (
          <div
            className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700"
            data-testid="override-error"
          >
            {mutation.error.message}
          </div>
        )}

        {/* Proposed adjustment (after success) */}
        {proposedAdjustment && (
          <div
            className="bg-amber-50 border border-amber-200 rounded p-3 space-y-2"
            data-testid="proposed-adjustment"
          >
            <p className="text-sm font-semibold text-amber-800">
              Proposed prompt adjustment (requires admin approval)
            </p>
            <p className="text-sm text-amber-700">{proposedAdjustment}</p>
            <button
              onClick={handleAcknowledge}
              className="px-3 py-1 bg-amber-600 text-white text-sm rounded hover:bg-amber-700"
              data-testid="acknowledge-btn"
            >
              Acknowledge
            </button>
          </div>
        )}

        {/* Buttons */}
        {!proposedAdjustment && (
          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-300"
              data-testid="cancel-override"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={isSubmitDisabled}
              className="px-4 py-2 bg-red-600 text-white text-sm rounded hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="submit-override"
            >
              {mutation.isPending ? 'Submitting...' : 'Submit Override'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
