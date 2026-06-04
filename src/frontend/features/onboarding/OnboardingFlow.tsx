/**
 * features/onboarding/OnboardingFlow — 3-step onboarding wizard.
 *
 * Step 1: Choose scoring profile (3 presets: Value Investor, Growth Hunter, Macro Aware).
 *         Next is disabled until a profile is selected.
 *         POST /api/v1/onboarding/profile on advance.
 *
 * Step 2: Add first holdings (PositionList edit mode + CSV upload).
 *         Next enabled only when has_holding=true.
 *         "Skip for now" → POST /api/v1/onboarding/skip → navigate to /.
 *
 * Step 3: Preview screen + "Go to Map" → navigate to /.
 *
 * AC-001: First-time user → onboarding flow; cannot navigate to map until
 *         holding added or skip clicked.
 * PLAN-F-024 TASK-009
 */
import React, { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';

// ── Types ──────────────────────────────────────────────────────────────────────

interface ScoringProfile {
  id: string;
  label: string;
  description: string;
}

const PRESET_PROFILES: ScoringProfile[] = [
  {
    id: 'value-investor',
    label: 'Value Investor',
    description: 'Focus on undervalued companies with strong fundamentals.',
  },
  {
    id: 'growth-hunter',
    label: 'Growth Hunter',
    description: 'Target high-growth companies in emerging markets.',
  },
  {
    id: 'macro-aware',
    label: 'Macro Aware',
    description: 'Factor in macroeconomic trends and geopolitical events.',
  },
];

interface OnboardingFlowProps {
  onComplete?: () => void;
}

// ── API helpers ────────────────────────────────────────────────────────────────

async function selectProfile(profileId: string): Promise<void> {
  const resp = await fetch('/api/v1/onboarding/profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ profile_id: profileId }),
  });
  if (!resp.ok) throw new Error('Failed to select profile');
}

async function skipOnboarding(): Promise<void> {
  const resp = await fetch('/api/v1/onboarding/skip', {
    method: 'POST',
    credentials: 'include',
  });
  if (!resp.ok) throw new Error('Failed to skip onboarding');
}

async function fetchOnboardingState(): Promise<{ has_holding: boolean }> {
  const resp = await fetch('/api/v1/onboarding/state', { credentials: 'include' });
  if (!resp.ok) throw new Error('Failed to fetch onboarding state');
  const body = await resp.json();
  return body.data;
}

// ── Component ──────────────────────────────────────────────────────────────────

export function OnboardingFlow({ onComplete }: OnboardingFlowProps): React.ReactElement {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);

  // Check whether user has a holding (for Step 2 gate)
  const { data: onboardingState, refetch: refetchState } = useQuery({
    queryKey: ['onboarding-state'],
    queryFn: fetchOnboardingState,
    enabled: step === 2,
  });

  const profileMutation = useMutation<void, Error, string>({
    mutationFn: selectProfile,
    onSuccess: () => setStep(2),
  });

  const skipMutation = useMutation<void, Error, void>({
    mutationFn: skipOnboarding,
    onSuccess: () => {
      if (onComplete) onComplete();
    },
  });

  // Step 1 ─────────────────────────────────────────────────────────────────────

  if (step === 1) {
    return (
      <div data-testid="onboarding-step-1">
        <h1>Choose your investing style</h1>
        <div data-testid="profile-cards">
          {PRESET_PROFILES.map((profile) => (
            <button
              key={profile.id}
              type="button"
              data-testid={`profile-card-${profile.id}`}
              aria-pressed={selectedProfileId === profile.id}
              onClick={() => setSelectedProfileId(profile.id)}
              style={{
                border: selectedProfileId === profile.id ? '2px solid blue' : '1px solid gray',
              }}
            >
              <strong>{profile.label}</strong>
              <p>{profile.description}</p>
            </button>
          ))}
        </div>
        <button
          type="button"
          data-testid="step1-next"
          disabled={selectedProfileId === null || profileMutation.isPending}
          onClick={() => {
            if (selectedProfileId) {
              profileMutation.mutate(selectedProfileId);
            }
          }}
        >
          Next
        </button>
      </div>
    );
  }

  // Step 2 ─────────────────────────────────────────────────────────────────────

  if (step === 2) {
    const hasHolding = onboardingState?.has_holding === true;

    return (
      <div data-testid="onboarding-step-2">
        <h1>Add your first holdings</h1>
        <p>Add at least one stock to your portfolio to continue.</p>

        {/* Placeholder for PositionList edit mode and CSV upload */}
        <div data-testid="position-editor">
          <button
            type="button"
            onClick={() => refetchState()}
          >
            Refresh
          </button>
        </div>

        <div>
          <button
            type="button"
            data-testid="step2-next"
            disabled={!hasHolding}
            onClick={() => setStep(3)}
          >
            Next
          </button>
          <button
            type="button"
            data-testid="step2-skip"
            onClick={() => skipMutation.mutate()}
          >
            Skip for now
          </button>
        </div>
      </div>
    );
  }

  // Step 3 ─────────────────────────────────────────────────────────────────────

  return (
    <div data-testid="onboarding-step-3">
      <h1>You're all set!</h1>
      <p>Your portfolio is ready. Head to the map to see geopolitical events affecting your holdings.</p>
      <button
        type="button"
        data-testid="go-to-map"
        onClick={() => {
          if (onComplete) onComplete();
        }}
      >
        Go to Map
      </button>
    </div>
  );
}

export default OnboardingFlow;
