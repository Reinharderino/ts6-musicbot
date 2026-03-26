"""
Resolves a search query or URL to a streamable audio URL via yt-dlp.
Supports YouTube, SoundCloud, and any site yt-dlp handles (~1000+).
"""

import asyncio
import yt_dlp

YDL_OPTS = {
    # Prefer opus/webm (~160 kbps) → m4a/aac (~128 kbps) → any best audio
    "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
}


async def resolve(query: str) -> dict:
    """
    Resolves a search query or URL to track metadata.
    Returns dict with: url, title, duration, webpage_url, uploader.
    Raises ValueError if nothing found.
    """
    import audio.resolver as _mod
    search_query = query if query.startswith("http") else f"ytsearch1:{query}"
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(None, lambda: _mod._resolve_sync(search_query))
    if info is None:
        raise ValueError(f"No results for: {query}")
    if "entries" in info:
        info = info["entries"][0]
    return {
        "url": info["url"],
        "title": info.get("title", "Untitled"),
        "duration": info.get("duration", 0),
        "webpage_url": info.get("webpage_url", query),
        "uploader": info.get("uploader", ""),
    }


async def re_resolve(webpage_url: str) -> str:
    """Re-fetch a fresh stream URL from the track's webpage URL.
    Call this just before playback to avoid expired YouTube stream URLs.
    """
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(None, lambda: _resolve_sync(webpage_url))
    if "entries" in info:
        info = info["entries"][0]
    return info["url"]


def _resolve_sync(query: str) -> dict:
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if info is None:
            raise ValueError(f"No results for: {query}")
        return info
