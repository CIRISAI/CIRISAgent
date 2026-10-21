"""Collapse identical consecutive log lines into "… repeated N times".

WHY. A user's `latest.log` covering 3m40s of runtime ran to 3,810 lines. The
fault he actually had — `401 Invalid API Key` — was in there, thirteen times,
buried under thousands of lines of per-round chatter. A log that long is not
read; it is grepped by someone who already knows what to look for, which is
exactly the person who does not need it.

The classic syslog behaviour is the right one here, and it is safe under this
codebase's rule that logs must explain failures:

  - the FIRST occurrence always emits, in full, unchanged
  - only exact repeats are held back
  - the count is always reported, so nothing is silently dropped

An error that happens 200 times still appears, and the reader learns something
they did not have before: that it happened 200 times rather than once.

DELIBERATELY EXACT-MATCH. It would be easy to collapse on the format template
instead and catch near-repeats too — but then "Fetching messages from channel: A"
and "… channel: B" become one line and a real distinction disappears. Exact
matching can only ever collapse lines that were genuinely identical, so it cannot
hide a fact. Under-collapsing is recoverable; over-collapsing loses evidence.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple


class RepeatCollapsingFilter(logging.Filter):
    """Suppress identical consecutive records, reporting the count instead.

    Attach to a HANDLER, not a logger: handlers are where records become lines,
    and a logger-level filter would also hide the record from other handlers
    that may want it.

    Args:
        max_hold_seconds: emit a running "repeated N times" note at least this
            often during a long streak, so a stuck agent still shows a heartbeat
            rather than going completely silent.
        min_repeats: how many identical lines must pile up before collapsing.
            2 means the second identical line is already held.
    """

    def __init__(self, max_hold_seconds: float = 30.0, min_repeats: int = 2) -> None:
        super().__init__()
        self._key: Optional[Tuple[str, int, str]] = None
        self._count = 0
        self._first_at = 0.0
        self._last_report_at = 0.0
        self.max_hold_seconds = max_hold_seconds
        self.min_repeats = max(2, min_repeats)
        # Emitting the summary re-enters this filter through the same handler.
        # It terminates today only because the summary text differs from what it
        # summarises — which is true but fragile, and logging is the last place
        # that should be able to recurse. The guard makes it structural.
        self._emitting = False

    @staticmethod
    def _key_for(record: logging.LogRecord) -> Tuple[str, int, str]:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - a broken record must not break logging
            message = str(record.msg)
        return (record.name, record.levelno, message)

    def _summary(self, record: logging.LogRecord, count: int) -> None:
        """Rewrite `record` in place into the repeat summary.

        Reusing the record keeps the logger name, level and timestamp of the
        line being summarised, so the summary appears exactly where the streak
        ended and at the same severity — an ERROR repeated 200 times must not be
        summarised at INFO.
        """
        record.msg = "%s  [previous message repeated %d more time%s over %.0fs]"
        record.args = (
            self._key[2] if self._key else "",
            count,
            "" if count == 1 else "s",
            max(0.0, time.monotonic() - self._first_at),
        )

    def filter(self, record: logging.LogRecord) -> bool:
        key = self._key_for(record)
        now = time.monotonic()

        # A different line: flush any streak we were holding, then let it through.
        if key != self._key:
            held = self._count
            prev_key = self._key
            self._key = key
            self._count = 0
            self._first_at = now
            self._last_report_at = now

            if held >= self._min_held() and prev_key is not None and not self._emitting:
                # Emit the summary for the streak that just ended, through the
                # same logger so it lands in the same place.
                self._emitting = True
                try:
                    logging.getLogger(prev_key[0]).log(
                        prev_key[1],
                        "%s  [repeated %d more time%s]",
                        prev_key[2],
                        held,
                        "" if held == 1 else "s",
                    )
                finally:
                    self._emitting = False
            return True

        # Same line as last time.
        self._count += 1
        if self._count < self._min_held():
            return True

        # Long streak: report periodically so a stuck loop is still visible.
        if now - self._last_report_at >= self.max_hold_seconds:
            self._last_report_at = now
            self._summary(record, self._count)
            self._count = 0
            self._first_at = now
            return True

        return False

    def _min_held(self) -> int:
        return self.min_repeats - 1
