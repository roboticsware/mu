"""
MicroPython package manager widget.
"""
import os
import shutil
import tempfile
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QLabel,
    QSplitter,
    QMessageBox
)
from .logic import (
    search_pypi, 
    download_from_pypi, 
    extract_package, 
    get_installable_files,
    fetch_micropython_index,
    install_mip_package,
    get_package_info,
    _ensure_remote_dir
)

class MipSearchThread(QThread):
    log_signal = pyqtSignal(str)
    result_signal = pyqtSignal(object)

    def __init__(self, package_name):
        super().__init__()
        self.package_name = package_name

    def run(self):
        try:
            self.log_signal.emit(f"Searching for '{self.package_name}'...")
            info = get_package_info(self.package_name)
            self.result_signal.emit(info)
        except Exception as e:
            self.log_signal.emit(f"Search error: {str(e)}")
            self.result_signal.emit(None)

class MipInstallThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, package_info, file_manager):
        super().__init__()
        self.package_info = package_info
        self.package_name = package_info.get("name")
        self.source = package_info.get("source")
        self.version = package_info.get("version")
        self.file_manager = file_manager

    def run(self):
        try:
            if self.source == "micropython-lib":
                self.log_signal.emit(f"Installing '{self.package_name}' from micropython-lib (v{self.version})...")
                success, message = install_mip_package(
                    self.package_name, 
                    self.version, 
                    self.file_manager, 
                    self.log_signal.emit
                )
                self.finished_signal.emit(success, message)
                return

            # PyPI installation
            self.log_signal.emit(f"Installing '{self.package_name}' from PyPI (v{self.version})...")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                self.log_signal.emit("Downloading from PyPI...")
                downloaded_file = download_from_pypi(self.package_name, temp_dir)
                if not downloaded_file:
                    self.finished_signal.emit(False, "Failed to download from PyPI.")
                    return
                
                self.log_signal.emit(f"Downloaded: {os.path.basename(downloaded_file)}")
                
                extract_dir = os.path.join(temp_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                self.log_signal.emit("Extracting package...")
                if not extract_package(downloaded_file, extract_dir):
                    self.finished_signal.emit(False, "Failed to extract package.")
                    return
                
                installables = get_installable_files(extract_dir, self.package_name)
                if not installables:
                    self.finished_signal.emit(False, "No installable files found in package.")
                    return
                
                self.log_signal.emit("Transferring to device...")
                if not self.file_manager:
                    self.finished_signal.emit(False, "No device connection available.")
                    return
                
                # Make sure /lib exists
                try:
                    self.file_manager.mkdir("/lib")
                except Exception:
                    pass
                    
                for local_path, remote_dir in installables:
                    _ensure_remote_dir(self.file_manager, remote_dir.strip("/"), self.log_signal.emit)
                    self._upload_to_device(local_path, remote_dir)
                
                self.log_signal.emit(f"Successfully installed {self.package_name} from PyPI.")
                self.finished_signal.emit(True, "Installation complete.")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

    def _upload_to_device(self, local_path, remote_dir):
        """Recursively upload files/folders to the device."""
        basename = os.path.basename(local_path)
        # Ensure remote_path is relative for microfs
        remote_path = remote_dir.strip("/") + "/" + basename
        if os.path.isdir(local_path):
            self.log_signal.emit(f"Creating directory {remote_path}")
            try:
                self.file_manager.mkdir(remote_path)
            except Exception:
                pass
            for item in os.listdir(local_path):
                self._upload_to_device(os.path.join(local_path, item), remote_path)
        else:
            if local_path.endswith(".py") or local_path.endswith(".mpy"):
                self.log_signal.emit(f"Uploading {remote_path}")
                try:
                    # use FileManager's put(local_path, target=remote_path)
                    self.file_manager.put(local_path, remote_path)
                except Exception as e:
                    self.log_signal.emit(f"Error uploading {remote_path}: {e}")


class NoEnterLineEdit(QLineEdit):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.returnPressed.emit()
        else:
            super().keyPressEvent(event)

class MicroPythonPackagesWidget(QWidget):
    """
    Widget to search and install MicroPython packages to the device.
    """

    def __init__(self, mode, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.file_manager = None
        self.is_installing = False
        self.current_package_info = None
        self.setup()

    def setup(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Search area
        search_layout = QHBoxLayout()
        self.search_box = NoEnterLineEdit()
        self.search_box.setPlaceholderText(_("Search PyPI for MicroPython packages (e.g. picozero-rw)"))
        self.search_box.returnPressed.connect(self.on_search_clicked)
        
        self.search_button = QPushButton(_("Search"))
        self.search_button.clicked.connect(self.on_search_clicked)
        
        search_layout.addWidget(self.search_box)
        search_layout.addWidget(self.search_button)
        layout.addLayout(search_layout)

        # Internet requirement notice
        self.notice_label = QLabel(_("Internet connection required for searching and downloading packages."))
        self.notice_label.setStyleSheet("color: #888; font-size: 10px; margin-bottom: 5px;")
        layout.addWidget(self.notice_label)

        from PyQt6.QtWidgets import QProgressBar, QTextBrowser
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Splitter for info and logs
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Detail area
        detail_widget = QWidget()
        detail_layout = QVBoxLayout()
        detail_layout.setContentsMargins(0, 0, 0, 0)
        
        self.details_pane = QTextBrowser()
        self.details_pane.setOpenExternalLinks(True)
        self.details_pane.setHtml(
            f"<h3>{_('Package Details')}</h3>"
            f"<p>{_('Enter a package name above and click Search.')}</p>"
        )
        detail_layout.addWidget(self.details_pane)
        
        # Install button
        self.install_button = QPushButton(_("Install"))
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.on_install_clicked)
        detail_layout.addWidget(self.install_button)
        
        detail_widget.setLayout(detail_layout)
        splitter.addWidget(detail_widget)

        # Log area
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        splitter.addWidget(self.log_area)

        layout.addWidget(splitter)

    def log(self, message):
        self.log_area.appendPlainText(message)

    def on_search_clicked(self):
        query = self.search_box.text().strip()
        if not query:
            return

        self.log(f"--- Searching for {query} ---")
        self.search_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.progress_bar.show()
        
        self.search_thread = MipSearchThread(query)
        self.search_thread.log_signal.connect(self.log)
        self.search_thread.result_signal.connect(self.on_search_finished)
        self.search_thread.start()

    def on_search_finished(self, info):
        self.search_button.setEnabled(True)
        self.progress_bar.hide()
        
        if info:
            self.current_package_info = info
            self.log(f"Found {info['name']} (v{info['version']}) from {info['source']}")
            
            html = f"<h2>{info['name']}</h2>"
            html += f"<b>{_('Source')}:</b> {info['source']}<br>"
            if info.get('version'):
                html += f"<b>{_('Latest stable version')}:</b> {info['version']}<br>"
            if info.get('summary'):
                html += f"<b>{_('Summary')}:</b> {info['summary']}<br>"
            if info.get('author'):
                html += f"<b>{_('Author')}:</b> {info['author']}<br>"
            if info.get('homepage'):
                html += f"<b>{_('Homepage')}:</b> <a href='{info['homepage']}'>{info['homepage']}</a><br>"
            if info.get('pypi_url'):
                html += f"<b>{_('PyPI page')}:</b> <a href='{info['pypi_url']}'>{info['pypi_url']}</a><br>"
                
            self.details_pane.setHtml(html)
            self.install_button.setEnabled(True)
        else:
            self.current_package_info = None
            self.details_pane.setHtml(
                f"<h3>{_('Not Found')}</h3>"
                f"<p>{_('Could not find package.')}</p>"
            )
            self.install_button.setEnabled(False)

    def on_install_clicked(self):
        if not self.current_package_info:
            return
            
        try:
            device = self.mode.editor.current_device
            if not device:
                QMessageBox.warning(self, _("Error"), _("No device connected. Please connect a device first."))
                return
                
            from mu.modes.base import FileManager
            # Stop REPL/Plotter/Files temporarily to use serial safely
            if self.mode.repl:
                self.mode.toggle_repl(None)
            if self.mode.plotter:
                self.mode.toggle_plotter(None)
            if getattr(self.mode, "fs", None):
                self.mode.toggle_files(None)
                
            self.log(f"--- Starting installation of {self.current_package_info['name']} ---")
            self.search_button.setEnabled(False)
            self.install_button.setEnabled(False)
            self.install_button.setText(_("Installing..."))
            
            # Disable main dialog buttons
            dialog = self.window()
            if hasattr(dialog, "set_buttons_enabled"):
                dialog.set_buttons_enabled(False)
                
            self.progress_bar.show()
            self.is_installing = True
            
            # We instantiate a temporary file manager
            self.temp_fm = FileManager(device.port)
            self.temp_fm.on_start() # Open serial connection
            
            self.thread = MipInstallThread(self.current_package_info, self.temp_fm)
            self.thread.log_signal.connect(self.log)
            self.thread.finished_signal.connect(self.on_install_finished)
            self.thread.start()
        except Exception as e:
            self.log(f"Error: {e}")
            self.search_button.setEnabled(True)
            self.install_button.setEnabled(True)
            self.install_button.setText(_("Install"))
            self.progress_bar.hide()
            self.is_installing = False
            
            # Re-enable main dialog buttons
            dialog = self.window()
            if hasattr(dialog, "set_buttons_enabled"):
                dialog.set_buttons_enabled(True)

    def on_install_finished(self, success, message):
        self.log(message)
        self.search_button.setEnabled(True)
        self.install_button.setEnabled(True)
        self.install_button.setText(_("Install"))
        self.progress_bar.hide()
        self.is_installing = False
        
        # Re-enable main dialog buttons
        dialog = self.window()
        if hasattr(dialog, "set_buttons_enabled"):
            dialog.set_buttons_enabled(True)
        
        # Close temporary file manager
        if self.temp_fm:
            self.temp_fm.close()
            self.temp_fm = None
