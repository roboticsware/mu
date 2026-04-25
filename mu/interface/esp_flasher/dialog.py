"""
PyQt6 widget for the ESP Online Firmware Flasher.

This widget replaces the manual .bin-file workflow with an online one:
  1. Fetch board/version list from Thonny's esptool JSON.
  2. Select a board variant and version from drop-downs.
  3. Download the .bin file with a live progress bar.
  4. Erase the device flash, then write the new firmware via esptool.

The widget expects to be embedded as a tab inside AdminDialog when the
active mode is "esp".
"""
import logging
import os

from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QGroupBox,
    QSizePolicy,
)

from mu.interface.esp_flasher.fetcher import EspFirmwareFetcher
from mu.interface.esp_flasher.flasher import EspFlasher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _FetchWorker(QObject):
    """Fetches the firmware release list in a background thread."""

    finished = pyqtSignal(list)   # emits List[EspFirmwareRelease]
    error = pyqtSignal(str)

    def run(self):
        try:
            releases = EspFirmwareFetcher().get_releases()
            self.finished.emit(releases)
        except Exception as exc:
            self.error.emit(str(exc))


class _DownloadFlashWorker(QObject):
    """Downloads a .bin file then erases + writes the ESP device."""

    progress = pyqtSignal(int, int)   # (downloaded_bytes, total_bytes)
    log = pyqtSignal(str)             # log messages
    finished = pyqtSignal(bool)       # True = success

    def __init__(self, url: str, port: str, chip_family: str):
        super().__init__()
        self._url = url
        self._port = port
        self._chip_family = chip_family

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
                flasher.write(self._port, self._chip_family, tmp_path, self.log.emit)
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
        [Fetch Versions] → populates board/version combos
        [Erase && Flash] → downloads .bin, erases flash, writes firmware
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
                "2. Click <b>Fetch Versions</b> to load available firmware.<br>"
                "3. Select your <b>Board</b> and <b>Version</b>.<br>"
                "4. Click <b>Erase &amp; Flash</b> — the device will be "
                "erased and the new firmware written automatically.<br>"
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

        # Row 0: board selector
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
        form.addWidget(board_label, 0, 0)
        form.addWidget(self.board_combo, 0, 1)
        form.addWidget(self.btn_fetch, 0, 2)

        # Row 1: version selector
        version_label = QLabel(_("Version:"))
        self.version_combo = QComboBox()
        self.version_combo.setMinimumWidth(280)
        self.version_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.version_combo.setEnabled(False)
        form.addWidget(version_label, 1, 0)
        form.addWidget(self.version_combo, 1, 1)

        # Row 2: serial port
        port_label = QLabel(_("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(280)
        self.port_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._populate_ports(device_list)
        form.addWidget(port_label, 2, 0)
        form.addWidget(self.port_combo, 2, 1)

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
        self.btn_flash.setEnabled(not busy)
        self.board_combo.setEnabled(not busy)
        self.version_combo.setEnabled(not busy)
        self.port_combo.setEnabled(not busy)

    def _log(self, msg: str):
        self.log_area.appendPlainText(msg)
        logger.info("[EspOnlineFlasher] %s", msg)

    # -----------------------------------------------------------------------
    # Slots
    # -----------------------------------------------------------------------

    def _fetch_versions(self):
        self._log(_("Fetching firmware list…"))
        self.btn_fetch.setEnabled(False)
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
        if not releases:
            self._log(_("No compatible firmware found."))
            return

        # Populate board combo with unique board labels
        seen = []
        for rel in releases:
            if rel.label not in seen:
                seen.append(rel.label)
                self.board_combo.addItem(rel.label)
        self.board_combo.setEnabled(True)
        self._log(_("Loaded firmware for {} boards.").format(len(seen)))
        self._on_board_changed()

    def _on_fetch_error(self, msg):
        self.btn_fetch.setEnabled(True)
        self._log(_("Error fetching versions: {}").format(msg))

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
        self._update_flash_button()

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

        self._set_busy(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self._log(
            _("Starting: {} on {}").format(os.path.basename(rel.url), port)
        )

        self._flash_thread = QThread()
        self._flash_worker = _DownloadFlashWorker(rel.url, port, rel.family)
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
