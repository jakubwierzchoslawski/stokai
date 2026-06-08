/**
 * useFormulaValidation — validates DSL formula with 300ms debounce.
 *
 * - Does not call /validate on empty string.
 * - Returns ValidationResult with valid flag and error list.
 */
import { useState, useEffect, useRef, useCallback } from "react";

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

interface UseFormulaValidationOptions {
  debounceMs?: number;
}

interface UseFormulaValidationReturn {
  validationResult: ValidationResult | null;
  isValidating: boolean;
  validate: (formula: string) => void;
}

const VALIDATE_URL = "/api/v1/indicators/validate";

export function useFormulaValidation(
  options: UseFormulaValidationOptions = {}
): UseFormulaValidationReturn {
  const { debounceMs = 300 } = options;

  const [validationResult, setValidationResult] =
    useState<ValidationResult | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortController = useRef<AbortController | null>(null);

  const validate = useCallback(
    (formula: string): void => {
      // Clear previous debounce timer
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }

      // Do not validate empty strings
      if (!formula.trim()) {
        setValidationResult(null);
        setIsValidating(false);
        return;
      }

      debounceTimer.current = setTimeout(async () => {
        // Cancel any in-flight request
        if (abortController.current) {
          abortController.current.abort();
        }
        abortController.current = new AbortController();

        setIsValidating(true);
        try {
          const response = await fetch(VALIDATE_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ formula_dsl: formula }),
            signal: abortController.current.signal,
          });

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }

          const json = await response.json();
          setValidationResult(json.data as ValidationResult);
        } catch (err: unknown) {
          if (err instanceof Error && err.name === "AbortError") {
            // Request was cancelled — ignore
            return;
          }
          setValidationResult({
            valid: false,
            errors: [err instanceof Error ? err.message : "Validation failed"],
          });
        } finally {
          setIsValidating(false);
        }
      }, debounceMs);
    },
    [debounceMs]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      if (abortController.current) abortController.current.abort();
    };
  }, []);

  return { validationResult, isValidating, validate };
}
