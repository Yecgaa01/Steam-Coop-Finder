from __future__ import annotations

import json
from pathlib import Path


DEFAULT_CONFIG = {
    "interface_language": "pt",
    "country_code": "ua",
    "page_size": 100,
}


class AppConfig:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(loaded, dict):
            self.data.update({key: loaded[key] for key in DEFAULT_CONFIG if key in loaded})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def interface_language(self) -> str:
        return str(self.data.get("interface_language") or "pt")

    @interface_language.setter
    def interface_language(self, value: str) -> None:
        self.data["interface_language"] = value
        self.save()

    @property
    def country_code(self) -> str:
        return str(self.data.get("country_code") or "ua")

    @country_code.setter
    def country_code(self, value: str) -> None:
        self.data["country_code"] = value
        self.save()

    @property
    def page_size(self) -> int:
        return int(self.data.get("page_size") or 100)

    @page_size.setter
    def page_size(self, value: int) -> None:
        self.data["page_size"] = value
        self.save()
