import os
import re
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import yt_dlp

from config import MAX_FILE_SIZE_MB, DOWNLOAD_PATH

logger = logging.getLogger(__name__)

PLATFORM_PATTERNS = {
    "tiktok": [
        r"tiktok\.com",
        r"vm\.tiktok\.com",
        r"vt\.tiktok\.com",
    ],
    "instagram": [
        r"instagram\.com/(reel|p|tv)/",
        r"instagr\.am",
    ],
    "youtube": [
        r"youtube\.com/watch",
        r"youtube\.com/shorts",
        r"youtu\.be/",
        r"yt\.be/",
        r"m\.youtube\.com",
    ],
}


@dataclass
class DownloadResult:
    success: bool
    file_path: Optional[str] = None
    title: Optional[str] = None
    platform: Optional[str] = None
    thumbnail: Optional[str] = None
    duration: Optional[int] = None
    error: Optional[str] = None


def detect_platform(url: str) -> Optional[str]:
    url_lower = url.lower()
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url_lower):
                return platform
    return None


def is_supported_url(url: str) -> bool:
    return detect_platform(url) is not None


def _get_ydl_opts(output_path: str, platform: str) -> dict:
    base_opts = {
        "outtmpl": os.path.join(output_path, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "merge_output_format": "mp4",
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
        "max_filesize": MAX_FILE_SIZE_MB * 1024 * 1024,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        },
    }

    if platform == "tiktok":
        base_opts.update({
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        })
    elif platform == "instagram":
        base_opts.update({
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        })
    elif platform == "youtube":
        base_opts.update({
            "format": (
                "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                "/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
                "/best[ext=mp4]/best"
            ),
        })

    return base_opts


def _classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if any(k in msg for k in ["private", "login", "sign in", "age-restricted"]):
        return "private"
    if any(k in msg for k in ["too large", "filesize", "size limit"]):
        return "too_large"
    if any(k in msg for k in ["not found", "no video", "404", "does not exist"]):
        return "not_found"
    if any(k in msg for k in ["geo", "country", "region", "not available"]):
        return "geo_blocked"
    if any(k in msg for k in ["copyright", "removed"]):
        return "removed"
    return "general"


async def download_video(url: str) -> DownloadResult:
    platform = detect_platform(url)
    if not platform:
        return DownloadResult(success=False, error="unsupported")

    tmp_dir = tempfile.mkdtemp(dir=DOWNLOAD_PATH)
    ydl_opts = _get_ydl_opts(tmp_dir, platform)

    def _do_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise ValueError("No video info returned")
            return info

    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _do_download)

        mp4_files = list(Path(tmp_dir).glob("*.mp4"))
        if not mp4_files:
            all_files = [f for f in Path(tmp_dir).iterdir()
                         if f.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov")]
            if not all_files:
                return DownloadResult(success=False, error="general")
            video_file = max(all_files, key=lambda f: f.stat().st_size)
        else:
            video_file = max(mp4_files, key=lambda f: f.stat().st_size)

        file_size_mb = video_file.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            os.remove(video_file)
            return DownloadResult(success=False, error="too_large")

        title    = info.get("title") or info.get("description") or "video"
        duration = info.get("duration")

        return DownloadResult(
            success=True,
            file_path=str(video_file),
            title=title[:100] if title else "video",
            platform=platform,
            duration=duration,
        )

    except yt_dlp.utils.DownloadError as e:
        logger.warning("yt-dlp error [%s]: %s", platform, e)
        return DownloadResult(success=False, error=_classify_error(e), platform=platform)

    except Exception as e:
        logger.error("Unexpected error [%s]: %s", platform, e, exc_info=True)
        return DownloadResult(success=False, error="general", platform=platform)


def cleanup_file(file_path: str):
    try:
        p = Path(file_path)
        if p.exists():
            p.unlink()
        parent = p.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except Exception as e:
        logger.warning("Cleanup failed for %s: %s", file_path, e)


def ensure_download_dir():
    Path(DOWNLOAD_PATH).mkdir(parents=True, exist_ok=True)
