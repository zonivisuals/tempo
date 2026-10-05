"""The engine's closed state vocabularies (AGENTS.md §3.4).

Declared once and imported everywhere, the same pattern the sidecar's
`vocabulary.py` uses. The import-time asserts fail at import if a schema
`Literal` drifts from its tuple, which is the earliest point an edit can be
caught.

The engine's vocabularies are smaller than the sidecar's on purpose. An engine
job covers indexing only, so it has no `uploading`, no `queued-for-backend`
(that is a sidecar state, meaning the engine is unreachable) and no `cancelled`.
The sidecar's `proxy.py` translates between them and `docs/engine-api.md` is
the contract of record.
"""

from typing import Literal, get_args

# --- job states -----------------------------------------------------------
# Indexing only. The sidecar's 7-value vocabulary is a superset.
JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_ERROR = "error"

JOB_STATES = (JOB_QUEUED, JOB_RUNNING, JOB_DONE, JOB_ERROR)
# States that claim the GPU. A second submit for the same content id returns
# the live job rather than starting a second run.
JOB_LIVE_STATES = (JOB_QUEUED, JOB_RUNNING)

# --- stage states ---------------------------------------------------------
STAGE_PENDING = "pending"
STAGE_RUNNING = "running"
STAGE_DONE = "done"
STAGE_ERROR = "error"

STAGE_STATES = (STAGE_PENDING, STAGE_RUNNING, STAGE_DONE, STAGE_ERROR)

# --- library states -------------------------------------------------------
# What `GET /v1/library/{cid}` reports for a content id. The sidecar's `_handoff`
# branches on these three; the rest it only needs to know it must upload.
LIB_MISSING = "missing"
LIB_PARTIAL = "partial"
LIB_UPLOADED = "uploaded"
LIB_INDEXING = "indexing"
LIB_READY = "ready"
LIB_STALE = "stale"
LIB_ERROR = "error"

LIB_STATES = (
    LIB_MISSING, LIB_PARTIAL, LIB_UPLOADED, LIB_INDEXING,
    LIB_READY, LIB_STALE, LIB_ERROR,
)

# --- query model state ----------------------------------------------------
# `loading` while the warm-up thread holds the GPU, `error` if it could not.
QM_LOADING = "loading"
QM_READY = "ready"
QM_ERROR = "error"

QUERY_MODEL_STATES = (QM_LOADING, QM_READY, QM_ERROR)

# Literal aliases, so a schema field and a write site cannot disagree.
JobState = Literal["queued", "running", "done", "error"]
StageState = Literal["pending", "running", "done", "error"]
LibraryState = Literal["missing", "partial", "uploaded", "indexing", "ready", "stale", "error"]
QueryModelState = Literal["loading", "ready", "error"]

assert get_args(JobState) == JOB_STATES
assert get_args(StageState) == STAGE_STATES
assert get_args(LibraryState) == LIB_STATES
assert get_args(QueryModelState) == QUERY_MODEL_STATES