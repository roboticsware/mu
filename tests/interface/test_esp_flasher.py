# -*- coding: utf-8 -*-
"""
Tests for the ESP online/offline custom firmware flasher support.
"""
import json
import os
import shutil
import sys
import types
import zipfile
from unittest import mock

import pytest

import mu.interface.dialogs
import mu.logic
from mu.interface.esp_flasher.dialog import EspOnlineFlasherWidget
from mu.interface.esp_flasher.fetcher import (
    EspFirmwareFetcher,
    EspFirmwareRelease,
    infer_chip_family,
)
from mu.interface.esp_flasher.flasher import (
    EspFlasher,
    default_flash_offset,
    resolve_firmware_segments,
)
from mu.modes import ESPMode
from mu.qt.QtCore import QProcess


def _make_zip(path, entries):
    """Create a zip archive at path from a dict of {arcname: bytes_or_str}."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


@pytest.fixture
def esp_device():
    return mu.logic.Device(
        0x303A,
        0x1001,
        "/dev/cu.usbmodem101",
        123456,
        "Espressif",
        "ESP32-S3",
        "esp",
        None,
    )


def test_default_flash_offset():
    assert default_flash_offset("esp32") == "0x1000"
    assert default_flash_offset("esp32s2") == "0x1000"
    assert default_flash_offset("esp32s3") == "0x0"
    assert default_flash_offset("esp32c3") == "0x0"
    assert default_flash_offset("esp8266") == "0x0"


def test_resolve_single_bin_auto_and_custom(tmp_path):
    fw = tmp_path / "firmware.bin"
    fw.write_bytes(b"\xe9\x00")

    segs, tmp_dirs = resolve_firmware_segments(str(fw), "esp32s3")
    assert segs == [("0x0", str(fw))]
    assert tmp_dirs == []

    segs, tmp_dirs = resolve_firmware_segments(str(fw), "esp32")
    assert segs == [("0x1000", str(fw))]
    assert tmp_dirs == []

    segs, tmp_dirs = resolve_firmware_segments(
        str(fw), "esp32s3", flash_offset="0x10000"
    )
    assert segs == [("0x10000", str(fw))]
    assert tmp_dirs == []


def test_resolve_single_bin_zip(tmp_path):
    zp = tmp_path / "single.zip"
    _make_zip(zp, {"mpy_cam-s3.bin": b"ABCD" * 10, "README.txt": b"hi"})

    segs, tmp_dirs = resolve_firmware_segments(str(zp), "esp32s3")
    try:
        assert len(segs) == 1
        assert segs[0][0] == "0x0"
        assert os.path.basename(segs[0][1]) == "mpy_cam-s3.bin"
        assert os.path.isfile(segs[0][1])
    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)


def test_resolve_flasher_args_json_zip(tmp_path):
    zp = tmp_path / "ei_build.zip"
    manifest = {
        "flash_files": {
            "0x10000": "build/firmware.bin",
            "0x0": "build/bootloader/bootloader.bin",
            "0x8000": "build/partition_table/partition-table.bin",
        }
    }
    _make_zip(
        zp,
        {
            "flasher_args.json": json.dumps(manifest),
            "build/bootloader/bootloader.bin": b"BOOT",
            "build/partition_table/partition-table.bin": b"PART",
            "build/firmware.bin": b"APP",
        },
    )

    segs, tmp_dirs = resolve_firmware_segments(str(zp), "esp32s3")
    try:
        assert [(addr, os.path.basename(p)) for addr, p in segs] == [
            ("0x0", "bootloader.bin"),
            ("0x8000", "partition-table.bin"),
            ("0x10000", "firmware.bin"),
        ]
    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)


def test_resolve_flash_args_txt_zip(tmp_path):
    zp = tmp_path / "idf_args.zip"
    _make_zip(
        zp,
        {
            "flash_args": (
                "--flash_mode dio --flash_freq 80m\n"
                "0x0 bootloader.bin\n"
                "0x8000 partition-table.bin\n"
                "0x10000 micropython.bin\n"
            ),
            "bootloader.bin": b"B",
            "partition-table.bin": b"P",
            "micropython.bin": b"M",
        },
    )

    segs, tmp_dirs = resolve_firmware_segments(str(zp), "esp32s3")
    try:
        assert [(addr, os.path.basename(p)) for addr, p in segs] == [
            ("0x0", "bootloader.bin"),
            ("0x8000", "partition-table.bin"),
            ("0x10000", "micropython.bin"),
        ]
    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)


@pytest.mark.parametrize(
    "chip,expected_boot_addr",
    [("esp32s3", "0x0"), ("esp32", "0x1000")],
)
def test_resolve_heuristic_multipart_zip(tmp_path, chip, expected_boot_addr):
    zp = tmp_path / "heuristic.zip"
    _make_zip(
        zp,
        {
            "bootloader.bin": b"B" * 16,
            "partition-table.bin": b"P" * 16,
            "micropython.bin": b"A" * 64,
        },
    )

    segs, tmp_dirs = resolve_firmware_segments(str(zp), chip)
    try:
        assert [(addr, os.path.basename(p)) for addr, p in segs] == [
            (expected_boot_addr, "bootloader.bin"),
            ("0x8000", "partition-table.bin"),
            ("0x10000", "micropython.bin"),
        ]
    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)


def test_resolve_zip_slip_protection_and_empty_error(tmp_path):
    zp = tmp_path / "evil.zip"
    _make_zip(
        zp,
        {
            "../outside.bin": b"EVIL",
            "safe.bin": b"SAFE",
        },
    )
    segs, tmp_dirs = resolve_firmware_segments(str(zp), "esp32s3")
    try:
        assert len(segs) == 1
        assert os.path.basename(segs[0][1]) == "safe.bin"
        assert os.path.commonpath(
            [os.path.realpath(tmp_dirs[0]), segs[0][1]]
        ) == os.path.realpath(tmp_dirs[0])
        assert not (tmp_path / "outside.bin").exists()
    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)

    empty_zip = tmp_path / "empty.zip"
    _make_zip(empty_zip, {"readme.md": b"no bin here"})
    with pytest.raises(RuntimeError, match="No .bin file found"):
        resolve_firmware_segments(str(empty_zip), "esp32s3")


def test_infer_chip_family():
    assert infer_chip_family("tflite-esp32-s3-cam.bin") == "esp32s3"
    assert infer_chip_family("micropython_esp32c6.zip") == "esp32c6"
    assert infer_chip_family("board-c3-v1.bin") == "esp32c3"
    assert infer_chip_family("esp32s2-mini.bin") == "esp32s2"
    assert infer_chip_family("esp8266-1m.bin") == "esp8266"
    assert infer_chip_family("generic-esp32.bin") == "esp32"


def test_fetcher_custom_releases_json_list_and_dict():
    fetcher = EspFirmwareFetcher()

    list_resp = mock.MagicMock()
    list_resp.json.return_value = [
        {
            "label": "ESP32-S3 TFLite",
            "family": "esp32s3",
            "version": "1.24.1-tflite",
            "url": "https://example.com/tflite-s3.zip",
            "flash_offset": "0x0",
        }
    ]
    dict_resp = mock.MagicMock()
    dict_resp.json.return_value = {
        "firmwares": [
            {
                "name": "Edge Impulse S3",
                "version": "2.0.0",
                "url": "https://example.com/ei-esp32-s3.bin",
            }
        ]
    }

    with mock.patch("requests.get", return_value=list_resp):
        rels = fetcher.get_custom_releases("https://example.com/manifest.json")
    assert len(rels) == 1
    assert rels[0].label == "ESP32-S3 TFLite"
    assert rels[0].family == "esp32s3"
    assert rels[0].flash_offset == "0x0"

    with mock.patch("requests.get", return_value=dict_resp):
        rels = fetcher.get_custom_releases("https://example.com/manifest2.json")
    assert len(rels) == 1
    assert rels[0].label == "Edge Impulse S3"
    assert rels[0].family == "esp32s3"


def test_fetcher_custom_releases_github_repo():
    fetcher = EspFirmwareFetcher()
    gh_resp = mock.MagicMock()
    gh_resp.json.return_value = [
        {
            "tag_name": "v0.9.0",
            "assets": [
                {
                    "name": "micropython-tflite-esp32s3.zip",
                    "browser_download_url": "https://github.com/org/repo/releases/download/v0.9.0/micropython-tflite-esp32s3.zip",
                },
                {
                    "name": "checksums.txt",
                    "browser_download_url": "https://github.com/org/repo/releases/download/v0.9.0/checksums.txt",
                },
            ],
        }
    ]

    with mock.patch("requests.get", return_value=gh_resp) as mock_get:
        rels = fetcher.get_custom_releases("https://github.com/org/repo")

    called_url = mock_get.call_args[0][0]
    assert called_url == "https://api.github.com/repos/org/repo/releases?per_page=10"
    assert len(rels) == 1
    assert rels[0].family == "esp32s3"
    assert rels[0].tag == "v0.9.0"


def test_esp_flasher_write_multipart_zip(tmp_path):
    zp = tmp_path / "fw.zip"
    _make_zip(
        zp,
        {
            "bootloader.bin": b"B",
            "partition-table.bin": b"P",
            "micropython.bin": b"M",
        },
    )

    recorded_args = []
    fake_esptool = types.SimpleNamespace(main=lambda argv: recorded_args.append(argv))
    logs = []

    with mock.patch.dict(sys.modules, {"esptool": fake_esptool}):
        EspFlasher().write("/dev/ttyACM0", "esp32s3", str(zp), log_cb=logs.append)

    assert len(recorded_args) == 1
    args = recorded_args[0]
    assert args[:7] == [
        "--chip",
        "esp32s3",
        "--port",
        "/dev/ttyACM0",
        "--baud",
        "460800",
        "write_flash",
    ]
    assert args[7] == "-z"
    assert args[8] == "0x0"
    assert os.path.basename(args[9]) == "bootloader.bin"
    assert args[10] == "0x8000"
    assert os.path.basename(args[11]) == "partition-table.bin"
    assert args[12] == "0x10000"
    assert os.path.basename(args[13]) == "micropython.bin"
    # Temp dir must be cleaned up after write() finishes
    assert not os.path.exists(os.path.dirname(args[9]))


def test_offline_widget_multipart_zip_and_custom_offset(tmp_path, esp_device):
    zp = tmp_path / "tflite_s3.zip"
    _make_zip(
        zp,
        {
            "bootloader.bin": b"B",
            "partition-table.bin": b"P",
            "micropython.bin": b"M",
        },
    )

    editor = mock.MagicMock()
    view = mock.MagicMock()
    mm = ESPMode(editor, view)
    modes = mock.MagicMock()
    device_list = mu.logic.DeviceList(modes)
    device_list.add_device(esp_device)

    espff = mu.interface.dialogs.ESPFirmwareFlasherWidget()
    espff.setup(mm, device_list)
    espff.run_esptool = mock.MagicMock()

    s3_idx = espff.device_type.findData("esp32s3")
    assert s3_idx >= 0
    espff.device_type.setCurrentIndex(s3_idx)
    espff.txtFolder.setText(str(zp))
    espff.update_firmware()

    assert len(espff.commands) == 2
    write_cmd = espff.commands[1]
    assert "0x0 " in write_cmd
    assert "0x8000 " in write_cmd
    assert "0x10000 " in write_cmd
    assert len(espff._temp_dirs) == 1
    temp_dir = espff._temp_dirs[0]
    assert os.path.isdir(temp_dir)

    # Finishing the last command cleans up the extracted temp directory
    espff.commands = []
    espff.esptool_finished(0, QProcess.NormalExit)
    assert not os.path.exists(temp_dir)

    # Test single .bin with custom offset (e.g. 0x10000 app-only)
    app_bin = tmp_path / "app.bin"
    app_bin.write_bytes(b"APP")
    espff.txtFolder.setText(str(app_bin))
    espff.offset_combo.setCurrentText("0x10000")
    espff.update_firmware()
    assert 'write_flash -z 0x10000 "{}"'.format(app_bin) in espff.commands[1]


def test_online_widget_custom_direct_url(esp_device):
    editor = mock.MagicMock()
    view = mock.MagicMock()
    mm = ESPMode(editor, view)
    modes = mock.MagicMock()
    device_list = mu.logic.DeviceList(modes)
    device_list.add_device(esp_device)

    widget = EspOnlineFlasherWidget()
    widget.setup(mm, device_list)
    widget.custom_url_edit.setText(
        "https://example.com/custom-tflite-esp32s3.zip"
    )
    widget._load_custom_source()

    assert widget.board_combo.count() == 1
    assert widget.version_combo.count() == 1
    assert widget.chip_combo.currentData() == "esp32s3"
    assert widget.btn_flash.isEnabled()


def test_online_widget_chip_syncs_board_and_version(esp_device):
    editor = mock.MagicMock()
    view = mock.MagicMock()
    mm = ESPMode(editor, view)
    modes = mock.MagicMock()
    device_list = mu.logic.DeviceList(modes)
    device_list.add_device(esp_device)

    widget = EspOnlineFlasherWidget()
    widget.setup(mm, device_list)

    releases = [
        EspFirmwareRelease(
            "ESP32 / WROOM (Generic)",
            "esp32",
            "1.29.0",
            "https://example.com/esp32.bin",
        ),
        EspFirmwareRelease(
            "ESP8266 (Generic)",
            "esp8266",
            "1.29.0",
            "https://example.com/esp8266.bin",
        ),
    ]
    widget._on_fetch_done(releases)

    assert widget.board_combo.currentText() == "ESP32 / WROOM (Generic)"
    assert widget.chip_combo.currentData() == "esp32"

    esp8266_idx = widget.chip_combo.findData("esp8266")
    widget.chip_combo.setCurrentIndex(esp8266_idx)

    assert widget.board_combo.currentText() == "ESP8266 (Generic)"
    assert widget.version_combo.currentData().family == "esp8266"

    # When Custom URL is selected, changing Chip should keep Custom URL active
    widget.custom_url_edit.setText("https://example.com/my-custom.bin")
    widget._load_custom_source()
    assert widget.board_combo.currentText() == _("Custom URL")
    s2_idx = widget.chip_combo.findData("esp32s2")
    widget.chip_combo.setCurrentIndex(s2_idx)
    assert widget.board_combo.currentText() == _("Custom URL")
