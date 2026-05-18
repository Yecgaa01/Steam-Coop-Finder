from __future__ import annotations

import csv
import json
from pathlib import Path

from models import Game


EXPORT_HEADERS = [
    "AppID",
    "Name",
    "Local Co-op",
    "Online Co-op",
    "Split Screen",
    "LAN Co-op",
    "Genres",
    "Languages",
    "Full Price",
    "Currency",
    "Discount %",
    "Store Link",
    "Updated At",
]


def export_games_csv(path: str | Path, games: list[Game]) -> None:
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(EXPORT_HEADERS)
        for game in games:
            writer.writerow(
                [
                    game.appid,
                    game.name,
                    yes_no(game.local_coop),
                    yes_no(game.online_coop),
                    yes_no(game.split_screen),
                    yes_no(game.lan_coop),
                    game.genres_text,
                    game.languages_text,
                    game.price,
                    game.currency,
                    game.discount_percent,
                    game.store_link,
                    game.updated_at,
                ]
            )


def game_to_dict(game: Game) -> dict:
    return {
        "appid": game.appid,
        "name": game.name,
        "local_coop": game.local_coop,
        "online_coop": game.online_coop,
        "split_screen": game.split_screen,
        "lan_coop": game.lan_coop,
        "genres": game.genres,
        "languages": game.languages,
        "price": game.price,
        "currency": game.currency,
        "discount_percent": game.discount_percent,
        "store_link": game.store_link,
        "header_image": game.header_image,
        "updated_at": game.updated_at,
    }


def export_games_json(path: str | Path, games: list[Game]) -> None:
    data = [game_to_dict(game) for game in games]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def yes_no(value: bool) -> str:
    return "Yes" if value else "No"
