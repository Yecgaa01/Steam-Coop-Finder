from __future__ import annotations

from models import Game
from steam_api import has_language


class GameFilters:
    def __init__(
        self,
        search_text: str = "",
        require_local: bool = False,
        require_online: bool = False,
        require_split_screen: bool = False,
        require_lan: bool = False,
        languages: list[str] | None = None,
        genres: list[str] | None = None,
        favorites_only: bool = False,
    ) -> None:
        self.search_text = search_text.strip().casefold()
        self.require_local = require_local
        self.require_online = require_online
        self.require_split_screen = require_split_screen
        self.require_lan = require_lan
        self.languages = languages or []
        self.genres = genres or []
        self.favorites_only = favorites_only

    def matches(self, game: Game) -> bool:
        if self.favorites_only and not game.favorite:
            return False
        if self.search_text and self.search_text not in game.name.casefold() and self.search_text not in str(game.appid):
            return False
        if self.require_local and not game.local_coop:
            return False
        if self.require_online and not game.online_coop:
            return False
        if self.require_split_screen and not game.split_screen:
            return False
        if self.require_lan and not game.lan_coop:
            return False
        if self.languages and not all(has_language(game.languages, language) for language in self.languages):
            return False
        if self.genres:
            game_genres = {genre.casefold() for genre in [*game.genres, *game.tags]}
            if not all(genre.casefold() in game_genres for genre in self.genres):
                return False
        return True


def filter_games(games: list[Game], filters: GameFilters) -> list[Game]:
    return [game for game in games if filters.matches(game)]
