"""
PyQt6 widget for the ESP Online Firmware Flasher.

This widget provides an online firmware flashing workflow:
  1. Fetch board/version list from Thonny's esptool JSON & curated boards,
     or load custom builds (e.g. TFLite-Micro / Edge Impulse) from a
     GitHub repo, JSON manifest, or direct .bin/.zip URL.
  2. Select a board variant, version, and target chip.
  3. Download the .bin or .zip archive with a live progress bar.
  4. Erase the device flash, then write single or multi-part firmware via esptool.

The widget expects to be embedded as a tab inside AdminDialog when the
active mode is "esp".
"""
import logging
import os

from mu.qt.QtCore import QObject, QThread, pyqtSignal, Qt
from mu.qt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QGroupBox,
    QSizePolicy,
)

from mu.interface.esp_flasher.fetcher import (
    EspFirmwareFetcher,
    EspFirmwareRelease,
    infer_chip_family,
)
from mu.interface.esp_flasher.flasher import EspFlasher

logger = logging.getLogger(__name__)

_CHIP_OPTIONS = [
    ("ESP32-S3", "esp32s3"),
    ("ESP32", "esp32"),
    ("ESP32-S2", "esp32s2"),
    ("ESP32-C3", "esp32c3"),
    ("ESP32-C6", "esp32c6"),
    ("ESP8266", "esp8266"),
]


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _FetchWorker(QObject):
    """Fetches the firmware release list in a background thread."""

    finished = pyqtSignal(list)   # emits List[EspFirmwareRelease]
    error = pyqtSignal(str)

    def __init__(self, custom_url: str = ""):
        super().__init__()
        self._custom_url = custom_url

    def run(self):
        try:
            fetcher = EspFirmwareFetcher()
            if self._custom_url:
                releases = fetcher.get_custom_releases(self._custom_url)
            else:
                releases = fetcher.get_releases()
            self.finished.emit(releases)
        except Exception as exc:
            self.error.emit(str(exc))


class _DownloadFlashWorker(QObject):
    """Downloads a .bin or .zip file then erases + writes the ESP device."""

    progress = pyqtSignal(int, int)   # (downloaded_bytes, total_bytes)
    log = pyqtSignal(str)             # log messages
    finished = pyqtSignal(bool)       # True = success

    def __init__(
        self, url: str, port: str, chip_family: str, flash_offset: str = ""
    ):
        super().__init__()
        self._url = url
        self._port = port
        self._chip_family = chip_family
        self._flash_offset = flash_offset

    def run(self):
        fetcher = EspFirmwareFetcher()
        flasher = EspFlasher()
        tmp_path = None
        try:
            self.log.emit(_("Downloading firmware…"))
            tmp_path = fetcher.download(self._url, self._on_progress)
            self.log.emit(_("Download complete. Erasing flash…"))
            try:
                flasher.erase(self._port, self._chip_family, self.log.emit)
                self.log.emit(_("Erase complete. Writing firmware…"))
                flasher.write(
                    self._port,
                    self._chip_family,
                    tmp_path,
                    self.log.emit,
                    flash_offset=self._flash_offset,
                )
                self.log.emit(
                    _("Flash complete! Device is rebooting with the new firmware.")
                )
                self.finished.emit(True)
            except Exception as flash_exc:
                self.log.emit(_("Flash failed: {}").format(flash_exc))
                self.finished.emit(False)
        except Exception as exc:
            self.log.emit(_("Download error: {}").format(exc))
            self.finished.emit(False)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _on_progress(self, downloaded: int, total: int):
        self.progress.emit(downloaded, total)


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class EspOnlineFlasherWidget(QWidget):
    """
    Online firmware flasher tab shown inside AdminDialog when the active
    mode is "esp".

    Workflow:
        [Fetch Versions] or [Load Custom URL] → populates board/version combos
        [Erase && Flash] → downloads .bin/.zip, erases flash, writes firmware
    """

    def setup(self, mode, device_list):
        self._mode = mode
        self._releases = []     # List[EspFirmwareRelease]
        self._all_releases = [] # all fetched releases (for filtering)

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        # -- Instructions ---------------------------------------------------
        grp_info = QGroupBox(_("How to flash MicroPython to your ESP board"))
        grp_info_layout = QVBoxLayout(grp_info)
        instructions = QLabel(
            _(
                "1. Connect your ESP board via USB.<br>"
                "2. Click <b>Fetch Versions</b> for standard/camera firmware, "
                "or paste a custom GitHub repo, manifest .json, or direct "
                ".bin/.zip URL (e.g. TFLite-Micro / Edge Impulse) and click "
                "<b>Load</b>.<br>"
                "3. Select your <b>Board</b>, <b>Version</b>, and <b>Chip</b>.<br>"
                "4. Click <b>Erase &amp; Flash</b> — single or multi-part "
                "firmware will be written automatically.<br>"
                "<i>Note: hold the BOOT button on your board if the device "
                "does not enter programming mode automatically.</i>"
            )
        )
        instructions.setTextFormat(Qt.TextFormat.RichText)
        instructions.setWordWrap(True)
        grp_info_layout.addWidget(instructions)
        layout.addWidget(grp_info)

        # -- Controls -------------------------------------------------------
        form = QGridLayout()

        # Row 0: custom firmware/manifest URL
        custom_label = QLabel(_("Custom URL:"))
        self.custom_url_edit = QLineEdit()
        self.custom_url_edit.setPlaceholderText(
            _("GitHub repo, manifest .json, or direct .bin/.zip URL")
        )
        self.btn_load_custom = QPushButton(_("Load"))
        self.btn_load_custom.clicked.connect(self._load_custom_source)
        form.addWidget(custom_label, 0, 0)
        form.addWidget(self.custom_url_edit, 0, 1)
        form.addWidget(self.btn_load_custom, 0, 2)

        # Row 1: board selector
        board_label = QLabel(_("Board:"))
        self.board_combo = QComboBox()
        self.board_combo.setMinimumWidth(280)
        self.board_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.board_combo.setEnabled(False)
        self.board_combo.currentIndexChanged.connect(self._on_board_changed)
        self.btn_fetch = QPushButton(_("Fetch Versions"))
        self.btn_fetch.clicked.connect(self._fetch_versions)
        form.addWidget(board_label, 1, 0)
        form.addWidget(self.board_combo, 1, 1)
        form.addWidget(self.btn_fetch, 1, 2)

        # Row 2: version selector
        version_label = QLabel(_("Version:"))
        self.version_combo = QComboBox()
        self.version_combo.setMinimumWidth(280)
        self.version_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.version_combo.setEnabled(False)
        self.version_combo.currentIndexChanged.connect(self._on_version_changed)
        form.addWidget(version_label, 2, 0)
        form.addWidget(self.version_combo, 2, 1)

        # Row 3: target chip family
        chip_label = QLabel(_("Chip:"))
        self.chip_combo = QComboBox()
        for chip_name, chip_val in _CHIP_OPTIONS:
            self.chip_combo.addItem(chip_name, userData=chip_val)
        self.chip_combo.currentIndexChanged.connect(self._on_chip_changed)
        form.addWidget(chip_label, 3, 0)
        form.addWidget(self.chip_combo, 3, 1)

        # Row 4: serial port
        port_label = QLabel(_("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(280)
        self.port_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        form.addWidget(port_label, 4, 0)
        form.addWidget(self.port_combo, 4, 1)

        layout.addLayout(form)

        # -- Progress bar ---------------------------------------------------
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # -- Flash button ---------------------------------------------------
        btn_row = QHBoxLayout()
        self.btn_flash = QPushButton(_("Erase && Flash"))
        self.btn_flash.setEnabled(False)
        self.btn_flash.clicked.connect(self._erase_and_flash)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_flash)
        layout.addLayout(btn_row)

        # -- Log area -------------------------------------------------------
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(160)
        layout.addWidget(self.log_area)

        # Initialize ports after button is created
        self._populate_ports(device_list)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _populate_ports(self, device_list):
        """Populate the port combo from the device list."""
        self.port_combo.clear()
        if device_list:
            for device in device_list:
                label = "{} ({})".format(
                    getattr(device, "name", device.port), device.port
                )
                self.port_combo.addItem(label, userData=device.port)
        self._update_flash_button()

    def _update_flash_button(self):
        can_flash = (
            self.version_combo.count() > 0
            and self.port_combo.count() > 0
        )
        self.btn_flash.setEnabled(can_flash)

    def _set_busy(self, busy: bool):
        self.btn_fetch.setEnabled(not busy)
        self.btn_load_custom.setEnabled(not busy)
        self.custom_url_edit.setEnabled(not busy)
        self.btn_flash.setEnabled(not busy)
        self.board_combo.setEnabled(not busy)
        self.version_combo.setEnabled(not busy)
        self.chip_combo.setEnabled(not busy)
        self.port_combo.setEnabled(not busy)

    def _log(self, msg: str):
        self.log_area.appendPlainText(msg)
        logger.info("[EspOnlineFlasher] %s", msg)

    def _rebuild_board_combo(self, select_label: str = ""):
        """Rebuild board_combo from self._all_releases and optionally select a label."""
        self.board_combo.blockSignals(True)
        self.board_combo.clear()
        seen = []
        for rel in self._all_releases:
            if rel.label not in seen:
                seen.append(rel.label)
                self.board_combo.addItem(rel.label)
        self.board_combo.setEnabled(len(seen) > 0)
        if select_label:
            idx = self.board_combo.findText(select_label)
            if idx >= 0:
                self.board_combo.setCurrentIndex(idx)
        self.board_combo.blockSignals(False)
        self._on_board_changed()
        return len(seen)

    def _merge_custom_releases(self, custom_releases):
        """Prepend custom releases (deduplicated) and select the first custom board."""
        existing = {
            (r.label, r.tag, r.url) for r in self._all_releases
        }
        new_items = [
            r for r in custom_releases
            if (r.label, r.tag, r.url) not in existing
        ]
        self._all_releases = new_items + self._all_releases
        target_label = custom_releases[0].label if custom_releases else ""
        self._rebuild_board_combo(select_label=target_label)

    # -----------------------------------------------------------------------
    # Slots
    # -----------------------------------------------------------------------

    def _fetch_versions(self):
        self._log(_("Fetching firmware list…"))
        self.btn_fetch.setEnabled(False)
        self.btn_load_custom.setEnabled(False)
        self.board_combo.setEnabled(False)
        self.board_combo.clear()
        self.version_combo.setEnabled(False)
        self.version_combo.clear()

        self._fetch_thread = QThread()
        self._fetch_worker = _FetchWorker()
        self._fetch_worker.moveToThread(self._fetch_thread)
        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.finished.connect(self._on_fetch_done)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.finished.connect(self._fetch_thread.quit)
        self._fetch_worker.error.connect(self._fetch_thread.quit)
        self._fetch_thread.start()

    def _on_fetch_done(self, releases):
        self._all_releases = releases
        self.btn_fetch.setEnabled(True)
        self.btn_load_custom.setEnabled(True)
        if not releases:
            self._log(_("No compatible firmware found."))
            return

        board_count = self._rebuild_board_combo()
        self._log(_("Loaded firmware for {} boards.").format(board_count))

    def _on_fetch_error(self, msg):
        self.btn_fetch.setEnabled(True)
        self.btn_load_custom.setEnabled(True)
        self._log(_("Error fetching versions: {}").format(msg))

    def _load_custom_source(self):
        url = self.custom_url_edit.text().strip()
        if not url:
            self._log(_("Please enter a custom firmware or manifest URL."))
            return

        clean_path = url.split("?")[0].lower()
        if clean_path.endswith((".bin", ".zip")):
            family = infer_chip_family(url)
            rel = EspFirmwareRelease(
                label=_("Custom URL"),
                family=family,
                version="custom",
                url=url,
            )
            self._merge_custom_releases([rel])
            self._log(_("Loaded custom firmware URL: {}").format(os.path.basename(clean_path)))
            return

        self._log(_("Loading custom firmware source…"))
        self.btn_load_custom.setEnabled(False)
        self.btn_fetch.setEnabled(False)
        self._custom_thread = QThread()
        self._custom_worker = _FetchWorker(custom_url=url)
        self._custom_worker.moveToThread(self._custom_thread)
        self._custom_thread.started.connect(self._custom_worker.run)
        self._custom_worker.finished.connect(self._on_custom_fetch_done)
        self._custom_worker.error.connect(self._on_custom_fetch_error)
        self._custom_worker.finished.connect(self._custom_thread.quit)
        self._custom_worker.error.connect(self._custom_thread.quit)
        self._custom_thread.start()

    def _on_custom_fetch_done(self, releases):
        self.btn_load_custom.setEnabled(True)
        self.btn_fetch.setEnabled(True)
        if not releases:
            self._log(_("No .bin or .zip firmware found at custom URL."))
            return
        self._merge_custom_releases(releases)
        self._log(_("Loaded {} custom firmware assets.").format(len(releases)))

    def _on_custom_fetch_error(self, msg):
        self.btn_load_custom.setEnabled(True)
        self.btn_fetch.setEnabled(True)
        self._log(_("Error loading custom source: {}").format(msg))

    def _on_board_changed(self):
        """Repopulate version combo for the currently selected board."""
        self.version_combo.clear()
        self.version_combo.setEnabled(False)
        selected_label = self.board_combo.currentText()
        if not selected_label:
            self._update_flash_button()
            return
        for rel in self._all_releases:
            if rel.label == selected_label:
                self.version_combo.addItem(str(rel), userData=rel)
        if self.version_combo.count() > 0:
            self.version_combo.setEnabled(True)
        self._on_version_changed()
        self._update_flash_button()

    def _on_version_changed(self):
        """Sync target chip selector with the selected firmware release."""
        rel = self.version_combo.currentData()
        if rel is None or not getattr(rel, "family", ""):
            return
        idx = self.chip_combo.findData(rel.family)
        if idx >= 0:
            self.chip_combo.blockSignals(True)
            self.chip_combo.setCurrentIndex(idx)
            self.chip_combo.blockSignals(False)

    def _on_chip_changed(self):
        """Sync board/version selectors when the user picks a different chip."""
        selected_chip = self.chip_combo.currentData()
        if not selected_chip or not self._all_releases:
            return
        if self.board_combo.currentText() == _("Custom URL"):
            return

        current_rel = self.version_combo.currentData()
        if current_rel is not None and getattr(current_rel, "family", "") == selected_chip:
            return

        for i in range(self.version_combo.count()):
            rel = self.version_combo.itemData(i)
            if rel is not None and getattr(rel, "family", "") == selected_chip:
                self.version_combo.setCurrentIndex(i)
                return

        for rel in self._all_releases:
            if getattr(rel, "family", "") == selected_chip:
                board_idx = self.board_combo.findText(rel.label)
                if board_idx >= 0:
                    self.board_combo.setCurrentIndex(board_idx)
                    return

    def _erase_and_flash(self):
        rel = self.version_combo.currentData()
        if rel is None:
            return
        port = self.port_combo.currentData()
        if not port:
            self._log(_("No port selected."))
            return

        # Close REPL / Files if open
        if self._mode.repl:
            self._mode.toggle_repl(None)
        if self._mode.plotter:
            self._mode.toggle_plotter(None)
        if self._mode.fs is not None:
            self._mode.toggle_files(None)

        chip_family = self.chip_combo.currentData() or rel.family
        flash_offset = getattr(rel, "flash_offset", "")

        self._set_busy(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self._log(
            _("Starting: {} ({}) on {}").format(
                os.path.basename(rel.url.split("?")[0]), chip_family, port
            )
        )

        self._flash_thread = QThread()
        self._flash_worker = _DownloadFlashWorker(
            rel.url, port, chip_family, flash_offset=flash_offset
        )
        self._flash_worker.moveToThread(self._flash_thread)
        self._flash_thread.started.connect(self._flash_worker.run)
        self._flash_worker.progress.connect(self._on_progress)
        self._flash_worker.log.connect(self._log)
        self._flash_worker.finished.connect(self._on_flash_done)
        self._flash_worker.finished.connect(self._flash_thread.quit)
        self._flash_thread.start()

    def _on_progress(self, downloaded: int, total: int):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(downloaded)
            pct = int(downloaded * 100 / total)
            self.progress_bar.setFormat(
                "{:.0f} KB / {:.0f} KB  ({}%)".format(
                    downloaded / 1024, total / 1024, pct
                )
            )
        else:
            self.progress_bar.setMaximum(0)

    def _on_flash_done(self, success: bool):
        self._set_busy(False)
        self.progress_bar.setVisible(False)
