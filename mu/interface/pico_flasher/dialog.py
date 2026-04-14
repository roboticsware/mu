"""
PyQt6 widget for the Pico Firmware Flasher.

This widget is inserted as a tab in AdminDialog when the active mode is
"pico".  It lets the user:
  1. Fetch the latest MicroPython releases from GitHub.
  2. Select a version / board variant from a drop-down.
  3. Download the .uf2 file with a live progress bar.
  4. Flash the firmware by copying the file to the Pico BOOTSEL drive.
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

from mu.interface.pico_flasher.fetcher import FirmwareFetcher
from mu.interface.pico_flasher.flasher import PicoDriveDetector, PicoFlasher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _FetchWorker(QObject):
    """Fetches the release list in a background thread."""

    finished = pyqtSignal(list)   # emits List[FirmwareRelease]
    error = pyqtSignal(str)

    def run(self):
        try:
            releases = FirmwareFetcher().get_releases()
            self.finished.emit(releases)
        except Exception as exc:
            self.error.emit(str(exc))


class _DownloadFlashWorker(QObject):
    """Downloads a .uf2 file and copies it to the Pico drive."""

    progress = pyqtSignal(int, int)   # (downloaded_bytes, total_bytes)
    log = pyqtSignal(str)             # log messages
    finished = pyqtSignal(bool)       # True = success

    def __init__(self, url: str, drive_path):
        super().__init__()
        self._url = url
        self._drive_path = drive_path

    def run(self):
        fetcher = FirmwareFetcher()
        flasher = PicoFlasher()
        tmp_path = None
        try:
            self.log.emit(_("Downloading firmware…"))
            tmp_path = fetcher.download(self._url, self._on_progress)
            self.log.emit(_("Download complete. Flashing…"))
            try:
                flasher.flash(tmp_path, self._drive_path)
                self.log.emit(
                    _("Flash complete! Pico is rebooting with the new firmware.")
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

class PicoFirmwareFlasherWidget(QWidget):
    """
    Tab widget shown inside AdminDialog when the active mode is "pico".

    Workflow:
        [Fetch Versions] → populates version combo
        [Refresh Drive]  → checks for RPI-RP2 / RP2350 mount
        [Download & Flash] → downloads .uf2 and copies to drive
    """

    def setup(self, mode):
        self._mode = mode
        self._releases = []        # List[FirmwareRelease]
        self._drive_path = None    # Path to the BOOTSEL drive, or None

        layout = QVBoxLayout()
        self.setLayout(layout)

        # -- Instructions ---------------------------------------------------
        grp_info = QGroupBox(_("How to flash MicroPython to your Pico"))
        grp_info_layout = QVBoxLayout()
        grp_info.setLayout(grp_info_layout)
        instructions = QLabel(
            _(
                "1. Hold the <b>BOOTSEL</b> button on your Pico and plug it "
                "into USB — it will appear as a drive called "
                "<b>RPI-RP2</b> (or RP2350 for Pico 2).<br>"
                "2. Click <b>Refresh Drive</b> until the drive is detected.<br>"
                "3. Click <b>Fetch Versions</b> to load available firmware.<br>"
                "4. Select a version and click <b>Download &amp; Flash</b>."
            )
        )
        instructions.setTextFormat(Qt.TextFormat.RichText)
        instructions.setWordWrap(True)
        grp_info_layout.addWidget(instructions)
        layout.addWidget(grp_info)

        # -- Controls -------------------------------------------------------
        form = QGridLayout()

        # Row 0: version selector
        version_label = QLabel(_("Firmware version:"))
        self.version_combo = QComboBox()
        self.version_combo.setMinimumWidth(300)
        self.version_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.version_combo.setEnabled(False)
        self.btn_fetch = QPushButton(_("Fetch Versions"))
        self.btn_fetch.clicked.connect(self._fetch_versions)
        form.addWidget(version_label, 0, 0)
        form.addWidget(self.version_combo, 0, 1)
        form.addWidget(self.btn_fetch, 0, 2)

        # Row 1: drive status
        drive_label = QLabel(_("BOOTSEL drive:"))
        self.drive_status = QLabel(_("Not detected"))
        self.drive_status.setStyleSheet("color: #e53935; font-weight: bold;")
        self.btn_refresh_drive = QPushButton(_("Refresh Drive"))
        self.btn_refresh_drive.clicked.connect(self._refresh_drive)
        form.addWidget(drive_label, 1, 0)
        form.addWidget(self.drive_status, 1, 1)
        form.addWidget(self.btn_refresh_drive, 1, 2)

        layout.addLayout(form)

        # -- Progress bar ---------------------------------------------------
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # -- Flash button ---------------------------------------------------
        btn_row = QHBoxLayout()
        self.btn_flash = QPushButton(_("Download && Flash"))
        self.btn_flash.setEnabled(False)
        self.btn_flash.clicked.connect(self._download_and_flash)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_flash)
        layout.addLayout(btn_row)

        # -- Log area -------------------------------------------------------
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(160)
        layout.addWidget(self.log_area)

        # Init drive state
        self._refresh_drive()

    # -----------------------------------------------------------------------
    # Slots
    # -----------------------------------------------------------------------

    def _fetch_versions(self):
        self._log(_("Fetching firmware list from Thonny…"))
        self.btn_fetch.setEnabled(False)
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
        self._releases = releases
        self.btn_fetch.setEnabled(True)
        if not releases:
            self._log(_("No compatible firmware found."))
            return
        for rel in releases:
            self.version_combo.addItem(str(rel), userData=rel)
        self.version_combo.setEnabled(True)
        self._log(
            _("Loaded {} firmware versions.").format(len(releases))
        )
        self._update_flash_button()

    def _on_fetch_error(self, msg):
        self.btn_fetch.setEnabled(True)
        self._log(_("Error fetching versions: {}").format(msg))

    def _refresh_drive(self):
        drive = PicoDriveDetector().find_drive()
        self._drive_path = drive
        if drive:
            self.drive_status.setText(str(drive))
            self.drive_status.setStyleSheet(
                "color: #43a047; font-weight: bold;"
            )
            self._log(_("BOOTSEL drive detected: {}").format(drive))
        else:
            self.drive_status.setText(_("Not detected"))
            self.drive_status.setStyleSheet(
                "color: #e53935; font-weight: bold;"
            )
        self._update_flash_button()

    def _download_and_flash(self):
        rel = self.version_combo.currentData()
        if rel is None or self._drive_path is None:
            return

        self._set_busy(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        size_str = "({:.1f} KB)".format(rel.size / 1024) if rel.size > 0 else ""
        self._log(
            _("Starting download: {} {}").format(
                os.path.basename(rel.url), size_str
            ).strip()
        )

        self._flash_thread = QThread()
        self._flash_worker = _DownloadFlashWorker(rel.url, self._drive_path)
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
            # Unknown total — show indeterminate
            self.progress_bar.setMaximum(0)

    def _on_flash_done(self, success: bool):
        self._set_busy(False)
        self.progress_bar.setVisible(False)
        # After flash the drive disappears — refresh status
        self._refresh_drive()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _update_flash_button(self):
        can_flash = (
            self.version_combo.count() > 0
            and self._drive_path is not None
        )
        self.btn_flash.setEnabled(can_flash)

    def _set_busy(self, busy: bool):
        self.btn_fetch.setEnabled(not busy)
        self.btn_refresh_drive.setEnabled(not busy)
        self.btn_flash.setEnabled(not busy)
        self.version_combo.setEnabled(not busy)

    def _log(self, msg: str):
        self.log_area.appendPlainText(msg)
        logger.info("[PicoFlasher] %s", msg)
