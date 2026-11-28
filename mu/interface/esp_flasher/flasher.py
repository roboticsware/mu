"""
ESP flasher using esptool Python API.

Wraps esptool's public Python interface to:
  1. Erase the ESP flash
  2. Resolve single .bin or multi-part .zip firmware images
  3. Write firmware segments to the ESP device

All operations run synchronously (call from a QThread).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import tempfile
import zipfile

logger = logging.getLogger(__name__)

# esp8266 needs --flash_size detect; esp32 variants handle it automatically
_ESP8266_FAMILY = "esp8266"
_HEX_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]+$")


def default_flash_offset(chip_family: str) -> str:
    """Return the default flash offset for a given chip family."""
    if chip_family in ("esp32", "esp32s2"):
        return "0x1000"
    return "0x0"


def _safe_extract_zip(zip_path: str, dest_dir: str) -> tuple[dict[str, str], list[str]]:
    """
    Safely extract a firmware zip archive into dest_dir (with Zip Slip protection).

    Returns (rel_to_abs_map, bin_abs_paths).
    """
    real_root = os.path.realpath(dest_dir)
    rel_to_abs: dict[str, str] = {}
    bin_files: list[str] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel_norm = info.filename.replace("\\", "/").lstrip("/")
            if not rel_norm:
                continue
            target_path = os.path.realpath(os.path.join(real_root, rel_norm))
            if os.path.commonpath([real_root, target_path]) != real_root:
                logger.warning("Skipping unsafe zip entry: %s", info.filename)
                continue
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with zf.open(info) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            rel_to_abs[rel_norm] = target_path
            if rel_norm.lower().endswith(".bin"):
                bin_files.append(target_path)

    return rel_to_abs, bin_files


def _match_extracted_file(
    rel_ref: str, rel_to_abs: dict[str, str]
) -> str | None:
    """Match a relative path or basename from metadata against extracted files."""
    cleaned = rel_ref.strip().strip('"').strip("'").replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    cleaned = cleaned.lstrip("/")
    if not cleaned:
        return None
    if cleaned in rel_to_abs:
        return rel_to_abs[cleaned]
    target_base = os.path.basename(cleaned).lower()
    for rel_path, abs_path in rel_to_abs.items():
        if os.path.basename(rel_path).lower() == target_base:
            return abs_path
    return None


def _find_metadata_file(rel_to_abs: dict[str, str], filename: str) -> str | None:
    """Find a metadata file by exact basename, preferring shallowest path."""
    matches = [
        (rel_path.count("/"), abs_path)
        for rel_path, abs_path in rel_to_abs.items()
        if os.path.basename(rel_path).lower() == filename.lower()
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[0][1]


def _segments_from_flasher_args_json(
    json_path: str, rel_to_abs: dict[str, str]
) -> list[tuple[str, str]]:
    """Parse ESP-IDF / Edge Impulse flasher_args.json flash_files mapping."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("Failed to parse flasher_args.json: %s", exc)
        return []

    flash_files = data.get("flash_files")
    if not isinstance(flash_files, dict):
        return []

    segments: list[tuple[str, str]] = []
    for addr, rel_path in flash_files.items():
        addr_str = str(addr).strip()
        if not _HEX_ADDR_RE.match(addr_str) or not isinstance(rel_path, str):
            continue
        matched = _match_extracted_file(rel_path, rel_to_abs)
        if matched and matched.lower().endswith(".bin"):
            segments.append((addr_str, matched))
    return segments


def _segments_from_flash_args(
    args_path: str, rel_to_abs: dict[str, str]
) -> list[tuple[str, str]]:
    """Parse ESP-IDF flash_args text file for (0xADDR, file.bin) pairs."""
    try:
        with open(args_path, "r", encoding="utf-8") as f:
            tokens = f.read().split()
    except Exception as exc:
        logger.warning("Failed to read flash_args: %s", exc)
        return []

    segments: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(tokens):
        tok = tokens[i].strip()
        if _HEX_ADDR_RE.match(tok):
            matched = _match_extracted_file(tokens[i + 1], rel_to_abs)
            if matched and matched.lower().endswith(".bin"):
                segments.append((tok, matched))
                i += 2
                continue
        i += 1
    return segments


def _segments_heuristic(
    bin_files: list[str], chip_family: str
) -> list[tuple[str, str]]:
    """Heuristically map multi-part ESP-IDF .bin files when metadata is absent."""
    basenames = {p: os.path.basename(p).lower() for p in bin_files}
    has_multipart = any(
        "bootloader" in name or "partition" in name or "ota_data" in name
        for name in basenames.values()
    )
    if len(bin_files) <= 1 or not has_multipart:
        return []

    segments: list[tuple[str, str]] = []
    used: set[str] = set()

    for p, name in basenames.items():
        if "bootloader" in name:
            segments.append((default_flash_offset(chip_family), p))
            used.add(p)
            break

    for p, name in basenames.items():
        if p not in used and "partition" in name:
            segments.append(("0x8000", p))
            used.add(p)
            break

    for p, name in basenames.items():
        if p not in used and "ota_data" in name:
            segments.append(("0xd000", p))
            used.add(p)
            break

    remaining = [p for p in bin_files if p not in used]
    if remaining:
        def _app_score(path: str) -> tuple[int, int]:
            b = basenames[path]
            preferred = 1 if any(k in b for k in ("micropython", "firmware", "app")) else 0
            return (preferred, os.path.getsize(path))

        app_bin = max(remaining, key=_app_score)
        segments.append(("0x10000", app_bin))

    return segments


def resolve_firmware_segments(
    firmware_path: str, chip_family: str, flash_offset: str = ""
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Resolve a .bin or .zip firmware path into flash segments [(hex_addr, bin_path), ...].

    Returns (segments, temp_dirs) where temp_dirs should be removed by the caller
    using shutil.rmtree(..., ignore_errors=True) after flashing completes.
    """
    is_zip = firmware_path.lower().endswith(".zip") or (
        os.path.isfile(firmware_path) and zipfile.is_zipfile(firmware_path)
    )
    explicit_offset = flash_offset.strip()

    if not is_zip:
        addr = explicit_offset or default_flash_offset(chip_family)
        return ([(addr, firmware_path)], [])

    tmp_dir = tempfile.mkdtemp(prefix="mu_esp_zip_")
    try:
        rel_to_abs, bin_files = _safe_extract_zip(firmware_path, tmp_dir)
        if not bin_files:
            raise RuntimeError("No .bin file found in firmware zip archive.")

        segments: list[tuple[str, str]] = []

        json_path = _find_metadata_file(rel_to_abs, "flasher_args.json")
        if json_path:
            segments = _segments_from_flasher_args_json(json_path, rel_to_abs)

        if not segments:
            args_path = _find_metadata_file(rel_to_abs, "flash_args")
            if args_path:
                segments = _segments_from_flash_args(args_path, rel_to_abs)

        if not segments:
            segments = _segments_heuristic(bin_files, chip_family)

        if not segments:
            largest_bin = max(bin_files, key=os.path.getsize)
            addr = explicit_offset or default_flash_offset(chip_family)
            segments = [(addr, largest_bin)]

        segments.sort(key=lambda item: int(item[0], 16))
        return (segments, [tmp_dir])
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _make_esptool_args(port: str, chip: str, baud: int = 460800):
    """Return base args list for esptool."""
    return [
        "--chip", chip,
        "--port", port,
        "--baud", str(baud),
    ]


class EspFlasher:
    """
    Wraps esptool to erase and write MicroPython .bin/.zip firmware onto an ESP board.

    Usage (from a background thread):
        flasher = EspFlasher()
        flasher.erase(port, chip_family, log_cb)
        flasher.write(port, chip_family, bin_path, log_cb)
    """

    def erase(self, port: str, chip_family: str, log_cb=None) -> None:
        """
        Erase the entire flash of the connected ESP device.

        :param port: Serial port string, e.g. "COM3" or "/dev/ttyUSB0".
        :param chip_family: Chip family string matching esptool --chip values,
                            e.g. "esp32", "esp8266", "esp32s3".
        :param log_cb: Optional callable(str) for progress messages.
        :raises: Exception on failure.
        """
        self._run(
            args=_make_esptool_args(port, chip_family) + ["erase_flash"],
            log_cb=log_cb,
            description="erase_flash",
        )

    def write(
        self,
        port: str,
        chip_family: str,
        bin_path: str,
        log_cb=None,
        flash_offset: str = "",
    ) -> None:
        """
        Write a .bin or .zip firmware file to the connected ESP device.

        :param port: Serial port string.
        :param chip_family: Chip family string, e.g. "esp32", "esp8266", "esp32s3".
        :param bin_path: Path to the downloaded .bin or .zip firmware file.
        :param log_cb: Optional callable(str) for progress messages.
        :param flash_offset: Optional hex offset override for single-.bin flashing.
        :raises: Exception on failure.
        """
        segments, temp_dirs = resolve_firmware_segments(
            bin_path, chip_family, flash_offset
        )
        try:
            if log_cb:
                summary = ", ".join(
                    "{} -> {}".format(addr, os.path.basename(path))
                    for addr, path in segments
                )
                log_cb("Flash segments: {}".format(summary))

            flat_segments: list[str] = []
            for addr, path in segments:
                flat_segments.extend([addr, path])

            if chip_family == _ESP8266_FAMILY:
                flash_args = ["--flash_size", "detect"] + flat_segments
            else:
                flash_args = ["-z"] + flat_segments

            self._run(
                args=_make_esptool_args(port, chip_family)
                + ["write_flash"]
                + flash_args,
                log_cb=log_cb,
                description="write_flash",
            )
        finally:
            for d in temp_dirs:
                shutil.rmtree(d, ignore_errors=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(self, args: list, log_cb=None, description: str = ""):
        """
        Invoke esptool via its Python API (_main / esptool.main).

        esptool >= 4.x exposes `esptool.main(argv)`.
        We capture stdout/stderr by monkey-patching sys.stdout/stderr
        so progress messages flow to the log callback.
        """
        import esptool
        import io

        if log_cb:
            log_cb("esptool: {}".format(" ".join(args)))

        # Redirect stdout/stderr to capture esptool output
        old_stdout, old_stderr = sys.stdout, sys.stderr
        captured = io.StringIO()
        sys.stdout = sys.stderr = captured

        try:
            esptool.main(args)
        except SystemExit as exc:
            output = captured.getvalue()
            sys.stdout, sys.stderr = old_stdout, old_stderr
            if log_cb and output:
                for line in output.splitlines():
                    log_cb(line)
            if exc.code not in (None, 0):
                raise RuntimeError(
                    "esptool {} failed (exit {}): {}".format(
                        description, exc.code, output.strip()
                    )
                )
        except Exception:
            output = captured.getvalue()
            sys.stdout, sys.stderr = old_stdout, old_stderr
            if log_cb and output:
                for line in output.splitlines():
                    log_cb(line)
            raise
        else:
            output = captured.getvalue()
            sys.stdout, sys.stderr = old_stdout, old_stderr
            if log_cb and output:
                for line in output.splitlines():
                    log_cb(line)
