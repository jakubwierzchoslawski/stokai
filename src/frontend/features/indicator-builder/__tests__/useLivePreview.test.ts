import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
/**
 * Tests for useLivePreview hook.
 *
 * Verifies:
 * - 500ms debounce before calling /preview
 * - Returns 5 company preview rows on success
 * - Shows loading state during in-flight requests
 */
import { renderHook, act, waitFor } from "@testing-library/react";
import { useLivePreview } from "../hooks/useLivePreview";

vi.mock("@tanstack/react-query", async () => {
  const original = await vi.importActual("@tanstack/react-query");
  return {
    ...(original as object),
    useQuery: vi.fn(),
    useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
  };
});

import { useQuery as _useQuery } from '@tanstack/react-query';
const useQuery = vi.mocked(_useQuery);

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});
