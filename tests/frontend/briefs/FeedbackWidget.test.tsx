import { describe, it, expect, vi , type Mock } from 'vitest';
/**
 * Tests for FeedbackWidget and useFeedback hook (PLAN-F-026 TASK-007).
 *
 * TDD â€” written before implementation.
 * Covers AC-002 (thumbs-down fires feedback) and AC-003 (edit correction).
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// â”€â”€ Mock useFeedback hook â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
vi.mock('../../../src/frontend/features/briefs/hooks/useFeedback', () => ({
  useFeedback: vi.fn(),
}));

import { useFeedback } from '../../../src/frontend/features/briefs/hooks/useFeedback';
import { FeedbackWidget } from '../../../src/frontend/features/briefs/FeedbackWidget';

const mockUseFeedback = useFeedback as Mock;

const BRIEF_ID = 'test-brief-id-456';

function makeMockMutation(overrides: Record<string, unknown> = {}) {
  const mutateFn = vi.fn();
  return {
    mutate: mutateFn,
    isSuccess: false,
    isError: false,
    isPending: false,
    ...overrides,
  };
}

describe('FeedbackWidget', () => {
  it('test_thumbs_down_calls_feedback_mutation_with_correct_payload', () => {
    const mutation = makeMockMutation();
    mockUseFeedback.mockReturnValue(mutation);

    render(<FeedbackWidget briefId={BRIEF_ID} />);

    fireEvent.click(screen.getByTestId('feedback-thumbs-down'));

    expect(mutation.mutate).toHaveBeenCalledWith({ feedback_type: 'thumbs_down' });
    // No correction field
    const callArg = mutation.mutate.mock.calls[0][0];
    expect(callArg.correction).toBeUndefined();
  });

  it('test_edit_button_expands_textarea', () => {
    const mutation = makeMockMutation();
    mockUseFeedback.mockReturnValue(mutation);

    render(<FeedbackWidget briefId={BRIEF_ID} />);

    // Textarea should not be visible initially
    expect(screen.queryByTestId('feedback-correction-textarea')).not.toBeInTheDocument();

    // Click edit button
    fireEvent.click(screen.getByTestId('feedback-edit-btn'));

    // Textarea should now be visible
    expect(screen.getByTestId('feedback-correction-textarea')).toBeInTheDocument();
  });

  it('test_submit_correction_calls_mutation_with_edit_type', async () => {
    const mutation = makeMockMutation();
    mockUseFeedback.mockReturnValue(mutation);

    render(<FeedbackWidget briefId={BRIEF_ID} />);

    // Open edit form
    fireEvent.click(screen.getByTestId('feedback-edit-btn'));

    // Type correction
    const textarea = screen.getByTestId('feedback-correction-textarea');
    fireEvent.change(textarea, { target: { value: 'correction text' } });

    // Submit
    fireEvent.click(screen.getByTestId('feedback-submit-correction'));

    expect(mutation.mutate).toHaveBeenCalledWith({
      feedback_type: 'edit',
      correction: 'correction text',
    });
  });

  it('test_empty_correction_blocked_client_side', () => {
    const mutation = makeMockMutation();
    mockUseFeedback.mockReturnValue(mutation);

    render(<FeedbackWidget briefId={BRIEF_ID} />);

    // Open edit form
    fireEvent.click(screen.getByTestId('feedback-edit-btn'));

    // Leave textarea empty and submit
    fireEvent.click(screen.getByTestId('feedback-submit-correction'));

    // Mutation must NOT be called
    expect(mutation.mutate).not.toHaveBeenCalled();

    // Validation message must be visible
    expect(screen.getByTestId('feedback-validation-error')).toBeInTheDocument();
  });

  it('test_successful_thumbs_up_shows_confirmation_state', () => {
    const mutation = makeMockMutation({ isSuccess: true });
    mockUseFeedback.mockReturnValue(mutation);

    render(<FeedbackWidget briefId={BRIEF_ID} />);

    // Click thumbs up
    fireEvent.click(screen.getByTestId('feedback-thumbs-up'));

    // Button should show confirmed state class
    const thumbsUpBtn = screen.getByTestId('feedback-thumbs-up');
    expect(thumbsUpBtn.className).toContain('feedback-widget__btn--confirmed');
  });
});
