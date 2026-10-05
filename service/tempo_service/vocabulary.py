"""The sidecar's closed state vocabularies (ADR-0021, AGENTS.md §3.4).

Every state string in the sidecar is declared here and imported from here. The
panel reads these too, and `service/tests/test_contracts.py` checks all three
copies against each other and against `docs/api.md`. A value that is not
declared here reaches the panel as a fallback sentence that names nothing,
which is why the sets are closed rather than documented.

`proxy.py` raises on an undeclared failure reason, so a new call site cannot
invent a fourth vocabulary.
"""

from typing import Literal, get_args

# --- job states -----------------------------------------------------------
# A sidecar job covers the whole handoff: upload plus the engine's stages.
JOB_QUEUED = "queued"
JOB_UPLOADING = "uploading"
JOB_QUEUED_FOR_BACKEND = "queued-for-backend"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_ERROR = "error"
JOB_CANCELLED = "cancelled"

JOB_STATES = (
    JOB_QUEUED, JOB_UPLOADING, JOB_QUEUED_FOR_BACKEND, JOB_RUNNING,
    JOB_DONE, JOB_ERROR, JOB_CANCELLED,
)
# States holding a claim on a footage key. A second enqueue for the same key
# must reuse the live job, never mint a duplicate full pipeline run.
JOB_ACTIVE_STATES = (JOB_QUEUED, JOB_UPLOADING, JOB_RUNNING, JOB_QUEUED_FOR_BACKEND)
JOB_TERMINAL_STATES = (JOB_DONE, JOB_ERROR, JOB_CANCELLED)

# --- footage states -------------------------------------------------------
# The registry entry's state. `stale` means the footage left the project and
# its entry was kept on purpose (D7: re-indexing is expensive).
FOOTAGE_UPLOADING = "uploading"
FOOTAGE_INDEXING = "indexing"
FOOTAGE_READY = "ready"
FOOTAGE_STALE = "stale"
FOOTAGE_ERROR = "error"

FOOTAGE_STATES = (
    FOOTAGE_UPLOADING, FOOTAGE_INDEXING, FOOTAGE_READY, FOOTAGE_STALE, FOOTAGE_ERROR,
)

# --- stage states ---------------------------------------------------------
STAGE_PENDING = "pending"
STAGE_RUNNING = "running"
STAGE_DONE = "done"
STAGE_ERROR = "error"

STAGE_STATES = (STAGE_PENDING, STAGE_RUNNING, STAGE_DONE, STAGE_ERROR)

# --- library states -------------------------------------------------------
# Declared by the engine's `GET /v1/library/{cid}` and read here in `_handoff`.
# The sidecar never writes one; the names are kept so a rename on the engine is
# a broken import rather than a silent "always upload".
LIB_READY = "ready"
LIB_INDEXING = "indexing"
LIB_PARTIAL = "partial"

# Literal aliases, so a schema field and a write site cannot disagree on the
# spelling of one value.
JobState = Literal["queued", "uploading", "queued-for-backend", "running", "done", "error", "cancelled"]
FootageState = Literal["uploading", "indexing", "ready", "stale", "error"]
StageState = Literal["pending", "running", "done", "error"]

# The asserts fail at import if a Literal drifts from its tuple, which is the
# earliest point a schema edit can be caught.
assert get_args(JobState) == JOB_STATES
assert get_args(FootageState) == FOOTAGE_STATES
assert get_args(StageState) == STAGE_STATES