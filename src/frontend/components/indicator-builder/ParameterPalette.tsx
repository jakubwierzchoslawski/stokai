/**
 * ParameterPalette — left panel of the Indicator Builder.
 *
 * - Loads parameters from GET /api/v1/admin/scoring/parameters.
 * - Draggable chips grouped by category.
 * - Clicking a chip inserts the parameter name at cursor position.
 */
import React, { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";

interface Parameter {
  parameter_id: string;
  name: string;
  description: string | null;
  source_field: string | null;
  enabled: boolean;
  tenant_id: string;
}

interface ParameterGroup {
  category: string;
  parameters: Parameter[];
}

interface ParameterPaletteProps {
  onParameterClick?: (parameterName: string) => void;
}

async function fetchParameters(): Promise<Parameter[]> {
  const response = await fetch("/api/v1/admin/scoring/parameters");
  if (!response.ok) {
    throw new Error(`Failed to load parameters: HTTP ${response.status}`);
  }
  const json = await response.json();
  return json.data.parameters as Parameter[];
}

function groupParameters(parameters: Parameter[]): ParameterGroup[] {
  // Group by source_field prefix (e.g. "financials", "ratios", "market")
  const groups = new Map<string, Parameter[]>();

  for (const param of parameters) {
    const category = param.source_field?.split(".")[0] ?? "other";
    if (!groups.has(category)) {
      groups.set(category, []);
    }
    groups.get(category)!.push(param);
  }

  return Array.from(groups.entries()).map(([category, params]) => ({
    category,
    parameters: params.sort((a, b) => a.name.localeCompare(b.name)),
  }));
}

export const ParameterPalette: React.FC<ParameterPaletteProps> = ({
  onParameterClick,
}) => {
  const {
    data: parameters = [],
    isLoading,
    error,
  } = useQuery<Parameter[], Error>({
    queryKey: ["parameter-catalog"],
    queryFn: fetchParameters,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const groups = groupParameters(parameters.filter((p) => p.enabled));

  const handleDragStart = useCallback(
    (e: React.DragEvent<HTMLButtonElement>, paramName: string) => {
      e.dataTransfer.setData("text/plain", paramName);
      e.dataTransfer.effectAllowed = "copy";
    },
    []
  );

  if (isLoading) {
    return (
      <div className="parameter-palette" aria-busy="true">
        <p>Loading parameters...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="parameter-palette parameter-palette--error" role="alert">
        <p>Failed to load parameters: {error.message}</p>
      </div>
    );
  }

  return (
    <div className="parameter-palette" role="navigation" aria-label="Parameter Palette">
      <h3 className="parameter-palette__title">Parameters</h3>
      <p className="parameter-palette__hint">
        Click or drag a parameter to insert it into the formula.
      </p>

      {groups.map((group) => (
        <div key={group.category} className="parameter-palette__group">
          <h4 className="parameter-palette__group-title">
            {group.category.charAt(0).toUpperCase() + group.category.slice(1)}
          </h4>
          <div className="parameter-palette__chips">
            {group.parameters.map((param) => (
              <button
                key={param.parameter_id}
                className="parameter-palette__chip"
                draggable
                onDragStart={(e) => handleDragStart(e, param.name)}
                onClick={() => onParameterClick?.(param.name)}
                title={param.description ?? param.name}
                aria-label={`Insert parameter: ${param.name}`}
              >
                {param.name}
              </button>
            ))}
          </div>
        </div>
      ))}

      {groups.length === 0 && (
        <p className="parameter-palette__empty">
          No parameters available. Ask an admin to add parameters.
        </p>
      )}
    </div>
  );
};

export default ParameterPalette;
