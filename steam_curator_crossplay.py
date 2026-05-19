from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

import requests


CURATOR_ID = "39520863"
CURATOR_NAME = "Steam Curator: Cross-Platform Play"
CURATOR_AJAX_URL = (
    "https://store.steampowered.com/curator/"
    + CURATOR_ID
    + "-Cross-Platform-Play/ajaxgetfilteredrecommendations/render/"
)

PLATFORM_PATTERNS = {
    "PlayStation": r"playstation|\bps4\b|\bps5\b",
    "Xbox": r"xbox|series x|series s",
    "Nintendo Switch": r"nintendo switch|\bswitch\b",
    "Steam": r"steam",
    "Epic Games Store": r"\begs\b|epic games store",
    "Microsoft Store": r"microsoft store|windows store",
    "Windows PC": r"\bpc\b|windows pc",
    "Mobile": r"mobile|ios|android",
}

NEGATIVE_PATTERNS = [
    r"does not (currently )?support cross[- ]?(platform|play)",
    r"no cross[- ]?platform",
    r"not cross[- ]?platform",
    r"doesn't support crossplay",
    r"does not support crossplay",
    r"no crossplay",
]

POSITIVE_PATTERNS = [
    r"cross[- ]?platform play is supported",
    r"supports cross[- ]?platform",
    r"crossplay is supported",
    r"supports crossplay",
    r"cross[- ]?play is supported",
]


class SteamCuratorCrossplayClient:
    def __init__(self, timeout: int = 20) -> None:
        self.session = requests.Session()
        self.timeout = timeout

    def lookup_appid(self, appid: int, name: str = "", max_pages: int = 5, page_size: int = 100) -> dict:
        override = load_override(appid, name)
        if override:
            return override
        start = 0
        for _ in range(max_pages):
            payload = self._fetch_page(start, page_size)
            html = payload.get("results_html", "")
            result = parse_curator_html_for_appid(html, appid)
            if result:
                return result
            start += page_size
            total = int(payload.get("total_count") or 0)
            if start >= total:
                break
        return {"status": "Unknown", "platforms": [], "source": CURATOR_NAME, "note": ""}

    def _fetch_page(self, start: int, count: int) -> dict:
        response = self.session.get(
            CURATOR_AJAX_URL,
            params={"query": "", "start": start, "count": count, "tagids": "", "sort": "recent"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


def load_override(appid: int, name: str = "") -> dict | None:
    path = Path(__file__).resolve().parent / "data" / "crossplay_overrides.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    appid_entry = data.get("appid", {}).get(str(appid))
    if appid_entry:
        return normalize_override(appid_entry)
    name_key = name.strip().casefold()
    if name_key:
        name_entry = data.get("name", {}).get(name_key)
        if name_entry:
            return normalize_override(name_entry)
    return None


def normalize_override(entry: dict) -> dict:
    return {
        "status": entry.get("status", "Unknown"),
        "platforms": entry.get("platforms", []),
        "source": "Manual override",
        "note": entry.get("note", "Manual override"),
    }

def parse_curator_html_for_appid(html: str, appid: int) -> dict | None:
    marker_match = re.search(rf'(data-ds-appid="{appid}"|/app/{appid}/)', html)
    if not marker_match:
        return None
    start = html.rfind('<div data-panel=', 0, marker_match.start())
    if start < 0:
        start = max(0, marker_match.start() - 2000)
    next_start = html.find('<div data-panel=', marker_match.end())
    end = next_start if next_start > start else min(len(html), marker_match.end() + 5000)
    return parse_recommendation_block(html[start:end])


def parse_recommendation_block(block: str) -> dict:
    text_match = re.search(r'<div class="recommendation_desc">([\s\S]*?)</div>', block)
    note = clean_html(text_match.group(1)) if text_match else ""
    lowered = note.casefold()
    recommended = "color_recommended" in block or "Recommended" in block
    informational = "color_informational" in block or "Informational" in block

    if any(re.search(pattern, lowered) for pattern in NEGATIVE_PATTERNS):
        status = "No"
    elif any(re.search(pattern, lowered) for pattern in POSITIVE_PATTERNS):
        status = "Yes"
    elif recommended and "cross" in lowered:
        status = "Yes"
    elif informational:
        status = "Unknown"
    else:
        status = "Unknown"

    platforms = extract_platforms(note)
    return {"status": status, "platforms": platforms, "source": CURATOR_NAME, "note": note}


def extract_platforms(text: str) -> list[str]:
    lowered = text.casefold()
    result = []
    for label, pattern in PLATFORM_PATTERNS.items():
        if re.search(pattern, lowered):
            result.append(label)
    return result


def clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()
