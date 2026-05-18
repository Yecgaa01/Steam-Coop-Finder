from __future__ import annotations

import re
from datetime import datetime
from html import unescape

import requests

from catalog import SteamApp
from models import Game


STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_STORESEARCH_URL = "https://store.steampowered.com/api/storesearch/"
STEAM_DISCOVERY_URL = "https://store.steampowered.com/search/results/"
STEAM_REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"

COOP_CATEGORIES = {
    "Online Co-op": "38",
    "Local Co-op": "24",
    "Shared/Split Screen Co-op": "39",
    "LAN Co-op": "48",
}

GENRE_TAGS = {
    "Any": "",
    "Action": "19",
    "Adventure": "21",
    "RPG": "122",
    "Indie": "492",
    "Casual": "597",
    "Simulation": "599",
    "Strategy": "9",
    "Sports": "701",
    "Racing": "699",
    "Survival": "1662",
    "Horror": "1667",
    "FPS": "1663",
    "Puzzle": "1664",
    "Platformer": "1625",
    "Open World": "1695",
    "Sandbox": "3810",
    "Souls-like": "29482",
    "Rogue-like": "1716",
    "Rogue-lite": "3959",
    "Metroidvania": "1628",
    "Action RPG": "4231",
    "Tactical RPG": "21725",
    "JRPG": "4434",
    "CRPG": "4474",
    "Dungeon Crawler": "1720",
    "Survival Horror": "3978",
    "Hack and Slash": "1646",
    "Bullet Hell": "4885",
    "Twin Stick Shooter": "4758",
    "Top-Down Shooter": "4637",
    "Looter Shooter": "353880",
    "Hero Shooter": "620519",
    "Extraction Shooter": "1199779",
    "Base Building": "7332",
    "Open World Survival Craft": "1100689",
    "Crafting": "1702",
    "Automation": "255534",
    "Colony Sim": "220585",
    "Farming Sim": "87918",
    "Life Sim": "10235",
    "Management": "12472",
    "City Builder": "4328",
    "Grand Strategy": "4364",
    "RTS": "1676",
    "Turn-Based Strategy": "1741",
    "Turn-Based Tactics": "14139",
    "Deckbuilding": "32322",
    "Card Battler": "791774",
    "MOBA": "1718",
    "MMORPG": "1754",
    "Party Game": "7178",
    "4 Player Local": "4840",
    "PvE": "6730",
    "PvP": "1775",
    "3D Platformer": "5395",
    "Precision Platformer": "3877",
    "Puzzle Platformer": "5537",
    "Arcade": "1773",
    "Driving": "1644",
    "Combat Racing": "4102",
    "Loot": "4236",
}


class SteamApiError(Exception):
    pass


class SteamClient:
    def __init__(self, timeout: int = 20) -> None:
        self.session = requests.Session()
        self.timeout = timeout

    def fetch_app(self, appid: int, country_code: str = "br", language: str = "english") -> Game:
        response = self.session.get(
            STEAM_APPDETAILS_URL,
            params={"appids": appid, "cc": country_code.lower(), "l": language},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        entry = payload.get(str(appid))
        if not entry or not entry.get("success") or not entry.get("data"):
            return Game.not_found(appid)
        return parse_steam_game(appid, entry["data"])

    def fetch_app_price(self, appid: int, country_code: str = "br", language: str = "english") -> Game:
        response = self.session.get(
            STEAM_APPDETAILS_URL,
            params={
                "appids": appid,
                "cc": country_code.lower(),
                "l": language,
                "filters": "basic,price_overview",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        entry = payload.get(str(appid))
        if not entry or not entry.get("success") or not entry.get("data"):
            return Game.not_found(appid)
        data = entry["data"]
        price = extract_price(data)
        return Game(
            appid=appid,
            name=data.get("name", ""),
            price=price["formatted"],
            currency=price["currency"],
            discount_percent=price["discount_percent"],
            store_link=f"https://store.steampowered.com/app/{appid}/",
            header_image=data.get("header_image", ""),
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )

    def fetch_app_details(self, appid: int, country_code: str = "br", language: str = "english") -> dict:
        response = self.session.get(
            STEAM_APPDETAILS_URL,
            params={"appids": appid, "cc": country_code.lower(), "l": language},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        entry = payload.get(str(appid))
        if not entry or not entry.get("success"):
            return {}
        return entry.get("data", {}) or {}

    def fetch_app_reviews(self, appid: int, language: str = "all") -> dict:
        response = self.session.get(
            STEAM_REVIEWS_URL.format(appid=appid),
            params={"json": 1, "language": language, "purchase_type": "all"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("query_summary", {}) or {}

    def search_store(self, term: str, country_code: str = "br", language: str = "english") -> list[SteamApp]:
        term = term.strip()
        if not term:
            return []
        response = self.session.get(
            STEAM_STORESEARCH_URL,
            params={"term": term, "cc": country_code.lower(), "l": language},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        result: list[SteamApp] = []
        seen: set[int] = set()
        for item in payload.get("items", []):
            if item.get("type") != "app":
                continue
            try:
                appid = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            name = str(item.get("name") or "").strip()
            if not name or appid in seen:
                continue
            seen.add(appid)
            result.append(SteamApp(appid=appid, name=name))
        return result

    def discover_coop_games(
        self,
        coop_category: str = "Online Co-op",
        start: int = 0,
        count: int = 25,
        sort_by: str = "Reviews_DESC",
        genre_tag: str = "Any",
    ) -> list[SteamApp]:
        category_id = COOP_CATEGORIES.get(coop_category, COOP_CATEGORIES["Online Co-op"])
        tag_id = GENRE_TAGS.get(genre_tag, "")
        params = {
            "query": "",
            "start": start,
            "count": count,
            "dynamic_data": "",
            "sort_by": sort_by,
            "term": "",
            "category1": "998",
            "category3": category_id,
            "json": 1,
        }
        if tag_id:
            params["tags"] = tag_id
        response = self.session.get(STEAM_DISCOVERY_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        result: list[SteamApp] = []
        seen: set[int] = set()
        for item in payload.get("items", []):
            name = str(item.get("name") or "").strip()
            appid = item.get("id") or appid_from_logo(item.get("logo", ""))
            try:
                appid = int(appid)
            except (TypeError, ValueError):
                continue
            if not name or appid in seen:
                continue
            seen.add(appid)
            result.append(SteamApp(appid=appid, name=name))
        return result


def appid_from_logo(url: str) -> int | None:
    match = re.search(r"/apps/(\d+)/", str(url))
    return int(match.group(1)) if match else None


def parse_steam_game(appid: int, data: dict) -> Game:
    categories = [str(item.get("description", "")) for item in data.get("categories", [])]
    category_text = " | ".join(categories).lower()
    price = extract_price(data)

    return Game(
        appid=appid,
        name=data.get("name", ""),
        local_coop=("local co-op" in category_text or "shared/split screen co-op" in category_text),
        online_coop=("online co-op" in category_text),
        split_screen=("shared/split screen" in category_text or "split screen" in category_text),
        lan_coop=("lan co-op" in category_text),
        genres=[g.get("description", "") for g in data.get("genres", []) if g.get("description")],
        languages=parse_languages(data.get("supported_languages", "")),
        price=price["formatted"],
        currency=price["currency"],
        discount_percent=price["discount_percent"],
        store_link=f"https://store.steampowered.com/app/{appid}/",
        header_image=data.get("header_image", ""),
        updated_at=datetime.now().isoformat(timespec="seconds"),
    )


def extract_price(data: dict) -> dict:
    if data.get("is_free"):
        return {"formatted": "Free", "currency": "", "discount_percent": 0}

    overview = data.get("price_overview")
    if not overview:
        return {"formatted": "N/A", "currency": "", "discount_percent": 0}

    return {
        "formatted": overview.get("initial_formatted") or overview.get("final_formatted") or "N/A",
        "currency": overview.get("currency") or "",
        "discount_percent": int(overview.get("discount_percent") or 0),
    }


def parse_languages(raw: str) -> list[str]:
    if not raw:
        return []

    text = unescape(str(raw))
    text = re.sub(r"<br\s*/?>", ",", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"languages with full audio support", "", text, flags=re.IGNORECASE)
    text = text.replace("\r", ",").replace("\n", ",")

    seen: set[str] = set()
    result: list[str] = []
    for item in text.split(","):
        language = item.strip()
        key = language.casefold()
        if language and key not in seen:
            seen.add(key)
            result.append(language)
    return result


def has_language(languages: list[str], target: str) -> bool:
    normalized = [lang.casefold() for lang in languages]
    target_key = target.casefold()

    if target_key == "portuguese":
        return any(
            "portuguese" in lang or "brazilian portuguese" in lang or "portugal" in lang
            for lang in normalized
        )

    if target_key == "chinese":
        return any("chinese" in lang for lang in normalized)

    return any(target_key in lang for lang in normalized)
