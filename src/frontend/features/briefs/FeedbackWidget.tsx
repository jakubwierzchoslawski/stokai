/**
 * FeedbackWidget — thumbs-up / thumbs-down / edit feedback controls.
 *
 * Renders three controls for brief feedback. Edit expands an inline textarea.
 * Calls useFeedback mutation on submission.
 *
 * PLAN-F-026 TASK-007
 */
import React, { useState } from 'react';
import { useFeedback } from './hooks/useFeedback';

interface FeedbackWidgetProps {
  briefId: string;
}

type FeedbackState = 'idle' | 'thumbs_up' | 'thumbs_down' | 'edit';

export function FeedbackWidget({ briefId }: FeedbackWidgetProps): React.ReactElement {
  const [feedbackState, setFeedbackState] = useState<FeedbackState>('idle');
  const [correction, setCorrection] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  const mutation = useFeedback(briefId);

  function handleThumbsUp(): void {
    setFeedbackState('thumbs_up');
    mutation.mutate({ feedback_type: 'thumbs_up' });
  }

  function handleThumbsDown(): void {
    setFeedbackState('thumbs_down');
    mutation.mutate({ feedback_type: 'thumbs_down' });
  }

  function handleEditClick(): void {
    setFeedbackState('edit');
    setCorrection('');
    setValidationError(null);
  }

  function handleCancelEdit(): void {
    setFeedbackState('idle');
    setCorrection('');
    setValidationError(null);
  }

  function handleSubmitCorrection(): void {
    if (!correction.trim()) {
      setValidationError('Correction text cannot be empty.');
      return;
    }
    setValidationError(null);
    mutation.mutate({ feedback_type: 'edit', correction });
  }

  const isSuccess = mutation.isSuccess;

  return (
    <div className="feedback-widget" data-testid="feedback-widget">
      <div className="feedback-widget__controls">
        <button
          className={`feedback-widget__btn feedback-widget__btn--thumbs-up${
            feedbackState === 'thumbs_up' && isSuccess
              ? ' feedback-widget__btn--confirmed'
              : ''
          }`}
          onClick={handleThumbsUp}
          aria-label="Thumbs up"
          data-testid="feedback-thumbs-up"
        >
          {feedbackState === 'thumbs_up' && isSuccess ? '✓' : '👍'}
        </button>

        <button
          className={`feedback-widget__btn feedback-widget__btn--thumbs-down${
            feedbackState === 'thumbs_down' && isSuccess
              ? ' feedback-widget__btn--confirmed'
              : ''
          }`}
          onClick={handleThumbsDown}
          aria-label="Thumbs down"
          data-testid="feedback-thumbs-down"
        >
          {feedbackState === 'thumbs_down' && isSuccess ? '✓' : '👎'}
        </button>

        <button
          className="feedback-widget__btn feedback-widget__btn--edit"
          onClick={handleEditClick}
          aria-label="Suggest correction"
          data-testid="feedback-edit-btn"
        >
          ✏️
        </button>
      </div>

      {feedbackState === 'edit' && (
        <div className="feedback-widget__edit-form" data-testid="feedback-edit-form">
          <textarea
            className="feedback-widget__textarea"
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            placeholder="Describe the correction..."
            data-testid="feedback-correction-textarea"
          />
          {validationError && (
            <p
              className="feedback-widget__validation-error"
              role="alert"
              data-testid="feedback-validation-error"
            >
              {validationError}
            </p>
          )}
          <div className="feedback-widget__edit-actions">
            <button
              className="feedback-widget__submit-btn"
              onClick={handleSubmitCorrection}
              data-testid="feedback-submit-correction"
            >
              Submit correction
            </button>
            <button
              className="feedback-widget__cancel-link"
              onClick={handleCancelEdit}
              data-testid="feedback-cancel-edit"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default FeedbackWidget;
