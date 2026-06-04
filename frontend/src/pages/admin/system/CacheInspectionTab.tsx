/**
 * CacheInspectionTab — Redis cache inspection and force-refresh per data type.
 *
 * - Table of {data_type, key_count, estimated_size}
 * - "Force Refresh" button per row
 * - Optional company_id input for price_bars type
 *
 * PLAN-F-030 TASK-010
 */
import React, { useState } from "react";
import { useCacheStats, useRefreshCache } from "./hooks/useSystemOps";

const DATA_TYPES = [
  { key: "price_bars", label: "Price Bars", companyScoped: true },
  { key: "embeddings", label: "Embeddings", companyScoped: false },
  { key: "event_data", label: "Event Data", companyScoped: false },
] as const;

type DataTypeKey = (typeof DATA_TYPES)[number]["key"];

export const CacheInspectionTab: React.FC = () => {
  const { data: stats, isLoading, isError } = useCacheStats();
  const refresh = useRefreshCache();
  const [companyId, setCompanyId] = useState<string>("");
  const [activeType, setActiveType] = useState<DataTypeKey | null>(null);

  const getCount = (dataType: DataTypeKey): number => {
    if (!stats) return 0;
    if (dataType === "price_bars") return stats.price_bars_count;
    if (dataType === "embeddings") return stats.embeddings_count;
    return stats.event_data_count;
  };

  const handleRefresh = async (dataType: DataTypeKey) => {
    setActiveType(dataType);
    try {
      const params: { data_type: string; company_id?: string } = {
        data_type: dataType,
      };
      if (dataType === "price_bars" && companyId.trim()) {
        params.company_id = companyId.trim();
      }
      const result = await refresh.mutateAsync(params);
      alert(
        `Cache refreshed: ${result.keys_deleted} key(s) deleted for "${dataType}".`
      );
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to refresh cache");
    } finally {
      setActiveType(null);
    }
  };

  if (isLoading) return <div data-testid="cache-loading">Loading...</div>;
  if (isError) return <div data-testid="cache-error">Failed to load cache stats</div>;

  return (
    <div data-testid="cache-inspection-tab">
      <h2>Cache Inspection</h2>

      {stats && (
        <div style={{ marginBottom: 16, color: "#6b7280" }}>
          Total Redis Memory:{" "}
          <strong>
            {(stats.total_redis_memory_bytes / 1024).toFixed(1)} KB
          </strong>
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th>Data Type</th>
            <th>Key Count</th>
            <th>Company ID (optional)</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {DATA_TYPES.map(({ key, label, companyScoped }) => (
            <tr key={key} data-testid={`cache-row-${key}`}>
              <td>{label}</td>
              <td data-testid={`key-count-${key}`}>{getCount(key)}</td>
              <td>
                {companyScoped && (
                  <input
                    data-testid="company-id-input"
                    type="text"
                    value={companyId}
                    onChange={(e) => setCompanyId(e.target.value)}
                    placeholder="UUID (leave blank for all)"
                    style={{ width: 260 }}
                  />
                )}
              </td>
              <td>
                <button
                  data-testid={`refresh-btn-${key}`}
                  onClick={() => handleRefresh(key)}
                  disabled={refresh.isPending && activeType === key}
                >
                  {refresh.isPending && activeType === key
                    ? "Refreshing..."
                    : "Force Refresh"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default CacheInspectionTab;
