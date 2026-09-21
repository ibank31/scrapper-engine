#!/usr/bin/env python3
"""Generate smooth FFmpeg crop expressions that follow the active face."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def video_size(path: str) -> tuple[int, int]:
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", path,
    ], text=True)
    stream = json.loads(raw)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def _smooth(values: list[float], alpha: float = 0.28) -> list[float]:
    if not values:
        return values
    result = [values[0]]
    for value in values[1:]:
        result.append(result[-1] * (1.0 - alpha) + value * alpha)
    return result


def detect_centers(path: str, sample_seconds: float = 0.5) -> tuple[int, int, float, list[tuple[float, float]]]:
    """Return source dimensions, duration and sampled face centers."""
    width, height = video_size(path)
    duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path,
    ], text=True).strip())
    try:
        import cv2
    except (ImportError, AttributeError):
        return width, height, duration, [(width / 2, height / 2)]
    if not hasattr(cv2, "VideoCapture") or not hasattr(cv2, "CascadeClassifier"):
        return width, height, duration, [(width / 2, height / 2)]
    cap = cv2.VideoCapture(path)
    cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    centers: list[tuple[float, float]] = []
    last = (width / 2, height / 2)
    frame_count = max(1, int(duration / sample_seconds) + 1)
    for index in range(frame_count):
        cap.set(cv2.CAP_PROP_POS_MSEC, index * sample_seconds * 1000.0)
        ok, frame = cap.read()
        if not ok:
            centers.append(last)
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(max(30, width // 12), max(30, height // 12)))
        if len(faces):
            x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
            last = (float(x + w / 2), float(y + h * 0.48))
        centers.append(last)
    cap.release()
    if not centers:
        centers = [(width / 2, height / 2)]
    xs = _smooth([point[0] for point in centers])
    ys = _smooth([point[1] for point in centers])
    return width, height, duration, list(zip(xs, ys))


def _piecewise(values: list[float], duration: float, default: float) -> str:
    if len(values) < 2:
        return f"{default:.2f}"
    if max(values) - min(values) < 2.0:
        return f"{sum(values) / len(values):.2f}"
    if len(values) > 20:
        stride = max(1, (len(values) - 1) // 19)
        values = [values[index] for index in range(0, len(values) - 1, stride)] + [values[-1]]
    step = duration / (len(values) - 1)
    expr = f"{values[-1]:.2f}"
    for index in range(len(values) - 2, -1, -1):
        start = index * step
        end = (index + 1) * step
        slope = (values[index + 1] - values[index]) / max(step, 0.001)
        segment = f"({values[index]:.2f}+{slope:.4f}*(t-{start:.3f}))"
        expr = f"if(between(t,{start:.3f},{end:.3f}),{segment},{expr})"
    return expr.replace(",", "\\,")


def crop_filter(path: str, out_width: int = 1080, out_height: int = 1920, sample_seconds: float = 0.5) -> str:
    """Return scale+crop filters; follow face when source is wider than 9:16."""
    width, height, duration, centers = detect_centers(path, sample_seconds)
    crop_width = min(width, int(round(height * out_width / out_height)))
    crop_height = min(height, int(round(width * out_height / out_width)))
    if width / height >= out_width / out_height:
        crop_width = int(round(height * out_width / out_height))
        max_x = max(0, width - crop_width)
        xs = [max(0.0, min(max_x, x - crop_width / 2)) for x, _ in centers]
        x_expr = _piecewise(xs, duration, max_x / 2)
        return f"crop={crop_width}:{height}:x='{x_expr}':y=0,scale={out_width}:{out_height}:flags=lanczos"
    crop_height = int(round(width * out_height / out_width))
    max_y = max(0, height - crop_height)
    ys = [max(0.0, min(max_y, y - crop_height / 2)) for _, y in centers]
    y_expr = _piecewise(ys, duration, max_y / 2)
    return f"crop={width}:{crop_height}:x=0:y='{y_expr}',scale={out_width}:{out_height}:flags=lanczos"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    args = parser.parse_args()
    print(crop_filter(args.video))
