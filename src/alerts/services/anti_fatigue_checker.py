"""
AntiFatigueChecker — stateless four-gate suppression chain.

Gates evaluated in order:
1. Daily limit
2. Quiet hours (supports overnight ranges)
3. Per-ticker re-alert interval
4. Deduplication window

Returns None when all gates pass, or the first failing AlertStatus.
"""
from __future__ import annotations

from datetime import datetime, timedelta, time

from src.alerts.models import AlertRuleRow, AntiFatigueState, AlertStatus


class AntiFatigueChecker:
    """Stateless service that applies four suppression gates in sequence.

    No constructor dependencies — all state is passed to *check()* at
    call time to keep this class easily testable and side-effect free.
    """

    def check(
        self,
        rule: AlertRuleRow,
        fatigue_state: AntiFatigueState,
        event_time_utc: datetime,
        matched_tickers: list[str],
    ) -> AlertStatus | None:
        """Evaluate suppression gates in order.

        Args:
            rule: The alert rule containing gate thresholds.
            fatigue_state: Snapshot of the user's current fatigue counters.
            event_time_utc: UTC timestamp of the triggering event.
            matched_tickers: Tickers from the event that matched the rule.

        Returns:
            None if all gates pass (alert may proceed to dispatch).
            First failing AlertStatus otherwise.
        """
        # Gate 1: Daily limit
        if fatigue_state.dispatched_today >= rule.daily_limit:
            return AlertStatus.SUPPRESSED_DAILY_LIMIT

        # Gate 2: Quiet hours
        if rule.quiet_hours_start is not None and rule.quiet_hours_end is not None:
            if self._is_in_quiet_hours(
                event_time_utc.timetz().replace(tzinfo=None),
                rule.quiet_hours_start,
                rule.quiet_hours_end,
            ):
                return AlertStatus.SUPPRESSED_QUIET_HOURS

        # Gate 3: Per-ticker interval
        if fatigue_state.last_ticker_dispatch is not None and matched_tickers:
            interval = timedelta(hours=rule.per_ticker_interval_hours)
            last = fatigue_state.last_ticker_dispatch
            # Ensure comparable (both UTC)
            if last.tzinfo is None:
                from datetime import timezone
                last = last.replace(tzinfo=timezone.utc)
            if event_time_utc.tzinfo is None:
                from datetime import timezone
                event_time_utc = event_time_utc.replace(tzinfo=timezone.utc)
            if event_time_utc - last < interval:
                return AlertStatus.SUPPRESSED_TICKER_INTERVAL

        # Gate 4: Deduplication window
        if len(fatigue_state.recent_event_alert_ids) > 0:
            return AlertStatus.SUPPRESSED_DEDUP

        return None

    # ── Private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _is_in_quiet_hours(
        event_time: time,
        quiet_start: time,
        quiet_end: time,
    ) -> bool:
        """Return True if *event_time* falls within [quiet_start, quiet_end).

        Handles overnight ranges where quiet_start > quiet_end (e.g. 22:00–06:00).

        Args:
            event_time: Time component of the event (timezone-naive).
            quiet_start: Start of quiet window.
            quiet_end: End of quiet window.

        Returns:
            True when the event falls within the quiet period.
        """
        if quiet_start <= quiet_end:
            # Same-day window: e.g. 23:00–23:30
            return quiet_start <= event_time < quiet_end
        else:
            # Overnight window: e.g. 22:00–06:00
            return event_time >= quiet_start or event_time < quiet_end
