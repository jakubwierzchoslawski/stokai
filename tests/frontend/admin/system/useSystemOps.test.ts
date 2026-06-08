import { describe, it, expect, vi, beforeEach , type Mock } from 'vitest';
/**
 * Tests for useSystemOps TanStack Query hooks.
 *
 * PLAN-F-030 TASK-009
 */

// Mock @tanstack/react-query before any import
vi.mock("@tanstack/react-query", () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return {
    ...actual,
    useQuery: vi.fn(),
    useMutation: vi.fn(),
    useQueryClient: vi.fn(),
  };
});

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  useIngestionJobs,
  useTriggerJob,
  useCostSummary,
  useUpdateThreshold,
} from "@/pages/admin/system/hooks/useSystemOps";

const mockUseQuery = useQuery as Mock;
const mockUseMutation = useMutation as Mock;
const mockUseQueryClient = useQueryClient as Mock;

const mockInvalidateQueries = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockUseQueryClient.mockReturnValue({
    invalidateQueries: mockInvalidateQueries,
  });
  mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isError: false });
  mockUseMutation.mockImplementation(({ onSuccess }) => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
    _onSuccess: onSuccess,
  }));
});

describe("useSystemOps hooks", () => {
  describe("useIngestionJobs", () => {
    it("calls useQuery with correct queryKey", () => {
      useIngestionJobs();
      expect(mockUseQuery).toHaveBeenCalledWith(
        expect.objectContaining({
          queryKey: ["admin", "system", "jobs"],
        })
      );
    });
  });

  describe("useTriggerJob", () => {
    it("calls useMutation with onSuccess that invalidates jobs query", () => {
      useTriggerJob();
      expect(mockUseMutation).toHaveBeenCalledWith(
        expect.objectContaining({
          onSuccess: expect.any(Function),
        })
      );

      // Call onSuccess and verify invalidateQueries is invoked
      const callArgs = mockUseMutation.mock.calls[0][0];
      callArgs.onSuccess();
      expect(mockInvalidateQueries).toHaveBeenCalledWith({
        queryKey: ["admin", "system", "jobs"],
      });
    });
  });

  describe("useCostSummary", () => {
    it("calls useQuery with correct queryKey", () => {
      useCostSummary();
      expect(mockUseQuery).toHaveBeenCalledWith(
        expect.objectContaining({
          queryKey: ["admin", "system", "cost"],
        })
      );
    });
  });

  describe("useUpdateThreshold", () => {
    it("calls useMutation with onSuccess that invalidates cost query", () => {
      useUpdateThreshold();
      const callArgs = mockUseMutation.mock.calls[0][0];
      callArgs.onSuccess();
      expect(mockInvalidateQueries).toHaveBeenCalledWith({
        queryKey: ["admin", "system", "cost"],
      });
    });
  });
});
