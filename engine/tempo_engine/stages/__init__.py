"""Pipeline stages (notebook cells f98b5375–da236107), one module per stage.

Every stage takes `progress(done, total)` and reports real units only
(AGENTS.md F4): frames scanned, frames embedded, audio seconds, keyframes,
cluster reps, steps.
"""

from collections.abc import Callable

Progress = Callable[[int, int], None]
