"""One-off model cache seeder (ADR-0004 follow-up).

Problem: stages download multi-GB weights/tokenizers into the ephemeral
container disk on first use. A truncated download poisons that container
(the observed `tokenizer.json` serde failure at a fixed line), and every
cold container pays full download latency.

Fix: download once into the shared `tempo-models` Volume (mounted at the
default HF cache path, so runtimes resolve it with zero code changes),
verifying byte sizes against the HuggingFace API listings. Any mismatch
fails LOUDLY here — never a silent corrupt cache.

File sizes below were read from
https://huggingface.co/api/models/<repo>/tree/main on 2026-09-24 and are
asserted, not trusted. Re-verify if a model revision changes.

Usage (on Modal, CPU is fine — pure download, no inference):
  modal run modal_backend/modal_app.py::seed_cache
"""

# (repo_id, allow_patterns, [(relative_path, expected_bytes), ...])
# allow_patterns mirror each library's own fetch rules (faster-whisper's
# documented list; transformers resolves the rest itself).
MANIFEST = [
    (
        "openai/clip-vit-large-patch14",
        ["config.json", "preprocessor_config.json", "model.safetensors",
         "merges.txt", "tokenizer.json", "tokenizer_config.json",
         "vocab.json", "special_tokens_map.json"],
        [("tokenizer.json", 2224003), ("config.json", 4519)],
    ),
    (
        "Systran/faster-whisper-large-v3",
        ["config.json", "preprocessor_config.json", "model.bin",
         "tokenizer.json", "vocabulary.*"],
        [("model.bin", 3087284237), ("tokenizer.json", 2480617)],
    ),
    (
        "Salesforce/blip2-opt-2.7b",
        ["*.json", "*.txt", "*.safetensors"],
        [("tokenizer.json", 3558841), ("config.json", 1029)],
    ),
]


class SeedError(Exception):
    """A cache entry failed verification — fix the manifest or network."""


def seed_all(cache_dir=None, downloader=None):
    """Populate the HF cache and verify sizes. Returns a report dict.

    cache_dir: override the HF default (tests use tmp dirs).
    downloader: fn(repo_id, allow_patterns, cache_dir) -> snapshot path
        (defaults to huggingface_hub.snapshot_download; tests inject fakes).
    """
    import os

    if downloader is None:
        from huggingface_hub import snapshot_download as downloader

    if cache_dir is not None:
        os.environ["HF_HUB_CACHE"] = str(cache_dir)
    report = {}
    for repo_id, patterns, checks in MANIFEST:
        snap = downloader(repo_id, allow_patterns=patterns)
        from pathlib import Path as _Path

        snap = _Path(snap)
        verified, total = [], 0
        for rel, want in checks:
            matches = sorted(snap.rglob(rel))
            if not matches:
                raise SeedError(f"{repo_id}: expected file missing: {rel}")
            got = matches[0].stat().st_size
            if got != want:
                raise SeedError(
                    f"{repo_id}: {rel} size {got} != expected {want} "
                    f"(truncated download — not cached)"
                )
            verified.append(rel)
            total += got
        report[repo_id] = {"files": verified, "checked_bytes": total, "ok": True}
    return report
