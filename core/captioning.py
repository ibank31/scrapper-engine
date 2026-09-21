#!/usr/bin/env python3
"""Clean word timestamps and build concise, readable caption cues."""
from __future__ import annotations

import re

FILLERS = {"um", "uh", "erm", "mm", "mhm", "hmm"}


def _token(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def clean_words(words: list[dict]) -> list[dict]:
    result: list[dict] = []
    previous = ""
    for word in words:
        text = _token(str(word.get("word", "")))
        if not text:
            continue
        normalized = re.sub(r"[^a-z0-9']", "", text.lower())
        if normalized in FILLERS:
            continue
        if normalized and normalized == previous:
            continue
        item = {"start": float(word.get("start", 0)), "end": float(word.get("end", word.get("start", 0))), "word": text}
        result.append(item)
        previous = normalized
    return result


def build_cues(transcript: dict, start: float, end: float, max_words: int = 5, max_chars: int = 30) -> list[dict]:
    words: list[dict] = []
    for segment in transcript.get("segments", []):
        ss, ee = float(segment.get("start", 0)), float(segment.get("end", 0))
        if ee <= start or ss >= end:
            continue
        segment_words = segment.get("words") or []
        if not segment_words:
            raw_words = str(segment.get("text") or "").split()
            span = max(0.05, ee - ss)
            segment_words = [{"start": ss + span * i / max(1, len(raw_words)), "end": ss + span * (i + 1) / max(1, len(raw_words)), "word": word} for i, word in enumerate(raw_words)]
        for word in segment_words:
            ws, we = float(word.get("start", ss)), float(word.get("end", ee))
            if we > start and ws < end:
                clone = dict(word)
                clone["start"], clone["end"] = max(ws, start), min(we, end)
                words.append(clone)
    words = clean_words(words)
    cues: list[dict] = []
    bucket: list[dict] = []
    chars = 0
    for word in words:
        candidate = chars + len(word["word"]) + (1 if bucket else 0)
        if bucket and (len(bucket) >= max_words or candidate > max_chars):
            cues.append({"start": bucket[0]["start"] - start, "end": bucket[-1]["end"] - start, "text": " ".join(w["word"] for w in bucket)})
            bucket, chars = [], 0
        bucket.append(word)
        chars += len(word["word"]) + (1 if chars else 0)
    if bucket:
        cues.append({"start": bucket[0]["start"] - start, "end": bucket[-1]["end"] - start, "text": " ".join(w["word"] for w in bucket)})
    return cues


def srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(transcript: dict, candidate: dict, path: str) -> list[dict]:
    cues = build_cues(transcript, float(candidate["start"]), float(candidate["end"]))
    lines: list[str] = []
    for index, cue in enumerate(cues, 1):
        lines += [str(index), f"{srt_time(cue['start'])} --> {srt_time(cue['end'])}", cue["text"], ""]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return cues
