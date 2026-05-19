from __future__ import annotations

from pathlib import Path
from subprocess import Popen
from sys import executable, argv
from time import sleep

from PySide6.QtCore import QByteArray, QObject, QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_config import AppConfig
from catalog import SteamApp
from steam_curator_crossplay import SteamCuratorCrossplayClient
from database import GameDatabase
from exporters import export_games_csv, export_games_json
from filters import GameFilters, filter_games
from models import Game
from steam_api import COOP_CATEGORIES, GENRE_TAGS, SteamClient
from tag_labels import tag_choices, tag_label
from translations import steam_language_for_interface, t


LANGUAGE_OPTIONS = [
    "English",
    "Portuguese",
    "Spanish",
    "French",
    "German",
    "Italian",
    "Japanese",
    "Korean",
    "Chinese",
    "Russian",
    "Polish",
    "Turkish",
    "Dutch",
    "Arabic",
]

STEAM_LANGUAGES = {
    "English": "english",
    "Português": "brazilian",
}

REGIONS = {
    "Ukraine / UAH": "ua",
    "Brazil / BRL": "br",
    "United States / USD": "us",
    "Portugal / EUR": "pt",
    "Germany / EUR": "de",
    "France / EUR": "fr",
    "Spain / EUR": "es",
    "Italy / EUR": "it",
    "Netherlands / EUR": "nl",
    "Poland / PLN": "pl",
    "United Kingdom / GBP": "gb",
    "Canada / CAD": "ca",
    "Mexico / MXN": "mx",
    "Argentina / ARS": "ar",
    "Chile / CLP": "cl",
    "Colombia / COP": "co",
    "Peru / PEN": "pe",
    "Uruguay / UYU": "uy",
    "Japan / JPY": "jp",
    "China / CNY": "cn",
    "South Korea / KRW": "kr",
    "Taiwan / TWD": "tw",
    "Hong Kong / HKD": "hk",
    "India / INR": "in",
    "Indonesia / IDR": "id",
    "Malaysia / MYR": "my",
    "Philippines / PHP": "ph",
    "Singapore / SGD": "sg",
    "Thailand / THB": "th",
    "Vietnam / VND": "vn",
    "Australia / AUD": "au",
    "New Zealand / NZD": "nz",
    "Turkey / TRY": "tr",
    "Saudi Arabia / SAR": "sa",
    "United Arab Emirates / AED": "ae",
    "South Africa / ZAR": "za",
}

COLUMNS = [
    "Name",
    "★",
    "Local",
    "Online",
    "Split",
    "LAN",
    "Genres",
    "Updated",
]


class MainWindow(QMainWindow):
    def __init__(self, db: GameDatabase, steam: SteamClient, config: AppConfig) -> None:
        super().__init__()
        self.db = db
        self.steam = steam
        self.config = config
        self.lang = config.interface_language
        self.all_games: list[Game] = []
        self.visible_games: list[Game] = []
        self.language_checks: dict[str, QCheckBox] = {}
        self.selected_genres: list[str] = []
        self.mass_thread: QThread | None = None
        self.log_messages: list[str] = []
        self.current_page = 0
        self.page_size = config.page_size
        self.filtered_games: list[Game] = []

        self.setWindowTitle("Steam Coop Finder")
        self.resize(1320, 760)
        self._build_ui()
        self._apply_style()
        self.reload_games()

    def tr(self, key: str, **kwargs: object) -> str:
        return t(self.lang, key, **kwargs)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("Steam Coop Finder")
        title.setObjectName("Title")
        subtitle = QLabel(self.tr("app_subtitle"))
        subtitle.setObjectName("Subtitle")
        title_col = QVBoxLayout()
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_row.addLayout(title_col, 1)
        settings_button = QPushButton(self.tr("settings"))
        settings_button.clicked.connect(self.open_settings)
        title_row.addWidget(settings_button)
        root_layout.addLayout(title_row)

        top_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("search_placeholder"))
        self.search_input.textChanged.connect(self.apply_filters)
        search_catalog_button = QPushButton(self.tr("search"))
        search_catalog_button.clicked.connect(self.search_game_by_name)
        discover_button = QPushButton(self.tr("discover"))
        discover_button.clicked.connect(self.discover_games)
        pause_button = QPushButton(self.tr("pause"))
        pause_button.clicked.connect(self.toggle_mass_import_pause)
        mass_button = QPushButton(self.tr("mass_import"))
        mass_button.clicked.connect(self.mass_import)
        log_button = QPushButton("Log")
        log_button.clicked.connect(self.show_log)
        update_all = QPushButton(self.tr("update"))
        update_all.clicked.connect(self.update_all_games)
        top_row.addWidget(self.search_input, 1)
        top_row.addWidget(search_catalog_button)
        top_row.addWidget(discover_button)
        top_row.addWidget(mass_button)
        top_row.addWidget(pause_button)
        top_row.addWidget(log_button)
        top_row.addWidget(update_all)
        root_layout.addLayout(top_row)

        filter_row = QHBoxLayout()
        self.online_check = QCheckBox(self.tr("online"))
        self.local_check = QCheckBox(self.tr("local"))
        self.split_check = QCheckBox(self.tr("split"))
        self.lan_check = QCheckBox(self.tr("lan"))
        for checkbox in [self.online_check, self.local_check, self.split_check, self.lan_check]:
            checkbox.stateChanged.connect(self.apply_filters)
            filter_row.addWidget(checkbox)
        self.favorite_check = QCheckBox("★")
        self.favorite_check.stateChanged.connect(self.apply_filters)
        filter_row.addWidget(self.favorite_check)
        language_button = QPushButton(self.tr("language"))
        language_button.clicked.connect(self.open_language_filter)
        filter_row.addWidget(language_button)
        self.language_checks = {}
        filter_row.addWidget(QLabel(self.tr("genre")))
        self.genre_input = QLineEdit()
        self.genre_input.setPlaceholderText("Souls-like, Rogue-like...")
        self.genre_input.returnPressed.connect(self.add_genre_filter)
        self.genre_completer = QCompleter([])
        self.genre_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.genre_completer.activated.connect(self.add_genre_from_completion)
        self.genre_input.setCompleter(self.genre_completer)
        filter_row.addWidget(self.genre_input, 1)
        self.genre_tags = QLabel("")
        self.genre_tags.setObjectName("Tags")
        filter_row.addWidget(self.genre_tags, 1)
        filter_row.addStretch()
        root_layout.addLayout(filter_row)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellClicked.connect(self.handle_table_cell_clicked)
        self.table.doubleClicked.connect(self.show_selected_game_details)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        root_layout.addWidget(self.table, 1)

        footer_row = QHBoxLayout()
        self.prev_button = QPushButton(self.tr("previous"))
        self.prev_button.clicked.connect(self.previous_page)
        self.next_button = QPushButton(self.tr("next"))
        self.next_button.clicked.connect(self.next_page)
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["50", "100", "250"])
        self.page_size_combo.setCurrentText(str(self.config.page_size))
        self.page_size_combo.currentTextChanged.connect(self.change_page_size)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("Status")
        footer_row.addWidget(self.prev_button)
        footer_row.addWidget(self.next_button)
        footer_row.addWidget(QLabel("Per page"))
        footer_row.addWidget(self.page_size_combo)
        footer_row.addStretch()
        footer_row.addWidget(self.status_label)
        root_layout.addLayout(footer_row)

        self.setCentralWidget(root)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #111827;
                color: #e5e7eb;
                font-size: 13px;
            }
            #Sidebar {
                background: #0b1220;
                border: 1px solid #243044;
                border-radius: 14px;
            }
            #Title {
                font-size: 24px;
                font-weight: 700;
                color: #f8fafc;
            }
            #Subtitle, #Status, #Tags {
                color: #9ca3af;
            }
            QLineEdit, QComboBox {
                background: #172033;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px;
                color: #f8fafc;
            }
            QPushButton {
                background: #2563eb;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                color: white;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #1d4ed8;
            }
            QCheckBox {
                padding: 2px;
            }
            QTableWidget {
                background: #0f172a;
                alternate-background-color: #111c30;
                border: 1px solid #243044;
                border-radius: 12px;
                gridline-color: transparent;
                selection-background-color: #1d4ed8;
                selection-color: white;
            }
            QHeaderView::section {
                background: #172033;
                color: #f8fafc;
                border: none;
                padding: 8px;
                font-weight: 700;
            }
            """
        )
        QApplication.instance().setFont(QFont("Segoe UI", 10))

    def country_code(self) -> str:
        return self.config.country_code

    def steam_language(self) -> str:
        return steam_language_for_interface(self.lang)

    def region_label(self) -> str:
        return next((label for label, code in REGIONS.items() if code == self.config.country_code), "Ukraine / UAH")

    def reload_games(self) -> None:
        self.all_games = self.db.apply_price_cache(self.db.list_games(), self.country_code())
        self.refresh_genre_suggestions()
        self.apply_filters()

    def refresh_genre_suggestions(self) -> None:
        genres = sorted(set(self.db.list_genres()) | set(GENRE_TAGS.keys()), key=lambda tag: tag_label(tag, self.lang).casefold())
        self.genre_completer.model().setStringList([tag_label(genre, self.lang) for genre in genres])

    def open_language_filter(self) -> None:
        dialog = LanguageFilterDialog(self.language_checks, self.lang, self)
        if dialog.exec() == QDialog.Accepted:
            self.language_checks = dialog.language_checks
            self.apply_filters()

    def current_filters(self) -> GameFilters:
        languages = [language for language, check in self.language_checks.items() if check.isChecked()]
        return GameFilters(
            search_text=self.search_input.text(),
            require_local=self.local_check.isChecked(),
            require_online=self.online_check.isChecked(),
            require_split_screen=self.split_check.isChecked(),
            require_lan=self.lan_check.isChecked(),
            languages=languages,
            genres=self.selected_genres,
            favorites_only=self.favorite_check.isChecked(),
        )

    def apply_filters(self) -> None:
        self.filtered_games = filter_games(self.all_games, self.current_filters())
        max_page = max(0, (len(self.filtered_games) - 1) // self.page_size) if self.filtered_games else 0
        self.current_page = min(self.current_page, max_page)
        start = self.current_page * self.page_size
        end = start + self.page_size
        self.visible_games = self.filtered_games[start:end]
        self.populate_table(self.visible_games)
        self.status_label.setText(
            f"{len(self.filtered_games)} de {len(self.all_games)} jogos visíveis · "
            f"{self.tr('page')} {self.current_page + 1}/{max_page + 1}"
        )
        self.prev_button.setEnabled(self.current_page > 0)
        self.next_button.setEnabled(self.current_page < max_page)


    def populate_table(self, games: list[Game]) -> None:
        self.table.setUpdatesEnabled(False)
        self.appid_by_row: dict[int, int] = {}
        self.table.setRowCount(len(games))
        for row, game in enumerate(games):
            values = [
                game.name,
                "★" if game.favorite else "☆",
                yes_no(game.local_coop),
                yes_no(game.online_coop),
                yes_no(game.split_screen),
                yes_no(game.lan_coop),
                game.genres_text,
                game.updated_at,
            ]
            self.appid_by_row[row] = game.appid
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in [1, 2, 3, 4, 5]:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
        self.table.setUpdatesEnabled(True)

    def handle_table_cell_clicked(self, row: int, column: int) -> None:
        if column != 1:
            return
        appid = self.appid_by_row.get(row)
        if appid is None:
            return
        game = next((item for item in self.all_games if item.appid == appid), None)
        if not game:
            return
        game.favorite = not game.favorite
        self.db.set_favorite(appid, game.favorite)
        item = self.table.item(row, column)
        if item:
            item.setText("★" if game.favorite else "☆")
        if self.favorite_check.isChecked() and not game.favorite:
            self.apply_filters()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self.lang, self)
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.should_clear_list:
            self.db.clear_games()
            self.reload_games()
            self.status_label.setText(self.tr("clear_list_done"))
            return
        self.config.country_code = dialog.country_code
        old_lang = self.config.interface_language
        self.config.interface_language = dialog.interface_language
        self.reload_games()
        if dialog.interface_language != old_lang:
            Popen([executable, *argv])
            QApplication.quit()

    def add_log(self, message: str) -> None:
        self.log_messages.append(message)
        self.status_label.setText(message)

    def show_log(self) -> None:
        text = "\n".join(self.log_messages[-200:]) or "Log vazio."
        QMessageBox.information(self, "Log", text)

    def change_page_size(self, value: str) -> None:
        self.page_size = int(value)
        self.config.page_size = self.page_size
        self.current_page = 0
        self.apply_filters()

    def previous_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self.apply_filters()

    def next_page(self) -> None:
        max_page = max(0, (len(self.filtered_games) - 1) // self.page_size) if self.filtered_games else 0
        if self.current_page < max_page:
            self.current_page += 1
            self.apply_filters()

    def search_game_by_name(self) -> None:
        dialog = GameSearchDialog(
            self.steam,
            self.country_code(),
            {game.appid for game in self.all_games},
            self.steam_language(),
            self,
        )
        if dialog.exec() == QDialog.Accepted and dialog.selected_apps:
            imported = 0
            for index, app in enumerate(dialog.selected_apps, start=1):
                self.status_label.setText(f"Importando {index}/{len(dialog.selected_apps)}: {app.name}")
                QApplication.processEvents()
                try:
                    game = self.steam.fetch_app(app.appid, self.country_code(), self.steam_language())
                    self.db.upsert_game(game)
                    self.db.update_game_price(game, self.country_code())
                    imported += 1
                except Exception as exc:
                    self.add_log(f"Erro ao importar {app.name}: {exc}")
            self.reload_games()
            QMessageBox.information(self, "Importação concluída", f"{imported} jogos foram importados.")

    def discover_games(self) -> None:
        dialog = DiscoveryDialog(
            self.steam,
            self.country_code(),
            {game.appid for game in self.all_games},
            self,
        )
        if dialog.exec() == QDialog.Accepted and dialog.selected_apps:
            imported = 0
            for index, app in enumerate(dialog.selected_apps, start=1):
                self.status_label.setText(f"Importando {index}/{len(dialog.selected_apps)}: {app.name}")
                QApplication.processEvents()
                try:
                    game = self.steam.fetch_app(app.appid, self.country_code(), self.steam_language())
                    if dialog.genre_tag != "Any":
                        game.tags.append(dialog.genre_tag)
                    self.db.upsert_game(game)
                    self.db.update_game_price(game, self.country_code())
                    imported += 1
                except Exception as exc:
                    self.add_log(f"Erro ao importar {app.name}: {exc}")
            self.reload_games()
            QMessageBox.information(self, "Importação concluída", f"{imported} jogos foram importados.")

    def toggle_mass_import_pause(self) -> None:
        if not self.mass_worker:
            self.status_label.setText("Nenhum Mass Import em andamento.")
            return
        paused = self.mass_worker.toggle_pause()
        self.status_label.setText("Mass Import pausado." if paused else "Mass Import retomado.")

    def mass_import(self) -> None:
        if self.mass_worker:
            self.mass_worker.request_stop()
            self.status_label.setText("Parando importação em lote...")
            return

        dialog = MassImportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        autosave_path = Path(__file__).resolve().parent / "data" / "mass_import_autosave.json"
        self.mass_thread = QThread(self)
        self.mass_worker = MassImportWorker(
            db_path=self.db.path,
            country_code=self.country_code(),
            steam_language=self.steam_language(),
            existing_appids={game.appid for game in self.all_games},
            autosave_path=autosave_path,
            coop_category=dialog.coop_category,
            genre_tag=dialog.genre_tag,
            limit=dialog.limit,
            page_size=dialog.page_size,
            sort_by=dialog.sort_by,
            delay_ms=dialog.delay_ms,
        )
        self.mass_worker.moveToThread(self.mass_thread)
        self.mass_thread.started.connect(self.mass_worker.run)
        self.mass_worker.progress.connect(self.status_label.setText)
        self.mass_worker.batch_saved.connect(self.reload_games)
        self.mass_worker.finished.connect(self.on_mass_import_finished)
        self.mass_worker.finished.connect(self.mass_thread.quit)
        self.mass_worker.finished.connect(self.mass_worker.deleteLater)
        self.mass_thread.finished.connect(self.mass_thread.deleteLater)
        self.mass_thread.start()
        self.status_label.setText("Mass Import iniciado.")

    def on_mass_import_finished(self, imported: int, scanned: int, stopped: bool, autosave_path: str) -> None:
        self.reload_games()
        status = "interrompida" if stopped else "concluída"
        QMessageBox.information(
            self,
            "Mass import",
            f"Importação {status}.\nImportados: {imported}\nEscaneados: {scanned}\nAutosave JSON:\n{autosave_path}",
        )
        self.mass_worker = None
        self.mass_thread = None

    def update_selected_game(self) -> None:
        appid = self.selected_appid()
        if appid is None:
            QMessageBox.information(self, "Nada selecionado", "Selecione um jogo na tabela.")
            return
        self.fetch_and_save(appid)

    def update_all_games(self) -> None:
        if not self.all_games:
            QMessageBox.information(self, "Sem jogos", "Busque um jogo na Steam primeiro.")
            return
        for index, game in enumerate(list(self.all_games), start=1):
            self.status_label.setText(f"Atualizando {index}/{len(self.all_games)}: {game.appid}")
            QApplication.processEvents()
            self.fetch_and_save(game.appid, show_message=False)
        self.reload_games()
        QMessageBox.information(self, "Atualizado", "Todos os jogos foram atualizados.")

    def update_prices_only(self, show_done_message: bool = True) -> None:
        if not self.all_games:
            QMessageBox.information(self, "Sem jogos", "Busque um jogo na Steam primeiro.")
            return
        for index, game in enumerate(list(self.all_games), start=1):
            self.status_label.setText(f"Atualizando preços {index}/{len(self.all_games)}: {game.name}")
            QApplication.processEvents()
            try:
                refreshed = self.steam.fetch_app_price(game.appid, self.country_code(), self.steam_language())
                self.db.update_game_price(refreshed, self.country_code())
            except Exception as exc:
                if "429" in str(exc):
                    self.status_label.setText("Rate limit da Steam. Pausando 120s antes de continuar preços...")
                    QApplication.processEvents()
                    sleep(120)
                    try:
                        refreshed = self.steam.fetch_app_price(game.appid, self.country_code(), self.steam_language())
                        self.db.update_game_price(refreshed, self.country_code())
                    except Exception:
                        continue
                else:
                    continue
            sleep(1)
        self.reload_games()
        if show_done_message:
            QMessageBox.information(self, "Preços atualizados", "Preços/moedas/descontos foram atualizados.")

    def on_region_changed(self) -> None:
        if not self.all_games:
            return
        self.reload_games()
        self.status_label.setText(
            "Moeda trocada instantaneamente. Jogos sem cache nessa região aparecem como Not cached."
        )

    def update_all_prices(self) -> None:
        self.on_region_changed()

    def fetch_and_save(self, appid: int, show_message: bool = True) -> None:
        try:
            self.status_label.setText(f"Buscando AppID {appid}...")
            QApplication.processEvents()
            game = self.steam.fetch_app(appid, self.country_code(), self.steam_language())
            self.db.upsert_game(game)
            self.db.update_game_price(game, self.country_code())
            self.reload_games()
            if show_message:
                QMessageBox.information(self, "Jogo atualizado", f"{game.name} foi salvo.")
        except Exception as exc:
            QMessageBox.critical(self, "Erro", f"Não foi possível buscar {appid}:\n{exc}")
            self.status_label.setText("Erro ao buscar jogo")

    def selected_appid(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.appid_by_row.get(row)

    def show_selected_game_details(self) -> None:
        appid = self.selected_appid()
        if appid is None:
            return
        game = next((item for item in self.all_games if item.appid == appid), None)
        if not game:
            return
        dialog = GameDetailsDialog(game, self.steam, self.country_code(), self.steam_language(), self.lang, self, self.db)
        dialog.exec()

    def open_selected_game(self) -> None:
        appid = self.selected_appid()
        if appid is None:
            return
        QDesktopServices.openUrl(QUrl(f"https://store.steampowered.com/app/{appid}/"))

    def add_genre_from_completion(self, genre: str) -> None:
        self.add_genre(genre)

    def add_genre_filter(self) -> None:
        self.add_genre(self.genre_input.text())

    def add_genre(self, genre: str) -> None:
        genre = genre.strip()
        if not genre:
            return
        known = {tag_label(item, self.lang).casefold(): item for item in (set(self.db.list_genres()) | set(GENRE_TAGS.keys()))}
        known.update({item.casefold(): item for item in (set(self.db.list_genres()) | set(GENRE_TAGS.keys()))})
        genre = known.get(genre.casefold())
        if not genre:
            self.genre_input.clear()
            return
        if genre.casefold() not in [item.casefold() for item in self.selected_genres]:
            self.selected_genres.append(genre)
        self.genre_input.clear()
        self.update_genre_tags()
        self.apply_filters()

    def clear_genres(self) -> None:
        self.selected_genres.clear()
        self.update_genre_tags()
        self.apply_filters()

    def update_genre_tags(self) -> None:
        if not self.selected_genres:
            self.genre_tags.setText("")
        else:
            self.genre_tags.setText("  ".join(f"{tag_label(genre, self.lang)} ×" for genre in self.selected_genres))

    def export_csv(self) -> None:
        default_path = str(Path.home() / "steam_coop_finder.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar CSV", default_path, "CSV (*.csv)")
        if not path:
            return
        export_games_csv(path, self.visible_games)
        QMessageBox.information(self, "Exportado", f"CSV salvo em:\n{path}")

    def export_json(self) -> None:
        default_path = str(Path.home() / "steam_coop_finder.json")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar JSON", default_path, "JSON (*.json)")
        if not path:
            return
        export_games_json(path, self.visible_games)
        QMessageBox.information(self, "Exportado", f"JSON salvo em:\n{path}")


class LanguageFilterDialog(QDialog):
    def __init__(self, current_checks: dict[str, QCheckBox], language: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.language = language
        self.setWindowTitle(t(language, "language"))
        self.resize(320, 420)
        self.checkboxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        for item in LANGUAGE_OPTIONS:
            checkbox = QCheckBox(item)
            checkbox.setChecked(current_checks.get(item).isChecked() if item in current_checks else False)
            self.checkboxes[item] = checkbox
            layout.addWidget(checkbox)

        buttons = QHBoxLayout()
        clear_button = QPushButton("Clear" if language == "en" else "Limpar")
        clear_button.clicked.connect(self.clear_all)
        close_button = QPushButton(t(language, "close"))
        close_button.clicked.connect(self.reject)
        apply_button = QPushButton(t(language, "apply"))
        apply_button.clicked.connect(self.accept)
        buttons.addWidget(clear_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        buttons.addWidget(apply_button)
        layout.addLayout(buttons)

    @property
    def language_checks(self) -> dict[str, QCheckBox]:
        return self.checkboxes

    def clear_all(self) -> None:
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(False)


class MassImportWorker(QObject):
    progress = Signal(str)
    batch_saved = Signal()
    finished = Signal(int, int, bool, str)

    def __init__(
        self,
        db_path: str | Path,
        country_code: str,
        steam_language: str,
        existing_appids: set[int],
        autosave_path: str | Path,
        coop_category: str,
        genre_tag: str,
        limit: int,
        page_size: int,
        sort_by: str,
        delay_ms: int,
    ) -> None:
        super().__init__()
        self.db_path = Path(db_path)
        self.country_code = country_code
        self.steam_language = steam_language
        self.existing_appids = set(existing_appids)
        self.autosave_path = Path(autosave_path)
        self.coop_category = coop_category
        self.genre_tag = genre_tag
        self.limit = limit
        self.page_size = page_size
        self.sort_by = sort_by
        self.delay_ms = delay_ms
        self._stop_requested = False
        self._pause_requested = False

    @Slot()
    def run(self) -> None:
        db = GameDatabase(self.db_path)
        steam = SteamClient()
        imported = 0
        scanned = 0
        stopped = False

        try:
            while scanned < self.limit and not self._stop_requested:
                count = min(self.page_size, self.limit - scanned)
                if self.genre_tag == "Any":
                    candidates = steam.discover_popular_genre_games(
                        coop_category=self.coop_category,
                        start=scanned,
                        count=count,
                        sort_by=self.sort_by,
                    )
                else:
                    candidates = steam.discover_coop_games(
                        coop_category=self.coop_category,
                        start=scanned,
                        count=count,
                        sort_by=self.sort_by,
                        genre_tag=self.genre_tag,
                    )
                if not candidates:
                    break

                scanned += count
                for app in candidates:
                    if not self._wait_if_paused():
                        stopped = True
                        break
                    if self._stop_requested:
                        stopped = True
                        break
                    if app.appid in self.existing_appids:
                        continue
                    self.existing_appids.add(app.appid)
                    self.progress.emit(
                        f"Mass import: {imported} importados / {scanned} escaneados — {app.name}"
                    )
                    try:
                        game = steam.fetch_app(app.appid, self.country_code, self.steam_language)
                        if self.genre_tag != "Any" and self.genre_tag not in game.tags:
                            game.tags.append(self.genre_tag)
                        db.upsert_game(game)
                        db.update_game_price(game, self.country_code)
                        imported += 1
                    except Exception as exc:
                        if "429" in str(exc):
                            self.progress.emit("Rate limit da Steam. Pausando 180s...")
                            if not self._wait_interruptible(180):
                                stopped = True
                                break
                        continue

                    if imported % 25 == 0:
                        export_games_json(self.autosave_path, db.list_games())
                        self.batch_saved.emit()
                    if not self._wait_interruptible(self.delay_ms / 1000):
                        stopped = True
                        break

                self.batch_saved.emit()
                if stopped:
                    break

            export_games_json(self.autosave_path, db.list_games())
            self.batch_saved.emit()
        finally:
            self.finished.emit(imported, scanned, stopped or self._stop_requested, str(self.autosave_path))

    def request_stop(self) -> None:
        self._stop_requested = True
        self._pause_requested = False

    def toggle_pause(self) -> bool:
        self._pause_requested = not self._pause_requested
        return self._pause_requested

    def _wait_if_paused(self) -> bool:
        while self._pause_requested and not self._stop_requested:
            self.progress.emit("Mass Import pausado. Clique Pausar para continuar.")
            sleep(0.2)
        return not self._stop_requested

    def _wait_interruptible(self, seconds: float) -> bool:
        remaining = seconds
        while remaining > 0:
            if not self._wait_if_paused():
                return False
            if self._stop_requested:
                return False
            interval = min(0.2, remaining)
            sleep(interval)
            remaining -= interval
        return True


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, language: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.language = language
        self.setWindowTitle(t(language, "settings"))
        self.resize(360, 230)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t(language, "region_currency")))
        self.region_combo = QComboBox()
        self.region_combo.addItems(REGIONS.keys())
        current_region = next((label for label, code in REGIONS.items() if code == config.country_code), "Ukraine / UAH")
        self.region_combo.setCurrentText(current_region)
        layout.addWidget(self.region_combo)

        layout.addWidget(QLabel(t(language, "interface_language")))
        self.language_combo = QComboBox()
        self.language_combo.addItem("Português", "pt")
        self.language_combo.addItem("English", "en")
        self.language_combo.setCurrentIndex(0 if config.interface_language == "pt" else 1)
        layout.addWidget(self.language_combo)

        clear_button = QPushButton(t(language, "clear_list"))
        clear_button.clicked.connect(self.accept_clear_list)
        layout.addWidget(clear_button)

        buttons = QHBoxLayout()
        close_button = QPushButton(t(language, "close"))
        close_button.clicked.connect(self.reject)
        apply_button = QPushButton(t(language, "apply"))
        apply_button.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(close_button)
        buttons.addWidget(apply_button)
        layout.addLayout(buttons)

    @property
    def should_clear_list(self) -> bool:
        return getattr(self, "_should_clear_list", False)

    def accept_clear_list(self) -> None:
        if QMessageBox.question(self, t(self.language, "settings"), t(self.language, "clear_list_confirm")) == QMessageBox.Yes:
            self._should_clear_list = True
            self.accept()

    @property
    def country_code(self) -> str:
        return REGIONS[self.region_combo.currentText()]

    @property
    def interface_language(self) -> str:
        return self.language_combo.currentData()


class GameDetailsDialog(QDialog):
    def __init__(self, game: Game, steam: SteamClient, country_code: str, steam_language: str, language: str, parent: QWidget | None = None, db: GameDatabase | None = None) -> None:
        super().__init__(parent)
        self.game = game
        self.steam = steam
        self.country_code = country_code
        self.steam_language = steam_language
        self.language = language
        self.db = db
        self.favorite = game.favorite
        self.setWindowTitle(game.name)
        self.resize(520, 420)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        top_row = QHBoxLayout()
        self.image_label = QLabel("Loading image...")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(210, 100)
        top_row.addWidget(self.image_label)

        title_col = QVBoxLayout()
        self.title_label = QLabel(game.name)
        self.title_label.setObjectName("Title")
        self.title_label.setWordWrap(True)
        title_col.addWidget(self.title_label)
        self.description_label = QLabel("")
        self.description_label.setWordWrap(True)
        self.description_label.setMaximumHeight(70)
        self.description_label.setObjectName("Subtitle")
        title_col.addWidget(self.description_label)
        top_row.addLayout(title_col, 1)
        root.addLayout(top_row)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(6)
        root.addLayout(self.grid)
        self.value_labels: dict[str, QLabel] = {}
        for row, key in enumerate([
            t(self.language, "developer"),
            t(self.language, "publisher"),
            t(self.language, "reviews"),
            t(self.language, "genres"),
            t(self.language, "categories"),
            t(self.language, "full_price"),
            t(self.language, "current_price"),
            "Crossplay",
        ]):
            label = QLabel(key)
            label.setObjectName("Subtitle")
            value = QLabel("Loading...")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if key == t(self.language, "reviews"):
                reviews_widget = QWidget()
                reviews_layout = QHBoxLayout(reviews_widget)
                reviews_layout.setContentsMargins(0, 0, 0, 0)
                reviews_layout.setSpacing(8)
                self.review_score_label = QLabel("Loading...")
                self.review_positive_label = QLabel("👍 0")
                self.review_positive_label.setStyleSheet("color: #22c55e; font-weight: 700;")
                self.review_negative_label = QLabel("👎 0")
                self.review_negative_label.setStyleSheet("color: #ef4444; font-weight: 700;")
                self.review_total_label = QLabel("= 0")
                reviews_layout.addWidget(self.review_score_label)
                reviews_layout.addWidget(self.review_positive_label)
                reviews_layout.addWidget(self.review_negative_label)
                reviews_layout.addWidget(self.review_total_label)
                reviews_layout.addStretch()
                self.grid.addWidget(label, row, 0, Qt.AlignTop)
                self.grid.addWidget(reviews_widget, row, 1)
                self.value_labels[key] = value
                continue
            self.grid.addWidget(label, row, 0, Qt.AlignTop)
            self.grid.addWidget(value, row, 1)
            self.value_labels[key] = value

        button_row = QHBoxLayout()
        favorite_button = QPushButton("★" if self.favorite else "☆")
        favorite_button.clicked.connect(self.toggle_favorite)
        self.favorite_button = favorite_button
        open_button = QPushButton(t(self.language, "open_steam"))
        open_button.clicked.connect(self.open_steam_page)
        close_button = QPushButton(t(self.language, "close"))
        close_button.clicked.connect(self.accept)
        button_row.addStretch()
        button_row.addWidget(favorite_button)
        button_row.addWidget(open_button)
        button_row.addWidget(close_button)
        root.addLayout(button_row)

        self.load_details()

    def load_details(self) -> None:
        try:
            details = self.steam.fetch_app_details(self.game.appid, self.country_code, self.steam_language)
        except Exception:
            details = {}
        try:
            reviews = self.steam.fetch_app_reviews(self.game.appid)
        except Exception:
            reviews = {}

        name = details.get("name") or self.game.name
        developers = ", ".join(details.get("developers", []) or []) or "N/A"
        publishers = ", ".join(details.get("publishers", []) or []) or "N/A"
        genres = ", ".join(g.get("description", "") for g in details.get("genres", []) if g.get("description")) or self.game.genres_text or "N/A"
        categories = ", ".join(c.get("description", "") for c in details.get("categories", []) if c.get("description")) or "N/A"
        short_description = details.get("short_description") or ""
        header_image = details.get("header_image") or self.game.header_image
        price_data = details.get("price_overview") or {}
        full_price = price_data.get("initial_formatted") or price_data.get("final_formatted") or ("Free" if details.get("is_free") else "Unavailable")
        final_price = price_data.get("final_formatted") or ("Free" if details.get("is_free") else "Unavailable")
        currency = price_data.get("currency") or self.game.currency or ""

        review_text = translate_review_score(self.language, reviews.get("review_score_desc") or "N/A")
        total_reviews = reviews.get("total_reviews", 0)
        total_positive = reviews.get("total_positive", 0)
        total_negative = reviews.get("total_negative", 0)

        self.title_label.setText(name)
        self.description_label.setText(short_description)
        self.value_labels[t(self.language, "developer")].setText(developers)
        self.value_labels[t(self.language, "publisher")].setText(publishers)
        self.review_score_label.setText(review_text)
        self.review_positive_label.setText(f"👍 {total_positive}")
        self.review_negative_label.setText(f"👎 {total_negative}")
        self.review_total_label.setText(f"= {total_reviews}")
        self.value_labels[t(self.language, "genres")].setText(genres)
        self.value_labels[t(self.language, "categories")].setText(categories)
        self.value_labels[t(self.language, "full_price")].setText(f"{currency} {full_price}".strip())
        self.value_labels[t(self.language, "current_price")].setText(final_price)
        self.load_crossplay()
        self.load_image(header_image)

    def load_crossplay(self) -> None:
        try:
            data = SteamCuratorCrossplayClient().lookup_appid(self.game.appid, self.game.name)
            if data["status"] == "Yes":
                platforms = ", ".join(data["platforms"]) if data["platforms"] else t(self.language, "crossplay_unknown")
                text = f"{t(self.language, 'crossplay_yes')} · {t(self.language, 'platforms')}: {platforms}"
            elif data["status"] == "No":
                text = t(self.language, "crossplay_no")
            else:
                text = t(self.language, "crossplay_unknown")
            note = f"\nNote: {data['note']}" if data.get("note") and data.get("source") != "Manual override" else ""
            self.value_labels["Crossplay"].setText(
                f"{text}{note}"
            )
        except Exception:
            self.value_labels["Crossplay"].setText(t(self.language, "crossplay_unknown"))

    def load_image(self, url: str) -> None:
        if not url:
            self.image_label.setText("No image")
            return
        try:
            response = self.steam.session.get(url, timeout=20)
            response.raise_for_status()
            pixmap = QPixmap()
            pixmap.loadFromData(QByteArray(response.content))
            if pixmap.isNull():
                self.image_label.setText("Image unavailable")
                return
            self.image_label.setPixmap(pixmap.scaled(210, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            self.image_label.setText("Image unavailable")

    def toggle_favorite(self) -> None:
        self.favorite = not self.favorite
        self.game.favorite = self.favorite
        self.favorite_button.setText("★" if self.favorite else "☆")
        if self.db:
            self.db.set_favorite(self.game.appid, self.favorite)

    def open_steam_page(self) -> None:
        QDesktopServices.openUrl(QUrl(f"https://store.steampowered.com/app/{self.game.appid}/"))


class MassImportDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mass import")
        self.resize(420, 260)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Importação em lote. Pode demorar bastante."))

        layout.addWidget(QLabel("Tipo de coop"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(COOP_CATEGORIES.keys())
        layout.addWidget(self.category_combo)

        layout.addWidget(QLabel("Gênero/tag"))
        self.genre_combo = QComboBox()
        self.genre_choices = tag_choices(list(GENRE_TAGS.keys()), getattr(parent, 'lang', 'en'))
        for label, value in self.genre_choices:
            self.genre_combo.addItem(label, value)
        layout.addWidget(self.genre_combo)

        layout.addWidget(QLabel("Limite"))
        self.limit_combo = QComboBox()
        self.limit_combo.addItems(["20", "50", "100", "200", "250"])
        layout.addWidget(self.limit_combo)

        layout.addWidget(QLabel("Delay entre detalhes"))
        self.delay_combo = QComboBox()
        self.delay_combo.addItems(["500 ms", "750 ms", "1000 ms", "1500 ms", "2000 ms", "3000 ms"])
        layout.addWidget(self.delay_combo)

        buttons = QHBoxLayout()
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        start_button = QPushButton("Start")
        start_button.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(start_button)
        layout.addLayout(buttons)

    @property
    def coop_category(self) -> str:
        return self.category_combo.currentText()

    @property
    def genre_tag(self) -> str:
        return self.genre_combo.currentData() or self.genre_combo.currentText()

    @property
    def limit(self) -> int:
        return int(self.limit_combo.currentText())

    @property
    def delay_ms(self) -> int:
        return int(self.delay_combo.currentText().split()[0])

    @property
    def page_size(self) -> int:
        return 100

    @property
    def sort_by(self) -> str:
        return "Reviews_DESC"


class DiscoveryDialog(QDialog):
    def __init__(
        self,
        steam: SteamClient,
        country_code: str,
        imported_appids: set[int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.steam = steam
        self.country_code = country_code
        self.imported_appids = imported_appids
        self.results: list[SteamApp] = []
        self.selected_apps: list[SteamApp] = []
        self.start = 0

        self.setWindowTitle("Descobrir jogos coop")
        self.resize(760, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Descubra jogos pela categoria coop da Steam:"))

        controls = QHBoxLayout()
        self.category_combo = QComboBox()
        self.category_combo.addItems(COOP_CATEGORIES.keys())
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Melhores avaliações", "Nome", "Menor preço", "Mais recentes"])
        self.sort_values = {
            "Melhores avaliações": "Reviews_DESC",
            "Nome": "_ASC",
            "Menor preço": "Price_ASC",
            "Mais recentes": "Released_DESC",
        }
        self.count_combo = QComboBox()
        self.count_combo.addItems(["25", "50", "100"])
        load_button = QPushButton("Carregar")
        load_button.clicked.connect(self.load_first_page)
        more_button = QPushButton("Mais resultados")
        more_button.clicked.connect(self.load_next_page)
        controls.addWidget(QLabel("Tipo:"))
        controls.addWidget(self.category_combo, 1)
        self.genre_combo = QComboBox()
        self.genre_choices = tag_choices(list(GENRE_TAGS.keys()), getattr(parent, 'lang', 'en'))
        for label, value in self.genre_choices:
            self.genre_combo.addItem(label, value)
        controls.addWidget(QLabel("Gênero:"))
        controls.addWidget(self.genre_combo, 1)
        controls.addWidget(QLabel("Ordenar:"))
        controls.addWidget(self.sort_combo)
        controls.addWidget(QLabel("Qtd:"))
        controls.addWidget(self.count_combo)
        controls.addWidget(load_button)
        controls.addWidget(more_button)
        layout.addLayout(controls)

        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(["Importar", "AppID", "Nome"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.doubleClicked.connect(self.open_selected_details)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.results_table, 1)

        selection_row = QHBoxLayout()
        select_all_button = QPushButton("Marcar todos")
        select_all_button.clicked.connect(self.check_all)
        unselect_all_button = QPushButton("Desmarcar todos")
        unselect_all_button.clicked.connect(self.uncheck_all)
        selection_row.addStretch()
        selection_row.addWidget(select_all_button)
        selection_row.addWidget(unselect_all_button)
        layout.addLayout(selection_row)

        button_row = QHBoxLayout()
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        import_button = QPushButton("Importar marcados")
        import_button.clicked.connect(self.accept_selected)
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(import_button)
        layout.addLayout(button_row)

        self.load_first_page()

    def load_first_page(self) -> None:
        self.start = 0
        self.results = []
        self.load_next_page()

    def load_next_page(self) -> None:
        try:
            count = int(self.count_combo.currentText())
            genre_tag = self.genre_combo.currentData() or self.genre_combo.currentText()
            if genre_tag == "Any":
                apps = self.steam.discover_popular_genre_games(
                    coop_category=self.category_combo.currentText(),
                    start=self.start,
                    count=count,
                    sort_by=self.sort_values[self.sort_combo.currentText()],
                )
            else:
                apps = self.steam.discover_coop_games(
                    coop_category=self.category_combo.currentText(),
                    start=self.start,
                    count=count,
                    sort_by=self.sort_values[self.sort_combo.currentText()],
                    genre_tag=genre_tag,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Erro", f"Não foi possível descobrir jogos:\n{exc}")
            return
        existing_ids = {app.appid for app in self.results} | self.imported_appids
        self.results.extend([app for app in apps if app.appid not in existing_ids])
        self.start += count
        self.populate_results()

    @property
    def genre_tag(self) -> str:
        return self.genre_combo.currentData() or self.genre_combo.currentText()

    def populate_results(self) -> None:
        self.results_table.setRowCount(len(self.results))
        for row, app in enumerate(self.results):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check_item.setCheckState(Qt.Unchecked)
            self.results_table.setItem(row, 0, check_item)
            appid_item = QTableWidgetItem(str(app.appid))
            appid_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(row, 1, appid_item)
            self.results_table.setItem(row, 2, QTableWidgetItem(app.name))

    def open_selected_details(self) -> None:
        row = self.results_table.currentRow()
        if row < 0 or row >= len(self.results):
            return
        app = self.results[row]
        game = Game(appid=app.appid, name=app.name, store_link=f"https://store.steampowered.com/app/{app.appid}/")
        dialog = GameDetailsDialog(
            game,
            self.steam,
            self.country_code,
            steam_language_for_interface(getattr(self.parent(), "lang", "pt")),
            getattr(self.parent(), "lang", "pt"),
            self,
        )
        dialog.exec()

    def check_all(self) -> None:
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)

    def uncheck_all(self) -> None:
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)

    def accept_selected(self) -> None:
        selected: list[SteamApp] = []
        for row, app in enumerate(self.results):
            item = self.results_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                selected.append(app)
        if not selected:
            QMessageBox.information(self, "Nada marcado", "Marque pelo menos um jogo para importar.")
            return
        self.selected_apps = selected
        self.accept()


class GameSearchDialog(QDialog):
    def __init__(
        self,
        steam: SteamClient,
        country_code: str,
        imported_appids: set[int],
        steam_language: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.steam = steam
        self.country_code = country_code
        self.imported_appids = imported_appids
        self.steam_language = steam_language
        self.selected_apps: list[SteamApp] = []
        self.results: list[SteamApp] = []

        self.setWindowTitle("Buscar jogo na Steam")
        self.resize(720, 460)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(500)
        self.search_timer.timeout.connect(self.update_results)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Digite parte do nome do jogo:"))

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Ex: Portal 2, Stardew, Baldur...")
        self.search_input.textChanged.connect(self.schedule_search)
        self.search_input.returnPressed.connect(self.update_results)
        search_button = QPushButton("Buscar")
        search_button.clicked.connect(self.update_results)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(search_button)
        layout.addLayout(search_row)

        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(["Importar", "AppID", "Nome"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.doubleClicked.connect(self.open_selected_details)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.results_table, 1)

        selection_row = QHBoxLayout()
        select_all_button = QPushButton("Marcar todos")
        select_all_button.clicked.connect(self.check_all)
        unselect_all_button = QPushButton("Desmarcar todos")
        unselect_all_button.clicked.connect(self.uncheck_all)
        selection_row.addStretch()
        selection_row.addWidget(select_all_button)
        selection_row.addWidget(unselect_all_button)
        layout.addLayout(selection_row)

        button_row = QHBoxLayout()
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        add_button = QPushButton("Adicionar marcados")
        add_button.clicked.connect(self.accept_selected)
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(add_button)
        layout.addLayout(button_row)

    def schedule_search(self) -> None:
        term = self.search_input.text().strip()
        if len(term) < 2:
            self.results = []
            self.results_table.setRowCount(0)
            return
        self.search_timer.start()

    def update_results(self) -> None:
        term = self.search_input.text().strip()
        if len(term) < 2:
            return
        try:
            self.results = [
                app for app in self.steam.search_store(term, self.country_code, self.steam_language)
                if app.appid not in self.imported_appids
            ]
        except Exception as exc:
            QMessageBox.critical(self, "Erro", f"Não foi possível buscar na Steam:\n{exc}")
            return
        self.results_table.setRowCount(len(self.results))
        for row, app in enumerate(self.results):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check_item.setCheckState(Qt.Unchecked)
            self.results_table.setItem(row, 0, check_item)
            appid_item = QTableWidgetItem(str(app.appid))
            appid_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(row, 1, appid_item)
            self.results_table.setItem(row, 2, QTableWidgetItem(app.name))

    def open_selected_details(self) -> None:
        row = self.results_table.currentRow()
        if row < 0 or row >= len(self.results):
            return
        app = self.results[row]
        game = Game(appid=app.appid, name=app.name, store_link=f"https://store.steampowered.com/app/{app.appid}/")
        dialog = GameDetailsDialog(
            game,
            self.steam,
            self.country_code,
            self.steam_language,
            getattr(self.parent(), "lang", "pt"),
            self,
        )
        dialog.exec()

    def check_all(self) -> None:
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)

    def uncheck_all(self) -> None:
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)

    def accept_selected(self) -> None:
        selected: list[SteamApp] = []
        for row, app in enumerate(self.results):
            item = self.results_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                selected.append(app)
        if not selected:
            row = self.results_table.currentRow()
            if row >= 0 and row < len(self.results):
                selected.append(self.results[row])
        if not selected:
            QMessageBox.information(self, "Nada selecionado", "Marque ou selecione um jogo da lista.")
            return
        self.selected_apps = selected
        self.accept()


def translate_review_score(language: str, value: str) -> str:
    key = "review_" + value.casefold().replace(" ", "_").replace("-", "_")
    translated = t(language, key)
    return value if translated == key else translated


def yes_no(value: bool) -> str:
    return "Yes" if value else "No"
