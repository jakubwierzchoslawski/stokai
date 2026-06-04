/**
 * FormulaCanvas — center panel of the Indicator Builder.
 *
 * - Textarea with inline error annotations.
 * - Save button triggers indicator save.
 * - useFormulaValidation with 300ms debounce.
 */
import React, { useCallback, useEffect } from "react";
import { useFormulaValidation } from "./hooks/useFormulaValidation";

interface FormulaCanvasProps {
  formula: string;
  onFormulaChange: (formula: string) => void;
  onSave: (formula: string) => void;
  isSaving?: boolean;
}

export const FormulaCanvas: React.FC<FormulaCanvasProps> = ({
  formula,
  onFormulaChange,
  onSave,
  isSaving = false,
}) => {
  const { validationResult, isValidating, validate } = useFormulaValidation({
    debounceMs: 300,
  });

  // Validate on formula change
  useEffect(() => {
    validate(formula);
  }, [formula, validate]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onFormulaChange(e.target.value);
    },
    [onFormulaChange]
  );

  const handleSave = useCallback(() => {
    if (validationResult?.valid !== false) {
      onSave(formula);
    }
  }, [formula, onSave, validationResult]);

  const hasErrors =
    validationResult !== null && !validationResult.valid;
  const errors = validationResult?.errors ?? [];

  return (
    <div className="formula-canvas" role="region" aria-label="Formula Editor">
      <div className="formula-canvas__header">
        <h3>Formula</h3>
        {isValidating && (
          <span className="formula-canvas__validating" aria-live="polite">
            Validating...
          </span>
        )}
      </div>

      <textarea
        className={`formula-canvas__textarea ${hasErrors ? "formula-canvas__textarea--error" : ""}`}
        value={formula}
        onChange={handleChange}
        rows={8}
        placeholder="Enter DSL formula, e.g. revenue * 0.5 + net_income"
        aria-label="DSL Formula"
        aria-invalid={hasErrors}
        aria-describedby={hasErrors ? "formula-errors" : undefined}
        spellCheck={false}
      />

      {hasErrors && (
        <ul
          id="formula-errors"
          className="formula-canvas__errors"
          role="alert"
          aria-label="Formula errors"
        >
          {errors.map((error, index) => (
            <li key={index} className="formula-canvas__error-item">
              {error}
            </li>
          ))}
        </ul>
      )}

      {validationResult?.valid && (
        <p className="formula-canvas__valid" role="status">
          Formula is valid
        </p>
      )}

      <div className="formula-canvas__actions">
        <button
          className="formula-canvas__save-btn"
          onClick={handleSave}
          disabled={isSaving || hasErrors || !formula.trim()}
          aria-busy={isSaving}
        >
          {isSaving ? "Saving..." : "Save Indicator"}
        </button>
      </div>
    </div>
  );
};

export default FormulaCanvas;
