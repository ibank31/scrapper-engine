"""Minimal Google Drive API client for campaign media intake.

The worker uses a refresh token supplied through environment variables. No
Google password, access token, or client secret is written to the repository.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

DRIVE_API = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
VIDEO_MIME_PREFIXES = ("video/",)
MEDIA_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".wav", ".mp3", ".m4a"}


class GoogleDriveError(RuntimeError):
    """A safe, user-actionable Google Drive integration failure."""


def configured() -> bool:
    return all(os.getenv(name) for name in (
        "GOOGLE_DRIVE_REFRESH_TOKEN",
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
    ))


def extract_drive_id(url_or_id: str) -> str | None:
    value = str(url_or_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", value):
        return value
    parsed = urlparse(value)
    query_id = parse_qs(parsed.query).get("id", [None])[0]
    if query_id:
        return query_id
    match = re.search(r"/(?:file/d|folders)/([A-Za-z0-9_-]+)", parsed.path)
    return match.group(1) if match else None


def _safe_error(response: requests.Response) -> str:
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error.get("status") or "Google Drive API error")[:300]
        return str(body)[:300]
    except ValueError:
        return response.text[:300] or f"HTTP {response.status_code}"


def _refresh_access_token(timeout: int = 30) -> str:
    if not configured():
        raise GoogleDriveError(
            "Google Drive OAuth belum dikonfigurasi; isi GOOGLE_DRIVE_REFRESH_TOKEN, "
            "GOOGLE_OAUTH_CLIENT_ID, dan GOOGLE_OAUTH_CLIENT_SECRET"
        )
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_DRIVE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=timeout,
    )
    if not response.ok:
        raise GoogleDriveError(f"OAuth token refresh gagal: HTTP {response.status_code}: {_safe_error(response)}")
    token = response.json().get("access_token")
    if not token:
        raise GoogleDriveError("OAuth token refresh tidak mengembalikan access_token")
    return str(token)


class GoogleDriveClient:
    def __init__(self, timeout: int = 30, retries: int = 3):
        self.timeout = timeout
        self.retries = max(1, retries)
        self._access_token = _refresh_access_token(timeout=timeout)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = DRIVE_API + path
        last_error = None
        for attempt in range(self.retries):
            try:
                response = requests.request(method, url, headers=self.headers, timeout=self.timeout, **kwargs)
                if response.status_code == 401 and attempt == 0:
                    self._access_token = _refresh_access_token(timeout=self.timeout)
                    continue
                if response.status_code in {408, 429, 500, 502, 503, 504} and attempt + 1 < self.retries:
                    time.sleep(min(8, 2 ** attempt))
                    continue
                if not response.ok:
                    raise GoogleDriveError(f"Google Drive API HTTP {response.status_code}: {_safe_error(response)}")
                return response
            except (requests.RequestException, GoogleDriveError) as exc:
                last_error = exc
                if isinstance(exc, GoogleDriveError) and "HTTP 4" in str(exc) and "HTTP 408" not in str(exc):
                    raise
                if attempt + 1 < self.retries:
                    time.sleep(min(8, 2 ** attempt))
        raise GoogleDriveError(f"Google Drive request gagal: {str(last_error)[:300]}")

    def list_media(self, folder_id: str, page_size: int = 100, max_depth: int = 5) -> list[dict]:
        files: list[dict] = []
        visited: set[str] = set()

        def walk(current_id: str, depth: int) -> None:
            if current_id in visited or depth > max_depth:
                return
            visited.add(current_id)
            page_token = None
            while True:
                params = {
                    "q": f"'{current_id}' in parents and trashed = false",
                    "pageSize": min(1000, page_size),
                    "orderBy": "name",
                    "fields": "nextPageToken,files(id,name,mimeType,size,capabilities/canDownload,md5Checksum)",
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                }
                if page_token:
                    params["pageToken"] = page_token
                body = self._request("GET", "/files", params=params).json()
                for item in body.get("files", []):
                    name = str(item.get("name") or "")
                    mime = str(item.get("mimeType") or "")
                    if mime == "application/vnd.google-apps.folder":
                        walk(str(item.get("id") or ""), depth + 1)
                    elif (mime.startswith(VIDEO_MIME_PREFIXES) or Path(name).suffix.lower() in MEDIA_EXTENSIONS) and item.get("capabilities", {}).get("canDownload", True):
                        files.append(item)
                page_token = body.get("nextPageToken")
                if not page_token:
                    return

        walk(folder_id, 0)
        return files

    def download_file(self, file_id: str, destination: str, chunk_size: int = 1024 * 1024) -> int:
        response = self._request("GET", f"/files/{file_id}", params={"alt": "media", "supportsAllDrives": "true"}, stream=True)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            with target.open("wb") as output:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        output.write(chunk)
                        total += len(chunk)
        except (OSError, requests.RequestException) as exc:
            target.unlink(missing_ok=True)
            raise GoogleDriveError(f"Download Drive gagal untuk {file_id}: {str(exc)[:240]}") from exc
        if total <= 0:
            target.unlink(missing_ok=True)
            raise GoogleDriveError(f"File Drive {file_id} kosong")
        return total

    def export_file(self, file_id: str, mime_type: str) -> bytes:
        """Export a Google Workspace file, such as a Sheet, in a supported format."""
        response = self._request(
            "GET",
            f"/files/{file_id}/export",
            params={"mimeType": mime_type},
        )
        return response.content


def download_folder_oauth(folder_url: str, destination: str, max_files: int = 0) -> tuple[str, str | None, int]:
    folder_id = extract_drive_id(folder_url)
    if not folder_id:
        return "failed", "folder ID Google Drive tidak ditemukan", 0
    try:
        client = GoogleDriveClient()
        files = client.list_media(folder_id)
        if not files:
            return "failed", "folder tidak berisi media yang dapat diunduh atau akses ditolak", 0
        downloaded = 0
        for item in files if max_files <= 0 else files[:max_files]:
            safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", str(item.get("name") or item["id"]))
            size = client.download_file(item["id"], str(Path(destination) / safe_name))
            downloaded += size
        return "downloaded", None, len(files[:max(1, max_files)])
    except GoogleDriveError as exc:
        return "failed", str(exc)[:300], 0
    except Exception as exc:
        return "failed", f"Google Drive integration error: {str(exc)[:240]}", 0


def download_file_oauth(file_url: str, destination: str) -> tuple[str, str | None]:
    file_id = extract_drive_id(file_url)
    if not file_id:
        return "failed", "file ID Google Drive tidak ditemukan"
    try:
        GoogleDriveClient().download_file(file_id, destination)
        return "downloaded", None
    except GoogleDriveError as exc:
        return "failed", str(exc)[:300]
    except Exception as exc:
        return "failed", f"Google Drive integration error: {str(exc)[:240]}"
