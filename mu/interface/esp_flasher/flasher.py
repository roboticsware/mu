"""
ESP flasher using esptool Python API.

Wraps esptool's public Python interface to:
  1. Erase the ESP flash
  2. Write a .bin firmware file

All operations run synchronously (call from a QThread).
"""
import logging
import sys

logger = logging.getLogger(__name__)

# Flash address by chip family
# esp8266 writes at 0x0; all esp32 variants write at 0x0 for MicroPython .bin
WRITE_FLASH_ADDRESS = "0x0"

# esp8266 needs --flash_size detect; esp32 variants handle it automatically
_ESP8266_FAMILY = "esp8266"


def _make_esptool_args(port: str, chip: str, baud: int = 460800):
    """Return base args list for esptool."""
    return [
        "--chip", chip,
        "--port", port,
        "--baud", str(baud),
    ]


class EspFlasher:
    """
    Wraps esptool to erase and write MicroPython .bin firmware onto an ESP board.

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

    def write(self, port: str, chip_family: str, bin_path: str, log_cb=None) -> None:
        """
        Write a .bin firmware file to the connected ESP device.

        :param port: Serial port string.
        :param chip_family: Chip family string, e.g. "esp32", "esp8266".
        :param bin_path: Path to the downloaded .bin firmware file.
        :param log_cb: Optional callable(str) for progress messages.
        :raises: Exception on failure.
        """
        # Determine flash address based on chip family
        if chip_family in ("esp32", "esp32s2"):
            flash_address = "0x1000"
        else:
            # esp8266, esp32s3, esp32c3, etc. write at 0x0
            flash_address = "0x0"

        if chip_family == _ESP8266_FAMILY:
            flash_args = ["--flash_size", "detect", flash_address, bin_path]
        else:
            flash_args = [flash_address, bin_path]

        self._run(
            args=_make_esptool_args(port, chip_family) + ["write_flash"] + flash_args,
            log_cb=log_cb,
            description="write_flash",
        )

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
