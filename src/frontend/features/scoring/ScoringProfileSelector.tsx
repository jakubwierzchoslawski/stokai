/**
 * ScoringProfileSelector — dropdown/tab component for switching scoring profiles.
 *
 * - Fetches available profiles from GET /api/v1/scoring-profiles.
 * - Selecting a profile updates ActiveProfileContext and invalidates company score queries.
 * - Built-in profiles shown as pill badges; custom profiles listed below.
 * - Mounted in the top navigation bar, visible from the Intelligence Map.
 */
import React, { useCallback, createContext, useContext } from "react";
import { useQuery } from "@tanstack/react-query";
import { useActiveProfile } from "./hooks/useActiveProfile";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ScoringProfile {
  profile_id: string;
  name: string;
  is_builtin: boolean;
  version: number;
  indicators: Array<{ indicator_id: string; weight: number }>;
  tenant_id: string;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface ActiveProfileContextValue {
  activeProfileId: string | null;
  setActiveProfile: (profileId: string | null) => void;
}

export const ActiveProfileContext =
  createContext<ActiveProfileContextValue | null>(null);

export function ActiveProfileProvider({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  const { activeProfileId, setActiveProfile } = useActiveProfile();

  return (
    <ActiveProfileContext.Provider value={{ activeProfileId, setActiveProfile }}>
      {children}
    </ActiveProfileContext.Provider>
  );
}

export function useActiveProfileContext(): ActiveProfileContextValue {
  const ctx = useContext(ActiveProfileContext);
  if (ctx === null) {
    throw new Error(
      "useActiveProfileContext must be used within ActiveProfileProvider"
    );
  }
  return ctx;
}

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------

async function fetchScoringProfiles(): Promise<ScoringProfile[]> {
  const response = await fetch("/api/v1/scoring-profiles");
  if (!response.ok) {
    throw new Error(
      `Failed to load scoring profiles: HTTP ${response.status}`
    );
  }
  const json = await response.json();
  return json.data.profiles as ScoringProfile[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ScoringProfileSelectorProps {
  /** Optional class name for styling. */
  className?: string;
}

/**
 * Renders a profile selector control suitable for the navigation bar.
 *
 * Built-in profiles appear as distinct pill badges.
 * Custom profiles appear in the dropdown below the built-ins.
 */
export const ScoringProfileSelector: React.FC<ScoringProfileSelectorProps> = ({
  className = "",
}) => {
  const { activeProfileId, setActiveProfile } = useActiveProfileContext();

  const {
    data: profiles = [],
    isLoading,
    error,
  } = useQuery<ScoringProfile[], Error>({
    queryKey: ["scoring-profiles"],
    queryFn: fetchScoringProfiles,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const handleSelect = useCallback(
    (profileId: string): void => {
      setActiveProfile(profileId);
    },
    [setActiveProfile]
  );

  if (isLoading) {
    return (
      <div
        className={`scoring-profile-selector scoring-profile-selector--loading ${className}`}
        aria-busy="true"
        aria-label="Loading profiles"
      >
        <span>Loading profiles...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={`scoring-profile-selector scoring-profile-selector--error ${className}`}
        role="alert"
      >
        <span>Failed to load profiles</span>
      </div>
    );
  }

  const builtinProfiles = profiles.filter((p) => p.is_builtin);
  const customProfiles = profiles.filter((p) => !p.is_builtin);

  return (
    <div
      className={`scoring-profile-selector ${className}`}
      role="navigation"
      aria-label="Scoring Profile Selector"
    >
      {/* Built-in profile pill badges */}
      <div
        className="scoring-profile-selector__builtins"
        role="group"
        aria-label="Built-in profiles"
      >
        {builtinProfiles.map((profile) => (
          <button
            key={profile.profile_id}
            className={`scoring-profile-selector__pill ${
              activeProfileId === profile.profile_id
                ? "scoring-profile-selector__pill--active"
                : ""
            }`}
            onClick={() => handleSelect(profile.profile_id)}
            aria-pressed={activeProfileId === profile.profile_id}
            aria-label={`Select profile: ${profile.name}`}
          >
            {profile.name}
          </button>
        ))}
      </div>

      {/* Custom profile dropdown */}
      {customProfiles.length > 0 && (
        <div className="scoring-profile-selector__custom">
          <label
            htmlFor="custom-profile-select"
            className="scoring-profile-selector__label"
          >
            Custom:
          </label>
          <select
            id="custom-profile-select"
            className="scoring-profile-selector__select"
            value={
              customProfiles.some((p) => p.profile_id === activeProfileId)
                ? (activeProfileId ?? "")
                : ""
            }
            onChange={(e) => {
              if (e.target.value) {
                handleSelect(e.target.value);
              }
            }}
            aria-label="Select custom profile"
          >
            <option value="">-- Select custom --</option>
            {customProfiles.map((profile) => (
              <option key={profile.profile_id} value={profile.profile_id}>
                {profile.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {profiles.length === 0 && (
        <span className="scoring-profile-selector__empty">
          No profiles available
        </span>
      )}
    </div>
  );
};

export default ScoringProfileSelector;
