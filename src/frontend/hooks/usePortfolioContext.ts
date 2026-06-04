/**
 * hooks/usePortfolioContext — portfolio context utilities for cross-component coordination.
 *
 * Exports invalidatePortfolioContext() which:
 * 1. Invalidates the ['portfolio'] TanStack Query cache.
 * 2. Dispatches a custom DOM event 'portfolio:changed' for non-React consumers.
 *
 * PLAN-F-024 TASK-007
 */
import { useQueryClient } from '@tanstack/react-query';

export const PORTFOLIO_QUERY_KEY = ['portfolio'] as const;
export const PORTFOLIO_CHANGED_EVENT = 'portfolio:changed';

/**
 * Returns a stable callback that invalidates the portfolio query cache and
 * dispatches a 'portfolio:changed' DOM event.
 *
 * Usage:
 *   const invalidate = usePortfolioContext();
 *   await invalidate();
 */
export function usePortfolioContext(): () => void {
  const queryClient = useQueryClient();

  return function invalidatePortfolioContext(): void {
    queryClient.invalidateQueries({ queryKey: PORTFOLIO_QUERY_KEY });
    window.dispatchEvent(new CustomEvent(PORTFOLIO_CHANGED_EVENT));
  };
}
