/**
 * CompanyUniverseTab — tracked company list with promote/demote actions.
 *
 * - Paginated table of tracked companies
 * - "Remove from tracked" button per row (DELETE /track)
 * - "Add company" inline search bar (GET /companies/search?q=)
 * - Search results in dropdown; clicking calls POST /track
 *
 * PLAN-F-030 TASK-010
 */
import React, { useState, useCallback } from "react";
import {
  useTrackedCompanies,
  useUntrackCompany,
  useTrackCompany,
  useSearchCompanies,
} from "./hooks/useSystemOps";

let _debounceTimer: ReturnType<typeof setTimeout> | undefined;

export const CompanyUniverseTab: React.FC = () => {
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  const { data: companyList, isLoading } = useTrackedCompanies(page, 50);
  const { data: searchResults } = useSearchCompanies(debouncedQuery);
  const untrack = useUntrackCompany();
  const track = useTrackCompany();

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = e.target.value;
      setSearchQuery(val);
      if (_debounceTimer) clearTimeout(_debounceTimer);
      _debounceTimer = setTimeout(() => {
        setDebouncedQuery(val);
      }, 300);
    },
    []
  );

  const handleUntrack = async (companyId: string) => {
    try {
      await untrack.mutateAsync(companyId);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to untrack company");
    }
  };

  const handleTrack = async (companyId: string) => {
    try {
      await track.mutateAsync(companyId);
      setSearchQuery("");
      setDebouncedQuery("");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to track company");
    }
  };

  return (
    <div data-testid="company-universe-tab">
      <h2>Company Universe</h2>

      {/* Tracked companies table */}
      {isLoading ? (
        <div data-testid="companies-loading">Loading...</div>
      ) : (
        <>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Name</th>
                <th>Sector</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {(companyList?.items ?? []).map((company) => (
                <tr
                  key={company.company_id}
                  data-testid={`company-row-${company.company_id}`}
                >
                  <td>{company.ticker}</td>
                  <td>{company.name}</td>
                  <td>{company.sector_gics ?? "—"}</td>
                  <td>
                    <button
                      data-testid={`untrack-btn-${company.company_id}`}
                      onClick={() => handleUntrack(company.company_id)}
                      disabled={untrack.isPending}
                    >
                      Remove from tracked
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button
              data-testid="prev-page-btn"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </button>
            <span>
              Page {page} of{" "}
              {Math.ceil((companyList?.total ?? 0) / 50) || 1}
            </span>
            <button
              data-testid="next-page-btn"
              disabled={
                (companyList?.total ?? 0) <= page * 50
              }
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </>
      )}

      {/* Add company search */}
      <div style={{ marginTop: 24 }}>
        <h3>Add Company</h3>
        <p style={{ color: "#6b7280", fontSize: "0.875rem" }}>
          Company will be included in the next scheduled ingestion cycle.
        </p>
        <div style={{ position: "relative", display: "inline-block" }}>
          <input
            data-testid="company-search-input"
            type="text"
            value={searchQuery}
            onChange={handleSearchChange}
            placeholder="Search by name or ticker..."
            style={{ width: 280, padding: "4px 8px" }}
          />
          {searchResults && searchResults.length > 0 && debouncedQuery && (
            <div
              data-testid="search-dropdown"
              style={{
                position: "absolute",
                top: "100%",
                left: 0,
                right: 0,
                border: "1px solid #d1d5db",
                background: "#fff",
                zIndex: 100,
                maxHeight: 200,
                overflowY: "auto",
              }}
            >
              {searchResults.map((company) => (
                <div
                  key={company.company_id}
                  data-testid={`search-result-${company.company_id}`}
                  style={{ padding: "6px 8px", cursor: "pointer" }}
                  onClick={() => handleTrack(company.company_id)}
                  role="option"
                  aria-selected="false"
                >
                  <strong>{company.ticker}</strong> — {company.name}
                  {company.is_tracked && (
                    <span style={{ color: "#6b7280", marginLeft: 8 }}>
                      (already tracked)
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CompanyUniverseTab;
