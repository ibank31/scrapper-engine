#!/usr/bin/env python3
"""Transcribe a local video/audio file with faster-whisper."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def _srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Local faster-whisper transcription")
    ap.add_argument("input", help="video/audio input")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--model", default="small", help="tiny/base/small/medium/large-v3/turbo")
    ap.add_argument("--language", default=None)
    ap.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    ap.add_argument("--compute-type", default=None, help="default: int8 on CPU, float16 on CUDA")
    args = ap.parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit("faster-whisper belum terpasang. Jalankan: pip install faster-whisper") from exc

    out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(args.input)), "transcript")
    os.makedirs(out_dir, exist_ok=True)
    compute_type = args.compute_type or ("int8" if args.device == "cpu" else "float16")
    model = WhisperModel(args.model, device=args.device, compute_type=compute_type)
    segments, info = model.transcribe(
        args.input,
        language=args.language,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    result_segments = []
    srt_lines = []
    for number, segment in enumerate(segments, 1):
        words = []
        for word in segment.words or []:
            words.append({"start": round(float(word.start), 3), "end": round(float(word.end), 3), "word": word.word})
        item = {"id": number - 1, "start": round(float(segment.start), 3), "end": round(float(segment.end), 3), "text": segment.text.strip(), "words": words}
        result_segments.append(item)
        srt_lines += [str(number), f"{_srt_time(item['start'])} --> {_srt_time(item['end'])}", item["text"], ""]
    payload = {"input": os.path.abspath(args.input), "model": args.model, "device": args.device, "compute_type": compute_type, "language": info.language, "language_probability": info.language_probability, "segments": result_segments}
    with open(os.path.join(out_dir, "transcript.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    with open(os.path.join(out_dir, "transcript.srt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(srt_lines))
    print("OK:", out_dir, "| segments:", len(result_segments), "| language:", info.language)


if __name__ == "__main__":
    main()
