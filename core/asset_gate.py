"""Deterministic gate for choosing locally downloaded video inputs."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


def manifest_video_paths(
    workspace: str | Path,
    manifest: dict[str, Any],
    *,
    extensions: Iterable[str],
) -> list[Path]:
    """Return only media eligible for deep processing.

    New manifests are authoritative: a video asset must have a passing
    media_validation result. Legacy manifests without that field retain the
    old defensive filesystem fallback.
    """
    root = Path(workspace)
    allowed = {str(ext).lower() for ext in extensions}
    assets = manifest.get("asset_manifest") or []
    has_validation = any(
        item.get("asset_kind") == "video" and isinstance(item.get("media_validation"), dict)
        for item in assets
    )
    selected: list[Path] = []
    for item in assets:
        if item.get("asset_kind") != "video" or not item.get("downloaded"):
            continue
        validation = item.get("media_validation")
        if validation is not None and validation.get("status") != "pass":
            continue
        local_path = str(item.get("local_path") or "")
        if not local_path:
            continue
        target = root / local_path
        if target.is_file() and target.suffix.lower() in allowed and not target.name.endswith(".part"):
            selected.append(target)
    if selected or has_validation:
        return selected
    return [
        path for path in (root / "assets").rglob("*")
        if path.is_file()
        and not path.name.startswith(".")
        and not path.name.endswith(".part")
        and path.suffix.lower() in allowed
    ]


def manifest_has_invalid_media(manifest: dict[str, Any]) -> bool:
    """Return whether the authoritative manifest contains failed video media."""
    return any(
        item.get("asset_kind") == "video"
        and item.get("status") in {"INVALID_MEDIA", "DOWNLOAD_FAILED"}
        for item in (manifest.get("asset_manifest") or [])
    )


__all__ = ["manifest_video_paths", "manifest_has_invalid_media"]
