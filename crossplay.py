from __future__ import annotations

import re
from html import unescape
from urllib.parse import quote_plus

import requests


SOURCE_NAME = "crossplaygames.com"
SOURCE_URL = "https://crossplaygames.com/"


class CrossplayClient:
    def __init__(self, timeout: int = 20) -> None:
        self.session = requests.Session()
        self.timeout = timeout
        self.session.headers.update({"User-Agent": "SteamCoopFinder/0.1 personal crossplay lookup"})

    def lookup_game(self, name: str) -> dict:
        name = name.strip()
        if not name:
            return {"status": "Unknown", "platforms": [], "source": SOURCE_NAME}
        url = f"https://crossplaygames.com/search/{quote_plus(name)}"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        html = response.text
        return parse_crossplay_page(html, name)


def parse_crossplay_page(html: str, name: str) -> dict:
    article = best_article_for_name(html, name)
    if not article:
        article = html
    has_crossplay = "CROSSPLAY</strong> ✔" in article or "CROSSPLAY</strong> &#10004" in article
    no_crossplay = "CROSSPLAY</strong> ✖" in article or "CROSSPLAY</strong> &#10006" in article
    platforms = [unescape(label).strip() for _, label in re.findall(
        r'href="https://crossplaygames\.com/platforms/([^"]+)">([^<]+)</a>',
        article,
    )]
    platforms = unique(platforms)
    status = "Yes" if has_crossplay else "No" if no_crossplay else "Unknown"
    return {"status": status, "platforms": platforms, "source": SOURCE_NAME}


def best_article_for_name(html: str, name: str) -> str:
    articles = re.findall(r"<article[\s\S]*?</article>", html)
    wanted = normalize(name)
    for article in articles:
        title_match = re.search(r'<h2 class="entry-title"[^>]*>\s*<a [^>]+>([^<]+)</a>', article)
        if title_match and normalize(unescape(title_match.group(1))) == wanted:
            return article
    for article in articles:
        title_match = re.search(r'<h2 class="entry-title"[^>]*>\s*<a [^>]+>([^<]+)</a>', article)
        if title_match and wanted in normalize(unescape(title_match.group(1))):
            return article
    return articles[0] if articles else ""


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def unique(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
