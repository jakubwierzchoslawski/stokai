/**
 * Tests for useSystemOps TanStack Query hooks.
 *
 * PLAN-F-030 TASK-009
 */

// Mock @tanstack/react-query before any import
jest.mock("@tanstack/react-query", () => {
  const actual = jest.requireActual("@tanstack/react-query");
  return {
    ...actual,
    useQuery: jest.fn(),
    useMutation: jest.fn(),
    useQueryClient: jest.fn(),
  };
});

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  useIngestionJobs,
  useTriggerJob,
  useCostSummary,
  useUpdateThreshold,
} from "../../../../frontend/src/pages/admin/system/hooks/useSystemOps";

const mockUseQuery = useQuery as jest.Mock;
const mockUseMutation = useMutation as jest.Mock;
const mockUseQueryClient = useQueryClient as jest.Mock;

const mockInvalidateQueries = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  mockUseQueryClient.mockReturnValue({
    invalidateQueries: mockInvalidateQueries,
  });
  mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isError: false });
  mockUseMutation.mockImplementation(({ onSuccess }) => ({
    mutateAsync: jest.fn().mockResolvedValue({}),
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
