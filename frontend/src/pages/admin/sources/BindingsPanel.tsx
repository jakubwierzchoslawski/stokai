/**
 * BindingsPanel — matrix table of market-source bindings.
 *
 * Rows = markets, cols = interface types. Each cell has primary + fallback
 * dropdowns populated from enabled sources. Only enabled sources appear in
 * dropdowns. PUT on change, DELETE on clear. Shows a "Change will take
 * effect within 60 s" toast after successful PUT.
 *
 * PLAN-F-028 TASK-010
 */
import React, { useState } from "react";
import { useBindings, useUpsertBinding, useDeleteBinding, Binding } from "./hooks/useBindings";
import { useSources, SourceConfig } from "./hooks/useSources";

const INTERFACE_TYPES = [
  "PriceProvider",
  "FundamentalsProvider",
  "NewsProvider",
  "FilingsProvider",
  "MacroProvider",
  "SocialProvider",
];

interface CellProps {
  marketId: string;
  interfaceType: string;
  role: "primary" | "fallback";
  enabledSources: SourceConfig[];
  currentSourceId: string | null;
  onUpsert: (sourceId: string) => void;
  onDelete: () => void;
}

function BindingCell({
  marketId,
  interfaceType,
  role,
  enabledSources,
  currentSourceId,
  onUpsert,
  onDelete,
}: CellProps) {
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    if (val === "") {
      onDelete();
    } else {
      onUpsert(val);
    }
  };

  return (
    <select
      value={currentSourceId ?? ""}
      onChange={handleChange}
      aria-label={`${role} for ${interfaceType} in market ${marketId}`}
      data-testid={`binding-select-${marketId}-${interfaceType}-${role}`}
    >
      <option value="">— none —</option>
      {enabledSources.map((src) => (
        <option key={src.source_id} value={src.source_id}>
          {src.display_name}
        </option>
      ))}
    </select>
  );
}

export const BindingsPanel: React.FC = () => {
  const { data: bindings, isLoading: bindingsLoading } = useBindings();
  const { data: sources, isLoading: sourcesLoading } = useSources();
  const upsert = useUpsertBinding();
  const remove = useDeleteBinding();
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(null), 4000);
  };

  const enabledSources = (sources ?? []).filter((s) => s.enabled);

  // Collect unique market IDs from bindings
  const marketIds = Array.from(
    new Set((bindings ?? []).map((b) => b.market_id))
  ).sort();

  const getBinding = (
    marketId: string,
    interfaceType: string,
    role: string
  ): string | null => {
    const b = (bindings ?? []).find(
      (b) =>
        b.market_id === marketId &&
        b.interface_type === interfaceType &&
        b.role === role
    );
    return b ? b.source_id : null;
  };

  const handleUpsert = (
    marketId: string,
    interfaceType: string,
    role: "primary" | "fallback",
    sourceId: string
  ) => {
    upsert.mutate(
      { market_id: marketId, interface_type: interfaceType, source_id: sourceId, role },
      {
        onSuccess: () => {
          showToast("Change will take effect within 60 s");
        },
      }
    );
  };

  const handleDelete = (
    marketId: string,
    interfaceType: string,
    sourceId: string
  ) => {
    remove.mutate({ market_id: marketId, interface_type: interfaceType, source_id: sourceId });
  };

  if (bindingsLoading || sourcesLoading) {
    return (
      <div className="bindings-loading" aria-busy="true" data-testid="bindings-loading">
        Loading bindings…
      </div>
    );
  }

  if (marketIds.length === 0) {
    return (
      <div className="bindings-empty" data-testid="bindings-empty">
        No market bindings found. Create a binding to route data for a market.
      </div>
    );
  }

  return (
    <div className="bindings-panel" data-testid="bindings-panel-content">
      {toast && (
        <div
          className="bindings-toast"
          role="status"
          aria-live="polite"
          data-testid="bindings-toast"
        >
          {toast}
        </div>
      )}

      <div className="bindings-table-wrapper">
        <table className="bindings-table">
          <thead>
            <tr>
              <th>Market</th>
              {INTERFACE_TYPES.map((iType) => (
                <th key={iType} colSpan={2}>
                  {iType}
                  <br />
                  <span className="bindings-role-header">
                    <small>Primary / Fallback</small>
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {marketIds.map((marketId) => (
              <tr key={marketId} data-testid={`binding-row-${marketId}`}>
                <td className="market-id-cell" title={marketId}>
                  {marketId.slice(0, 8)}…
                </td>
                {INTERFACE_TYPES.map((iType) => {
                  const primarySourceId = getBinding(marketId, iType, "primary");
                  const fallbackSourceId = getBinding(marketId, iType, "fallback");
                  return (
                    <React.Fragment key={iType}>
                      <td>
                        <BindingCell
                          marketId={marketId}
                          interfaceType={iType}
                          role="primary"
                          enabledSources={enabledSources}
                          currentSourceId={primarySourceId}
                          onUpsert={(sourceId) =>
                            handleUpsert(marketId, iType, "primary", sourceId)
                          }
                          onDelete={() =>
                            primarySourceId
                              ? handleDelete(marketId, iType, primarySourceId)
                              : undefined
                          }
                        />
                      </td>
                      <td>
                        <BindingCell
                          marketId={marketId}
                          interfaceType={iType}
                          role="fallback"
                          enabledSources={enabledSources}
                          currentSourceId={fallbackSourceId}
                          onUpsert={(sourceId) =>
                            handleUpsert(marketId, iType, "fallback", sourceId)
                          }
                          onDelete={() =>
                            fallbackSourceId
                              ? handleDelete(marketId, iType, fallbackSourceId)
                              : undefined
                          }
                        />
                      </td>
                    </React.Fragment>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default BindingsPanel;
