from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from database import GameDatabase
from app_config import AppConfig
from steam_api import SteamClient
from ui_main import MainWindow


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "steam_coop_finder.sqlite"
CONFIG_PATH = BASE_DIR / "data" / "config.json"


def main() -> None:
    app = QApplication([])
    db = GameDatabase(DB_PATH)
    steam = SteamClient()
    config = AppConfig(CONFIG_PATH)
    window = MainWindow(db, steam, config)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
