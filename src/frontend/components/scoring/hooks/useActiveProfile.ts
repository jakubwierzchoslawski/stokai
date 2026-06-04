/**
 * useActiveProfile — persists selected scoring profile_id in localStorage
 * and exposes it to the rest of the UI.
 *
 * Calling setActiveProfile(id):
 *  1. Updates React state (triggers re-renders).
 *  2. Persists value to localStorage under STORAGE_KEY.
 *  3. Invalidates all TanStack Query company score queries so the map refreshes.
 */
import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

const STORAGE_KEY = "stokai:active_profile_id";

function readFromStorage(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    // localStorage may be unavailable in certain environments (e.g. SSR)
    return null;
  }
}

function writeToStorage(profileId: string | null): void {
  try {
    if (profileId === null) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, profileId);
    }
  } catch {
    // Ignore localStorage write failures
  }
}

export interface UseActiveProfileReturn {
  /** Currently selected profile ID, or null if none selected. */
  activeProfileId: string | null;
  /** Set the active profile and persist it. */
  setActiveProfile: (profileId: string | null) => void;
}

/**
 * Hook that manages the active scoring profile selection.
 *
 * - Restores the last selected profile from localStorage on page load.
 * - On change, invalidates all company score TanStack Query caches so the
 *   Intelligence Map re-fetches with the new profile.
 */
export function useActiveProfile(): UseActiveProfileReturn {
  const [activeProfileId, setActiveProfileId] = useState<string | null>(
    () => readFromStorage()
  );
  const queryClient = useQueryClient();

  const setActiveProfile = useCallback(
    (profileId: string | null): void => {
      setActiveProfileId(profileId);
      writeToStorage(profileId);

      // Invalidate all company score queries so the map refreshes with the
      // scores from the new profile.
      queryClient.invalidateQueries({ queryKey: ["company-scores"] });
    },
    [queryClient]
  );

  return { activeProfileId, setActiveProfile };
}
