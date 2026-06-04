/**
 * time-mode.types.ts — TypeScript types for the time-mode system.
 *
 * TimeMode, PlaybackSpeed, DateRange, ScoreAtTime, TimeModeContext are
 * pure data contracts with no logic and no React dependency.
 *
 * PLAN-F-021 TASK-001
 */

// ── Time mode ─────────────────────────────────────────────────────────────────

/** Active time-dimension mode for the Intelligence Map. */
export type TimeMode = 'live' | 'historical' | 'playback';

// ── Playback speed ────────────────────────────────────────────────────────────

/**
 * Playback speed multiplier expressed as a display label so it is directly
 * serializable as a URL query parameter without transformation.
 */
export type PlaybackSpeed = '1x' | '4x' | '16x';

// ── Date range ────────────────────────────────────────────────────────────────

/** ISO 8601 date range used by Historical and Playback modes. */
export interface DateRange {
  /** ISO 8601 date "YYYY-MM-DD" */
  from_date: string;
  /** ISO 8601 date "YYYY-MM-DD" */
  to_date: string;
}

// ── Score at time ─────────────────────────────────────────────────────────────

/**
 * Company score snapshot at or before a given point in time.
 * Returned by GET /api/v1/scores/history and drives company marker coloring
 * in Historical mode.
 */
export interface ScoreAtTime {
  company_id: string;
  indicator_id: string;
  /** Normalized score 0–100. */
  score: number;
  /** Geo-adjusted score 0–100. */
  geo_adjusted: number;
  /** ISO 8601 timestamp of the closest snapshot at or before the requested time. */
  computed_at: string;
}

// ── Time mode context ─────────────────────────────────────────────────────────

/**
 * Aggregated time-mode context passed from useTimeModeState into useEventFeed
 * and down to the score overlay. Separates time-mode concerns from spatial
 * map-mode concerns owned by useMapMode.
 */
export interface TimeModeContext {
  timeMode: TimeMode;
  dateRange: DateRange | null;
  playbackSpeed: PlaybackSpeed;
  /**
   * Current virtual cursor position within the playback window.
   * Set by PlaybackEngine in Playback mode; null in Live and Historical modes.
   */
  currentTick: Date | null;
}
