/**
 * IndicatorBuilder — three-panel layout for the visual DSL editor.
 *
 * Layout:
 *   Left:   ParameterPalette (draggable parameter chips)
 *   Center: FormulaCanvas (textarea + validation + save)
 *   Right:  LivePreviewPanel (5 sample company scores)
 *
 * Version history available via VersionHistoryDrawer (overlay).
 */
import React, { useState, useCallback, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ParameterPalette } from "./ParameterPalette";
import { FormulaCanvas } from "./FormulaCanvas";
import { LivePreviewPanel } from "./LivePreviewPanel";
import { VersionHistoryDrawer } from "./VersionHistoryDrawer";

interface IndicatorBuilderProps {
  indicatorId?: string;
  initialFormula?: string;
  initialName?: string;
}

interface SaveIndicatorPayload {
  name: string;
  formula_dsl: string;
  normalization_mode: string;
  direction: string;
  geo_weight: number;
}

async function saveIndicator(
  payload: SaveIndicatorPayload,
  indicatorId?: string
): Promise<{ indicator_id: string; version: number }> {
  const url = indicatorId
    ? `/api/v1/indicators/${indicatorId}`
    : "/api/v1/indicators";
  const method = indicatorId ? "PUT" : "POST";

  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const json = await response.json().catch(() => ({}));
    throw new Error(json?.error?.message ?? `Save failed: HTTP ${response.status}`);
  }

  const json = await response.json();
  return json.data;
}

export const IndicatorBuilder: React.FC<IndicatorBuilderProps> = ({
  indicatorId,
  initialFormula = "",
  initialName = "",
}) => {
  const [formula, setFormula] = useState<string>(initialFormula);
  const [indicatorName, setIndicatorName] = useState<string>(initialName);
  const [currentIndicatorId, setCurrentIndicatorId] = useState<
    string | undefined
  >(indicatorId);
  const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const queryClient = useQueryClient();

  const saveMutation = useMutation({
    mutationFn: (formula: string) =>
      saveIndicator(
        {
          name: indicatorName || "Untitled Indicator",
          formula_dsl: formula,
          normalization_mode: "percentile",
          direction: "higher_better",
          geo_weight: 0.0,
        },
        currentIndicatorId
      ),
    onSuccess: (data) => {
      setCurrentIndicatorId(data.indicator_id);
      queryClient.invalidateQueries({ queryKey: ["indicators"] });
      queryClient.invalidateQueries({
        queryKey: ["indicator-versions", data.indicator_id],
      });
    },
  });

  const handleParameterClick = useCallback((paramName: string) => {
    setFormula((prev) => {
      const separator = prev.trim() ? " " : "";
      return prev + separator + paramName;
    });
  }, []);

  const handleSave = useCallback(
    (currentFormula: string) => {
      saveMutation.mutate(currentFormula);
    },
    [saveMutation]
  );

  return (
    <div className="indicator-builder" role="main" aria-label="Indicator Builder">
      {/* Header */}
      <div className="indicator-builder__header">
        <input
          type="text"
          className="indicator-builder__name-input"
          value={indicatorName}
          onChange={(e) => setIndicatorName(e.target.value)}
          placeholder="Indicator name"
          aria-label="Indicator name"
        />

        {currentIndicatorId && (
          <button
            className="indicator-builder__history-btn"
            onClick={() => setIsHistoryOpen(true)}
            aria-label="View version history"
          >
            Version History
          </button>
        )}
      </div>

      {/* Three-panel layout */}
      <div className="indicator-builder__panels">
        {/* Left: Parameter Palette */}
        <aside className="indicator-builder__panel indicator-builder__panel--left">
          <ParameterPalette onParameterClick={handleParameterClick} />
        </aside>

        {/* Center: Formula Canvas */}
        <main className="indicator-builder__panel indicator-builder__panel--center">
          <FormulaCanvas
            formula={formula}
            onFormulaChange={setFormula}
            onSave={handleSave}
            isSaving={saveMutation.isPending}
          />
          {saveMutation.isError && (
            <p role="alert" className="indicator-builder__save-error">
              Save failed:{" "}
              {saveMutation.error instanceof Error
                ? saveMutation.error.message
                : "Unknown error"}
            </p>
          )}
          {saveMutation.isSuccess && (
            <p role="status" className="indicator-builder__save-success">
              Saved successfully (v{saveMutation.data.version})
            </p>
          )}
        </main>

        {/* Right: Live Preview */}
        <aside className="indicator-builder__panel indicator-builder__panel--right">
          <LivePreviewPanel formula={formula} />
        </aside>
      </div>

      {/* Version History Drawer */}
      {currentIndicatorId && (
        <VersionHistoryDrawer
          indicatorId={currentIndicatorId}
          isOpen={isHistoryOpen}
          onClose={() => setIsHistoryOpen(false)}
        />
      )}
    </div>
  );
};

export default IndicatorBuilder;
