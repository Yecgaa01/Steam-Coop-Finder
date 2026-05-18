from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Game:
    appid: int
    name: str
    local_coop: bool = False
    online_coop: bool = False
    split_screen: bool = False
    lan_coop: bool = False
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    price: str = "N/A"
    currency: str = ""
    discount_percent: int = 0
    store_link: str = ""
    header_image: str = ""
    favorite: bool = False
    updated_at: str = ""

    @property
    def genres_text(self) -> str:
        values = []
        seen = set()
        for value in [*self.genres, *self.tags]:
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                values.append(value)
        return ", ".join(values)

    @property
    def languages_text(self) -> str:
        return ", ".join(self.languages)

    @classmethod
    def not_found(cls, appid: int) -> "Game":
        return cls(
            appid=appid,
            name="Not found",
            store_link=f"https://store.steampowered.com/app/{appid}/",
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )
