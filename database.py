from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from models import Game
from catalog import SteamApp


class GameDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    appid INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    local_coop INTEGER NOT NULL DEFAULT 0,
                    online_coop INTEGER NOT NULL DEFAULT 0,
                    split_screen INTEGER NOT NULL DEFAULT 0,
                    lan_coop INTEGER NOT NULL DEFAULT 0,
                    genres_json TEXT NOT NULL DEFAULT '[]',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    languages_json TEXT NOT NULL DEFAULT '[]',
                    price TEXT NOT NULL DEFAULT 'N/A',
                    currency TEXT NOT NULL DEFAULT '',
                    discount_percent INTEGER NOT NULL DEFAULT 0,
                    store_link TEXT NOT NULL DEFAULT '',
                    header_image TEXT NOT NULL DEFAULT '',
                    favorite INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()}
            if "tags_json" not in columns:
                conn.execute("ALTER TABLE games ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'")
            if "favorite" not in columns:
                conn.execute("ALTER TABLE games ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS steam_apps (
                    appid INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    name_key TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS game_prices (
                    appid INTEGER NOT NULL,
                    country_code TEXT NOT NULL,
                    currency TEXT NOT NULL DEFAULT '',
                    price TEXT NOT NULL DEFAULT 'N/A',
                    discount_percent INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (appid, country_code)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_game_prices_country
                ON game_prices(country_code)
                """
            )

    def upsert_game(self, game: Game) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO games (
                    appid, name, local_coop, online_coop, split_screen, lan_coop,
                    genres_json, tags_json, languages_json, price, currency, discount_percent,
                    store_link, header_image, favorite, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(appid) DO UPDATE SET
                    name=excluded.name,
                    local_coop=excluded.local_coop,
                    online_coop=excluded.online_coop,
                    split_screen=excluded.split_screen,
                    lan_coop=excluded.lan_coop,
                    genres_json=excluded.genres_json,
                    tags_json=excluded.tags_json,
                    languages_json=excluded.languages_json,
                    price=excluded.price,
                    currency=excluded.currency,
                    discount_percent=excluded.discount_percent,
                    store_link=excluded.store_link,
                    header_image=excluded.header_image,
                    favorite=games.favorite,
                    updated_at=excluded.updated_at
                """,
                (
                    game.appid,
                    game.name,
                    int(game.local_coop),
                    int(game.online_coop),
                    int(game.split_screen),
                    int(game.lan_coop),
                    json.dumps(game.genres, ensure_ascii=False),
                    json.dumps(game.tags, ensure_ascii=False),
                    json.dumps(game.languages, ensure_ascii=False),
                    game.price,
                    game.currency,
                    game.discount_percent,
                    game.store_link,
                    game.header_image,
                    int(game.favorite),
                    game.updated_at,
                ),
            )

    def update_game_price(self, game: Game, country_code: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE games
                SET price = ?, currency = ?, discount_percent = ?, updated_at = ?
                WHERE appid = ?
                """,
                (game.price, game.currency, game.discount_percent, game.updated_at, game.appid),
            )
            if country_code:
                conn.execute(
                    """
                    INSERT INTO game_prices (appid, country_code, currency, price, discount_percent, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(appid, country_code) DO UPDATE SET
                        currency=excluded.currency,
                        price=excluded.price,
                        discount_percent=excluded.discount_percent,
                        updated_at=excluded.updated_at
                    """,
                    (
                        game.appid,
                        country_code.lower(),
                        game.currency,
                        game.price,
                        game.discount_percent,
                        game.updated_at,
                    ),
                )

    def apply_price_cache(self, games: list[Game], country_code: str) -> list[Game]:
        if not games:
            return games
        appids = [game.appid for game in games]
        placeholders = ",".join("?" for _ in appids)
        params = [country_code.lower(), *appids]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT appid, currency, price, discount_percent, updated_at
                FROM game_prices
                WHERE country_code = ? AND appid IN ({placeholders})
                """,
                params,
            ).fetchall()
        prices = {row["appid"]: row for row in rows}
        for game in games:
            row = prices.get(game.appid)
            if row:
                game.currency = row["currency"]
                game.price = row["price"]
                game.discount_percent = row["discount_percent"]
                game.updated_at = row["updated_at"]
            else:
                game.currency = ""
                game.price = "Not cached"
                game.discount_percent = 0
        return games

    def delete_game(self, appid: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM games WHERE appid = ?", (appid,))

    def set_favorite(self, appid: int, favorite: bool) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE games SET favorite = ? WHERE appid = ?", (int(favorite), appid))

    def clear_games(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM game_prices")
            conn.execute("DELETE FROM games")

    def list_games(self) -> list[Game]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM games ORDER BY name COLLATE NOCASE").fetchall()
        return [self._row_to_game(row) for row in rows]

    def get_game(self, appid: int) -> Game | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM games WHERE appid = ?", (appid,)).fetchone()
        return self._row_to_game(row) if row else None

    def replace_app_catalog(self, apps: list[SteamApp]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM steam_apps")
            conn.executemany(
                "INSERT INTO steam_apps (appid, name, name_key) VALUES (?, ?, ?)",
                [(app.appid, app.name, app.name.casefold()) for app in apps],
            )

    def search_app_catalog(self, query: str, limit: int = 30) -> list[SteamApp]:
        query = query.strip().casefold()
        if not query:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT appid, name
                FROM steam_apps
                WHERE name_key LIKE ?
                ORDER BY
                    CASE WHEN name_key = ? THEN 0
                         WHEN name_key LIKE ? THEN 1
                         ELSE 2
                    END,
                    name COLLATE NOCASE
                LIMIT ?
                """,
                (f"%{query}%", query, f"{query}%", limit),
            ).fetchall()
        return [SteamApp(appid=row["appid"], name=row["name"]) for row in rows]

    def catalog_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM steam_apps").fetchone()
        return int(row["count"])

    def list_genres(self) -> list[str]:
        genres: set[str] = set()
        for game in self.list_games():
            genres.update(game.genres)
            genres.update(game.tags)
        return sorted(genres, key=str.casefold)

    def _row_to_game(self, row: sqlite3.Row) -> Game:
        return Game(
            appid=row["appid"],
            name=row["name"],
            local_coop=bool(row["local_coop"]),
            online_coop=bool(row["online_coop"]),
            split_screen=bool(row["split_screen"]),
            lan_coop=bool(row["lan_coop"]),
            genres=json.loads(row["genres_json"] or "[]"),
            tags=json.loads(row["tags_json"] or "[]"),
            languages=json.loads(row["languages_json"] or "[]"),
            price=row["price"],
            currency=row["currency"],
            discount_percent=row["discount_percent"],
            store_link=row["store_link"],
            favorite=bool(row["favorite"]),
            updated_at=row["updated_at"],
        )
