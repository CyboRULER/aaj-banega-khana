"""Live transcriber for recipe links.

Many recipe videos have captions disabled, so this tries several sources in
order and returns the first that yields usable text:

1. YouTube captions (en / en-IN / hi)
2. The video's title + description (recipes are often written there)
3. A recipe page linked from the description (e.g. "full recipe: <url>")

The combined text is handed to the LLM, which extracts the structured recipe.
"""
from __future__ import annotations

import html as html_mod
import json
import re
import urllib.request

from ..domain import TranscriptUnavailable
from ..services.transcription import Transcriber

_YT_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|/embed/)([A-Za-z0-9_-]{11})")
_DESC = re.compile(r'"shortDescription":"(.*?)","isCrawlable', re.S)
_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
_URL = re.compile(r"https?://[^\s)>\"']+")
_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S)
_UA = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
# Domains we won't follow from a description (socials, trackers, storefronts).
_SKIP = ("youtube.com", "youtu.be", "instagram.com", "facebook.com", "twitter.com",
         "x.com", "pinterest.", "amazon.", "bit.ly", "t.me", "whatsapp.com")

MIN_USEFUL = 200  # chars below which text is unlikely to hold a recipe


def _get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _strip_html(raw: str) -> str:
    text = html_mod.unescape(_TAGS.sub(" ", raw))
    return re.sub(r"[ \t]*\n\s*", "\n", re.sub(r"[ \t]{2,}", " ", text)).strip()


def fetch_captions(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi
    fetched = YouTubeTranscriptApi().fetch(video_id, languages=("en", "en-IN", "hi"))
    parts = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
    return " ".join(
        (p["text"] if isinstance(p, dict) else getattr(p, "text", "")) for p in parts).strip()


def fetch_page_meta(url: str) -> tuple[str, str]:
    """Return (title, description) for a YouTube watch page."""
    page = _get(url)
    title = ""
    m = _TITLE.search(page)
    if m:
        title = html_mod.unescape(m.group(1)).replace(" - YouTube", "").strip()
    desc = ""
    m = _DESC.search(page)
    if m:
        try:
            desc = json.loads('"' + m.group(1) + '"')
        except Exception:
            desc = m.group(1)
    return title, desc


def follow_recipe_link(description: str) -> str:
    """Fetch the first plausible recipe page linked in the description."""
    for link in _URL.findall(description or ""):
        if any(s in link.lower() for s in _SKIP):
            continue
        try:
            return _strip_html(_get(link))[:12000]
        except Exception:
            continue
    return ""


class YouTubeTranscriber(Transcriber):
    def fetch(self, url: str) -> str:
        m = _YT_ID.search(url)
        if not m:
            raise TranscriptUnavailable(f"not a recognized youtube url: {url}")
        video_id = m.group(1)
        sources: list[str] = []

        try:
            captions = fetch_captions(video_id)
            if captions:
                sources.append(captions)
        except Exception:
            pass  # captions are often disabled - fall through

        if sum(len(s) for s in sources) < MIN_USEFUL:
            try:
                title, desc = fetch_page_meta(url)
                if title:
                    sources.append(f"NAME: {title}")
                if desc:
                    sources.append(desc)
                    linked = follow_recipe_link(desc)
                    if linked:
                        sources.append(linked)
            except Exception:
                pass

        text = "\n\n".join(s for s in sources if s).strip()
        if len(text) < MIN_USEFUL:
            raise TranscriptUnavailable(
                "no captions, description or linked recipe found for this video")
        return text
