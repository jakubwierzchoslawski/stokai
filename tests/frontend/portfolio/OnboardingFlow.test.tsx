/**
 * tests/frontend/portfolio/OnboardingFlow.test.tsx
 *
 * Tests for OnboardingFlow and route guard.
 * PLAN-F-024 TASK-009
 */
import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { OnboardingFlow } from '../../../src/frontend/features/onboarding/OnboardingFlow';
import { ProtectedRoute } from '../../../src/frontend/app/routes';

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  mockFetch.mockReset();
});

// ── OnboardingFlow tests ───────────────────────────────────────────────────────

describe('OnboardingFlow', () => {
  test('test_onboarding_step1_next_disabled_until_profile_selected', () => {
    render(<OnboardingFlow />, { wrapper });

    const nextBtn = screen.getByTestId('step1-next');
    expect(nextBtn).toBeDisabled();
  });

  test('test_onboarding_step1_selects_profile_and_advances', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { profile_id: 'value-investor' } }),
    });

    render(<OnboardingFlow />, { wrapper });

    // Select a profile
    await userEvent.click(screen.getByTestId('profile-card-value-investor'));

    // Next button should now be enabled
    const nextBtn = screen.getByTestId('step1-next');
    expect(nextBtn).not.toBeDisabled();

    // Click next → should advance to step 2
    // Mock the onboarding/state fetch for step 2
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { has_holding: false } }),
    });

    await userEvent.click(nextBtn);

    await waitFor(() => {
      expect(screen.getByTestId('onboarding-step-2')).toBeInTheDocument();
    });
  });

  test('test_onboarding_step2_skip_navigates_to_map', async () => {
    const onComplete = jest.fn();

    // Mock profile select (step 1 → 2)
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: {} }),
      })
      // Mock state fetch for step 2
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: { has_holding: false } }),
      })
      // Mock skip call
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: { skipped: true } }),
      });

    render(<OnboardingFlow onComplete={onComplete} />, { wrapper });

    // Select profile and advance
    await userEvent.click(screen.getByTestId('profile-card-growth-hunter'));
    await userEvent.click(screen.getByTestId('step1-next'));

    await waitFor(() => {
      expect(screen.getByTestId('onboarding-step-2')).toBeInTheDocument();
    });

    // Click skip
    await userEvent.click(screen.getByTestId('step2-skip'));

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalled();
    });
  });

  test('test_onboarding_step2_next_disabled_until_holding', async () => {
    // Mock profile select
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: {} }),
      })
      // Mock state fetch — no holding
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: { has_holding: false } }),
      });

    render(<OnboardingFlow />, { wrapper });

    await userEvent.click(screen.getByTestId('profile-card-macro-aware'));
    await userEvent.click(screen.getByTestId('step1-next'));

    await waitFor(() => {
      expect(screen.getByTestId('onboarding-step-2')).toBeInTheDocument();
    });

    expect(screen.getByTestId('step2-next')).toBeDisabled();
  });
});

// ── Route guard tests ──────────────────────────────────────────────────────────

describe('ProtectedRoute', () => {
  test('test_route_guard_redirects_to_onboarding', async () => {
    // is_onboarding_required = true (not complete, not skipped, no holding)
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: { is_complete: false, skipped: false, has_holding: false },
      }),
    });

    render(
      <ProtectedRoute>
        <div data-testid="protected-content">Map content</div>
      </ProtectedRoute>,
      { wrapper }
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('route-guard-redirect-onboarding')
      ).toBeInTheDocument();
    });
  });

  test('test_route_guard_allows_map_when_complete', async () => {
    // is_complete = true → no redirect
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: { is_complete: true, skipped: false, has_holding: true },
      }),
    });

    render(
      <ProtectedRoute>
        <div data-testid="protected-content">Map content</div>
      </ProtectedRoute>,
      { wrapper }
    );

    await waitFor(() => {
      expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    });
  });
});
