"""Tier 1 — speech (faster-whisper).

Port of notebook cell b9ae1b9d (`_seg_dict`, `transcribe`): source-language
transcript with word timestamps + an English version for non-English audio.
English segments keep their own timestamps and are mapped to shots by time,
never by list index.

Deviations from the notebook:
  - progress = audio seconds transcribed (segment end times); a translation
    pass extends the total by one more duration;
  - models come from the resolved device profile; the translate model is
    released as soon as it is done.
"""

from .. import models
from ..config import Profile, settings
from . import Progress

NO_SPEECH_PROB_MAX = 0.6
AVG_LOGPROB_MIN = -1.0
TURBO_FALLBACK = {True: "large-v3", False: "medium"}  # turbo models cannot translate


def _seg_dict(seg, words: bool = True) -> dict | None:  # type: ignore[no-untyped-def]
    d = {"start": float(seg.start), "end": float(seg.end), "text": seg.text.strip(),
         "words": [{"word": w.word, "start": float(w.start), "end": float(w.end)} for w in (seg.words or [])]
         if words else []}
    hallucinated = (getattr(seg, "no_speech_prob", 0) > NO_SPEECH_PROB_MAX
                    and getattr(seg, "avg_logprob", 0) < AVG_LOGPROB_MIN)
    return None if (hallucinated or not d["text"]) else d


def transcribe(video_path: str, prof: Profile, progress: Progress) -> dict:
    from faster_whisper import WhisperModel

    compute = "float16" if prof.gpu else "int8"
    opts = dict(vad_filter=True, initial_prompt=settings.name_hints or None)

    model = WhisperModel(prof.whisper_model, device=models.device(), compute_type=compute)
    segs, info = model.transcribe(video_path, task="transcribe", word_timestamps=True, **opts)
    total = max(1, int(round(info.duration)))
    progress(0, total)
    src = []
    for s in segs:
        d = _seg_dict(s)
        if d:
            src.append(d)
        progress(min(int(s.end), total), total)
    lang = info.language

    en = src
    if lang != "en" and src:
        tr_name = prof.whisper_translate_model
        if "turbo" in tr_name:
            tr_name = TURBO_FALLBACK[prof.gpu]
        tr_model = model if tr_name == prof.whisper_model else WhisperModel(
            tr_name, device=models.device(), compute_type=compute)
        segs_en, _ = tr_model.transcribe(video_path, task="translate", language=lang,
                                         word_timestamps=False, **opts)
        en = []
        for s in segs_en:
            d = _seg_dict(s, words=False)
            if d:
                en.append(d)
            progress(total + min(int(s.end), total), 2 * total)
        progress(2 * total, 2 * total)
        if tr_model is not model:
            del tr_model

    del model
    models.free_memory()
    return {"language": lang, "language_prob": float(info.language_probability), "src": src, "en": en}
