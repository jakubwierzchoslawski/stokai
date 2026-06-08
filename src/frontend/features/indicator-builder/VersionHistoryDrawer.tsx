/**
 * VersionHistoryDrawer — version history panel with DSL diff view.
 *
 * - Lists indicator versions with created_at timestamps.
 * - Shows token-level diff between selected versions (green=added, red=removed).
 * - Rollback button triggers POST /indicators/{id}/rollback.
 */
import React, { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

interface IndicatorVersion {
  version_id: string;
  indicator_id: string;
  version: number;
  formula_dsl: string;
  diff_tokens: string[];
  created_at: string;
}

interface VersionHistoryDrawerProps {
  indicatorId: string;
  isOpen: boolean;
  onClose: () => void;
}

async function fetchVersions(indicatorId: string): Promise<IndicatorVersion[]> {
  const response = await fetch(`/api/v1/indicators/${indicatorId}/versions`);
  if (!response.ok) {
    throw new Error(`Failed to load versions: HTTP ${response.status}`);
  }
  const json = await response.json();
  return json.data.versions as IndicatorVersion[];
}

async function rollbackVersion(
  indicatorId: string,
  targetVersion: number
): Promise<void> {
  const response = await fetch(
    `/api/v1/indicators/${indicatorId}/rollback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_version: targetVersion }),
    }
  );
  if (!response.ok) {
    throw new Error(`Rollback failed: HTTP ${response.status}`);
  }
}

interface DiffToken {
  token: string;
  type: "added" | "removed" | "unchanged";
}

function parseDiffTokens(diffTokens: string[]): DiffToken[] {
  return diffTokens.map((raw) => {
    if (raw.startsWith("+")) {
      return { token: raw.slice(1), type: "added" };
    } else if (raw.startsWith("-")) {
      return { token: raw.slice(1), type: "removed" };
    } else {
      return { token: raw.slice(1), type: "unchanged" };
    }
  });
}

export const VersionHistoryDrawer: React.FC<VersionHistoryDrawerProps> = ({
  indicatorId,
  isOpen,
  onClose,
}) => {
  const [selectedVersion, setSelectedVersion] =
    useState<IndicatorVersion | null>(null);
  const queryClient = useQueryClient();

  const {
    data: versions = [],
    isLoading,
    error,
  } = useQuery<IndicatorVersion[], Error>({
    queryKey: ["indicator-versions", indicatorId],
    queryFn: () => fetchVersions(indicatorId),
    enabled: isOpen,
  });

  const rollbackMutation = useMutation({
    mutationFn: (targetVersion: number) =>
      rollbackVersion(indicatorId, targetVersion),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["indicator-versions", indicatorId] });
      queryClient.invalidateQueries({ queryKey: ["indicators"] });
    },
  });

  const handleRollback = useCallback(
    (version: IndicatorVersion) => {
      if (
        window.confirm(
          `Roll back to version ${version.version}? This will create a new version.`
        )
      ) {
        rollbackMutation.mutate(version.version);
      }
    },
    [rollbackMutation]
  );

  if (!isOpen) return null;

  const diffTokens = selectedVersion
    ? parseDiffTokens(selectedVersion.diff_tokens)
    : [];

  return (
    <aside
      className="version-history-drawer"
      role="complementary"
      aria-label="Version History"
    >
      <div className="version-history-drawer__header">
        <h3>Version History</h3>
        <button
          onClick={onClose}
          aria-label="Close version history"
          className="version-history-drawer__close"
        >
          ×
        </button>
      </div>

      {isLoading && <p>Loading versions...</p>}

      {error && (
        <p role="alert" className="version-history-drawer__error">
          {error.message}
        </p>
      )}

      <ul className="version-history-drawer__list" role="list">
        {versions.map((version) => (
          <li
            key={version.version_id}
            className={`version-history-drawer__item ${
              selectedVersion?.version_id === version.version_id
                ? "version-history-drawer__item--selected"
                : ""
            }`}
            role="listitem"
          >
            <button
              className="version-history-drawer__version-btn"
              onClick={() =>
                setSelectedVersion(
                  selectedVersion?.version_id === version.version_id
                    ? null
                    : version
                )
              }
              aria-pressed={
                selectedVersion?.version_id === version.version_id
              }
            >
              <span className="version-history-drawer__version-number">
                v{version.version}
              </span>
              <span className="version-history-drawer__version-date">
                {new Date(version.created_at).toLocaleString()}
              </span>
            </button>

            <button
              className="version-history-drawer__rollback-btn"
              onClick={() => handleRollback(version)}
              disabled={rollbackMutation.isPending}
              aria-label={`Rollback to version ${version.version}`}
            >
              Rollback
            </button>
          </li>
        ))}
      </ul>

      {selectedVersion && diffTokens.length > 0 && (
        <div className="version-history-drawer__diff" aria-label="DSL diff">
          <h4>Changes in v{selectedVersion.version}</h4>
          <pre className="version-history-drawer__diff-view">
            {diffTokens.map((dt, index) => (
              <span
                key={index}
                className={`version-history-drawer__diff-token version-history-drawer__diff-token--${dt.type}`}
                style={{
                  color:
                    dt.type === "added"
                      ? "#22c55e"
                      : dt.type === "removed"
                      ? "#ef4444"
                      : "inherit",
                  backgroundColor:
                    dt.type === "added"
                      ? "#dcfce7"
                      : dt.type === "removed"
                      ? "#fee2e2"
                      : "transparent",
                  padding: "0 2px",
                }}
              >
                {dt.token}{" "}
              </span>
            ))}
          </pre>
        </div>
      )}

      {rollbackMutation.isError && (
        <p role="alert" className="version-history-drawer__error">
          Rollback failed: {(rollbackMutation.error as Error).message}
        </p>
      )}
    </aside>
  );
};

export default VersionHistoryDrawer;
