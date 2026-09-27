"""Engine configuration (AGENTS.md §3.7, ADR-0008/0009).

Port of `tempo_pipeline_v4.ipynb` cell a1dde1e3 (configuration). Every
tunable lives here with a documented default and a TEMPO_ENGINE_ override;
logic imports names and numbers from here, never literals.

Model fields left empty resolve to the notebook's GPU or CPU default for the
device the engine runs on (`profile()`), so one config serves the Brev L4 and
offline CPU dev.

`config_signature()` covers everything that changes an index (pipeline
version, models, indexing parameters). Fusion weights are excluded on
purpose: retuning never reindexes.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PIPELINE_VERSION = "tempo-v4.0"

# Notebook cell a1dde1e3: GPU default / CPU default per model.
GPU_DEFAULTS = {
    "visual_model": "google/siglip2-so400m-patch14-384",
    "caption_model": "florence-community/Florence-2-large",
    "whisper_model": "large-v3",
    "caption_budget": 120,
}
CPU_DEFAULTS = {
    "visual_model": "google/siglip2-base-patch16-256",
    "caption_model": "florence-community/Florence-2-base",
    "whisper_model": "small",
    "caption_budget": 40,
}


class EngineSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TEMPO_ENGINE_",
        extra="ignore",
        protected_namespaces=(),
    )

    # Service. Bound to the instance's localhost: reachable only through
    # `brev port-forward` (ADR-0008).
    host: str = "127.0.0.1"
    port: int = 8900
    log_level: str = "INFO"
    # Bearer token for every route except /v1/health. Env only, never logged.
    token: str = ""

    # Durable state (= /home/ubuntu/workspace/tempo mounted at /data on Brev).
    data_root: Path = Path("./engine-data")

    # auto | cuda | cpu
    device: str = "auto"

    # Models: empty = device default (GPU_DEFAULTS / CPU_DEFAULTS).
    visual_model: str = ""
    caption_model: str = ""
    whisper_model: str = ""
    # Must not be a *-turbo model (turbo cannot translate); empty = whisper_model.
    whisper_translate_model: str = ""
    text_embed_model: str = "BAAI/bge-base-en-v1.5"
    bge_query_prompt: str = "Represent this sentence for searching relevant passages: "
    caption_task: str = "<DETAILED_CAPTION>"
    ner_model: str = "dslim/bert-base-NER"
    emotion_model: str = "j-hartmann/emotion-english-distilroberta-base"
    name_hints: str = ""  # e.g. "ohnePixel, Jhon, Akita" — helps Whisper spell names

    # Indexing parameters (all part of the signature).
    max_shot_sec: float = 8.0
    caption_budget: int = 0  # 0 = device default
    dialogue_pad_sec: float = 3.0
    min_dialogue_words: int = 3
    ocr_edge_min: float = 0.02
    ocr_min_conf: float = 0.40
    ner_min_score: float = 0.60
    emotion_min_score: float = 0.30
    frame_max_side: int = 1024
    frame_jpeg_quality: int = 90
    frame_ratios: tuple[float, float, float] = (0.2, 0.5, 0.8)

    # Throughput knobs (not part of the signature: they never change results).
    siglip_batch: int = 16
    text_embed_batch: int = 64
    ner_batch: int = 16
    shot_scan_step_s: float = 10.0  # scene-detect chunk between progress reports
    caption_max_new_tokens: int = 128
    caption_num_beams: int = 3

    # Display thumbs synced down to the sidecar.
    thumb_width: int = 320
    thumb_quality: int = 85

    # Fusion (ADR-0009, §3.5). Query-time only — excluded from the signature.
    w_visual: float = 0.35
    w_dialogue: float = 0.25
    w_caption: float = 0.15
    w_bm25: float = 0.15
    w_entity: float = 0.10
    w_anchor: float = 0.05
    zscore_cap: float = 3.0
    dedupe_scenes: bool = True
    faiss_candidates: int = 512
    corpus_cache_size: int = 8

    # Uploads (ADR-0008). delete = purge raw once the index persists (ADR-0006).
    max_chunk_mb: int = 64
    raw_retention: str = "delete"

    # Warm the query models at startup so the first search is not cold.
    preload_query_models: bool = True


@dataclass(frozen=True)
class Profile:
    """Resolved model names + budget for one device (GPU or CPU)."""

    gpu: bool
    visual_model: str
    caption_model: str
    whisper_model: str
    whisper_translate_model: str
    caption_budget: int


def profile(s: "EngineSettings", gpu: bool) -> Profile:
    base = GPU_DEFAULTS if gpu else CPU_DEFAULTS
    whisper = s.whisper_model or base["whisper_model"]
    return Profile(
        gpu=gpu,
        visual_model=s.visual_model or base["visual_model"],
        caption_model=s.caption_model or base["caption_model"],
        whisper_model=whisper,
        whisper_translate_model=s.whisper_translate_model or whisper,
        caption_budget=s.caption_budget or base["caption_budget"],
    )


def weights(s: "EngineSettings") -> dict[str, float]:
    return {
        "visual": s.w_visual,
        "dialogue": s.w_dialogue,
        "caption": s.w_caption,
        "bm25": s.w_bm25,
        "entity": s.w_entity,
        "anchor": s.w_anchor,
    }


def config_signature(s: "EngineSettings", prof: Profile) -> dict:
    """Everything that changes the index. Weights are excluded on purpose."""
    return {
        "v": PIPELINE_VERSION, **{k: v for k, v in asdict(prof).items() if k != "gpu"},
        "text": s.text_embed_model, "cap_task": s.caption_task, "ner": s.ner_model,
        "emo": s.emotion_model, "hints": s.name_hints, "max_shot": s.max_shot_sec,
        "pad": s.dialogue_pad_sec, "minw": s.min_dialogue_words,
        "ocr_edge": s.ocr_edge_min, "ocr_conf": s.ocr_min_conf,
        "ner_min": s.ner_min_score, "emo_min": s.emotion_min_score,
        "frame_side": s.frame_max_side, "frames": list(s.frame_ratios),
        "thumb": s.thumb_width,
    }


def signature_hash(sig: dict) -> str:
    return hashlib.sha1(json.dumps(sig, sort_keys=True).encode()).hexdigest()[:12]


settings = EngineSettings()
