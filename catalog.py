from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SteamApp:
    appid: int
    name: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.appid})"
