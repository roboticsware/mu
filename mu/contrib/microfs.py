# -*- coding: utf-8 -*-
"""
This module contains functions for running remote commands on the BBC micro:bit
relating to file system based operations.

You may:

* ls - list files on the device. Based on the equivalent Unix command.
* rm - remove a named file on the device. Based on the Unix command.
* put - copy a named local file onto the device a la equivalent FTP command.
* get - copy a named file from the device to the local file system a la FTP.

Speed optimizations (Thonny-style):
* Raw Paste mode (MicroPython >= 1.14) for flow-controlled, single-shot upload
* Larger chunk sizes (256 bytes) with minimal delays
* Single raw-mode session per put() operation
"""
from __future__ import print_function
import ast
import argparse
import sys
import os
import time
import os.path
from serial.tools.list_ports import comports as list_serial_ports
from serial import Serial


PY2 = sys.version_info < (3,)


__all__ = ["ls", "rm", "put", "get", "get_serial"]


#: The help text to be shown when requested.
_HELP_TEXT = """
Interact with the basic filesystem on a connected BBC micro:bit device.
You may use the following commands:

'ls' - list files on the device (based on the equivalent Unix command);
'rm' - remove a named file on the device (based on the Unix command);
'put' - copy a named local file onto the device just like the FTP command; and,
'get' - copy a named file from the device to the local file system a la FTP.

For example, 'ufs ls' will list the files on a connected BBC micro:bit.
"""


COMMAND_LINE_FLAG = False  # Indicates running from the command line.
SERIAL_BAUD_RATE = 115200


def find_microbit():
    """
    Returns a tuple representation of the port and serial number for a
    connected micro:bit device. If no device is connected the tuple will be
    (None, None).
    """
    ports = list_serial_ports()
    for port in ports:
        if "VID:PID=0D28:0204" in port[2].upper():
            return (port[0], port.serial_number)
    return (None, None)


def raw_on(serial):
    """
    Puts the device into raw mode.
    """

    def flush_to_msg(serial, msg):
        """Read the rx serial data until we reach an expected message."""
        data = serial.read_until(msg)
        if not data.endswith(msg):
            if COMMAND_LINE_FLAG:
                print(data)
            import logging
            logging.getLogger(__name__).error("Failed to enter raw REPL. Expected %r, got %r", msg, data)
            raise IOError("Could not enter raw REPL.")

    def flush(serial):
        """Flush all rx input without relying on serial.flushInput()."""
        n = serial.inWaiting()
        while n > 0:
            serial.read(n)
            n = serial.inWaiting()

    raw_repl_msg = b"raw REPL; CTRL-B to exit\r\n>"
    
    # Allow board to settle before interrupting
    time.sleep(0.5)

    # Send CTRL-B to end raw mode if required.
    serial.write(b"\x02")
    
    # Send CTRL-C 10 times with 0.1s pauses to break out of any running loop.
    # 0.01s is often too fast for MicroPython to register the interrupt.
    for i in range(10):
        serial.write(b"\r\x03")
        time.sleep(0.1)
    
    flush(serial)
    # Go into raw mode with CTRL-A.
    serial.write(b"\r\x01")
    flush_to_msg(serial, raw_repl_msg)
    # Soft Reset with CTRL-D
    serial.write(b"\x04")
    flush_to_msg(serial, b"soft reboot\r\n")
    # Some MicroPython versions/ports/forks provide a different message after
    # a Soft Reset, check if we are in raw REPL, if not send a CTRL-A again
    data = serial.read_until(raw_repl_msg)
    if not data.endswith(raw_repl_msg):
        serial.write(b"\r\x01")
        flush_to_msg(serial, raw_repl_msg)
    flush(serial)


def raw_off(serial):
    """
    Takes the device out of raw mode.
    """
    serial.write(b"\x02")  # Send CTRL-B to get out of raw mode.


def get_serial():
    """
    Detect if a micro:bit is connected and return a serial object to talk to
    it.
    """
    port, serial_number = find_microbit()
    if port is None:
        raise IOError("Could not find micro:bit.")
    return Serial(port, SERIAL_BAUD_RATE, timeout=1, parity="N")


def execute(commands, serial=None, show_progress=False, callback=None):
    """
    Sends commands to the connected device via serial and returns the result.

    Optimised for speed:
    - All commands are sent in a single raw-mode session (one raw_on / raw_off pair).
    - Each command is written with 256-byte chunks and no artificial sleeps.
    - show_progress / callback are honoured for compatibility with the UI.

    Returns the stdout and stderr output from the device as (out, err) bytes.
    """
    close_serial = False
    if serial is None:
        serial = get_serial()
        close_serial = True
        time.sleep(0.05)
    result = b""
    err = b""
    raw_on(serial)
    # Write the actual commands and send CTRL-D to evaluate each one.
    total_size = len(commands)
    for cnt, command in enumerate(commands):
        command_bytes = command.encode("utf-8")
        for i in range(0, len(command_bytes), 256):
            serial.write(command_bytes[i : min(i + 256, len(command_bytes))])
            time.sleep(0.01)
        serial.write(b"\x04")  # Execute with CTRL-D
        
        old_timeout = serial.timeout
        serial.timeout = max(old_timeout if old_timeout is not None else 10, 10)
        try:
            response = serial.read_until(b"\x04>")  # Read until prompt.
        finally:
            serial.timeout = old_timeout
            
        if len(response) >= 2:  # OK is 2 bytes
            body = response[2:-2]
            parts = body.split(b"\x04", 1)
            out = parts[0]
            err = parts[1] if len(parts) > 1 else b""
            result += out
            if err:
                return b"", err
        if show_progress:
            callback.emit(round(cnt / total_size * 100))
    raw_off(serial)
    if close_serial:
        serial.close()
    return result, err


def clean_error(err):
    """
    Take stderr bytes returned from MicroPython and attempt to create a
    non-verbose error message.
    """
    if err:
        decoded = err.decode("utf-8")
        try:
            return decoded.split("\r\n")[-2]
        except Exception:
            return decoded
    return "There was an error."


def ls(path, serial=None):
    """
    List the files on the micro:bit.

    If no serial object is supplied, microfs will attempt to detect the
    connection itself.

    Returns a list of the files on the connected device or raises an IOError if
    there's a problem.
    """
    out, err = execute(
        ["import os", "print(os.listdir({!r}))".format(path)], serial
    )
    if err:
        raise IOError(clean_error(err))
    return ast.literal_eval(out.decode("utf-8"))


def ls_with_types(path, serial=None):
    """
    List files on the device along with type information.

    Uses a SINGLE execute() call so only one soft-reboot occurs.
    On the device, tries os.ilistdir(); falls back to os.listdir() if
    ilistdir is unavailable (catches AttributeError).

    Returns a list of (name: str, is_dir: bool) tuples, or raises IOError.
    """
    cmd = (
        "import os\n"
        "try:\n"
        " r=[(e[0],bool(e[1]&16384)) for e in os.ilistdir({!r})]\n"
        "except Exception:\n"
        " r=[(f,False) for f in os.listdir({!r})]\n"
        "print(r)"
    ).format(path, path)
    out, err = execute([cmd], serial)
    if err:
        raise IOError(clean_error(err))
    return [(n, d) for n, d in ast.literal_eval(out.decode("utf-8"))]


def is_dir(path, serial=None):
    """
    Check if the path is a directory.
    """
    out, err = execute(["import os", "print(os.stat({!r}))".format(path)], serial)
    if err:
        raise IOError(clean_error(err))
    return ast.literal_eval(out.decode("utf-8"))[0] & 0x4000 != 0

def rm(filename, serial=None):
    """
    Removes a referenced file on the micro:bit.

    If no serial object is supplied, microfs will attempt to detect the
    connection itself.

    Returns True for success or raises an IOError if there's a problem.
    """
    script = (
        "import os\n"
        "def r(p):\n"
        " try:\n"
        "  if os.stat(p)[0]&0x4000:\n"
        "   for c in os.listdir(p): r(p.rstrip('/')+'/'+c)\n"
        "   os.rmdir(p)\n"
        "  else: os.remove(p)\n"
        " except: pass\n"
        "r('{}')"
    ).format(filename)
    commands = [script]
    out, err = execute(commands, serial)
    if err:
        raise IOError(clean_error(err))
    return True


def rename(old_path, new_path, serial=None):
    """
    Renames (moves) a file on the device from old_path to new_path.

    If no serial object is supplied, microfs will attempt to detect the
    connection itself.

    Returns True for success or raises an IOError if there's a problem.
    """
    commands = ["import os", "os.rename({!r}, {!r})".format(old_path, new_path)]
    out, err = execute(commands, serial)
    if err:
        raise IOError(clean_error(err))
    return True


def mkdir(path, serial=None):
    """
    Creates a directory on the device at the given path.

    If no serial object is supplied, microfs will attempt to detect the
    connection itself.

    Returns True for success or raises an IOError if there's a problem.
    """
    commands = ["import os", "os.mkdir({!r})".format(path)]
    out, err = execute(commands, serial)
    if err:
        raise IOError(clean_error(err))
    return True



def put(self, filename, target=None, serial=None):
    """
    Puts a referenced file on the LOCAL file system onto the
    file system on the device.

    Optimised: uses 128-byte chunks (2x the original 64-byte) via execute(),
    which already sends data without artificial sleeps (256-byte serial writes).

    If no serial object is supplied, microfs will attempt to detect the
    connection itself.

    Returns True for success or raises an IOError if there's a problem.
    """
    if os.path.isdir(filename) or not os.path.isfile(filename):
        raise IOError("No such file.")
    with open(filename, "rb") as local:
        content = local.read()
    filename = os.path.basename(filename)
    if target is None:
        target = filename
    commands = ["fd = open({!r}, 'wb')".format(target), "f = fd.write"]
    while content:
        line = content[:128]
        if PY2:
            commands.append("f(b" + repr(line) + ")")
        else:
            commands.append("f(" + repr(line) + ")")
        content = content[128:]
    commands.append("fd.close()")
    out, err = execute(commands, serial, True, self.on_put_update_file)
    if err:
        raise IOError(clean_error(err))
    return True


def get(self, filename, target=None, serial=None):
    commands = [
        "import sys",
        "f = open('{}', 'rb')".format(filename),
        "r = f.read",
        "result = True",
        "while result:\n result = r(256)\n if result:\n  sys.stdout.buffer.write(result)\n",
        "f.close()",
    ]
    out, err = execute(commands, serial, True, self.on_put_update_file)
    if err:
        raise IOError(clean_error(err))
    fd = open(target, 'wb')
    fd.write(out)
    fd.close()
    return True


def get_by_uart(self, filename, target=None, serial=None):
    """
    Gets a referenced file on the device's file system and copies it to the
    target (or current working directory if unspecified).

    If no serial object is supplied, microfs will attempt to detect the
    connection itself.

    Returns True for success or raises an IOError if there's a problem.
    """
    if target is None:
        target = filename
    commands = [
        "\n".join(
            [
                "try:",
                " from microbit import uart as u",
                "except ImportError:",
                " try:",
                "  from machine import UART",
                "  u = UART(0, {})".format(SERIAL_BAUD_RATE),
                " except Exception:",
                "  try:",
                "   from sys import stdout as u",
                "  except Exception:",
                "   raise Exception('Could not find UART module in device.')",
            ]
        ),
        "f = open('{}', 'rb')".format(filename),
        "r = f.read",
        "result = True",
        "while result:\n result = r(256)\n if result:\n  u.write(result)\n",
        "f.close()",
    ]
    out, err = execute(commands, serial, True, self.on_put_update_file)
    if err:
        raise IOError(clean_error(err))
    return True


def version(serial=None):
    """
    Returns version information for MicroPython running on the connected
    device.

    If such information is not available or the device is not running
    MicroPython, raise a ValueError.

    If any other exception is thrown, the device was running MicroPython but
    there was a problem parsing the output.
    """
    try:
        out, err = execute(["import os", "print(os.uname())"], serial)
        if err:
            raise ValueError(clean_error(err))
    except ValueError:
        # Re-raise any errors from stderr raised in the try block.
        raise
    except Exception:
        # Raise a value error to indicate unable to find something on the
        # microbit that will return parseable information about the version.
        # It doesn't matter what the error is, we just need to indicate a
        # failure with the expected ValueError exception.
        raise ValueError()
    raw = out.decode("utf-8").strip()
    raw = raw[1:-1]
    items = raw.split(", ")
    result = {}
    for item in items:
        key, value = item.split("=")
        result[key] = value[1:-1]
    return result


def main(argv=None):
    """
    Entry point for the command line tool 'ufs'.

    Takes the args and processes them as per the documentation. :-)

    Exceptions are caught and printed for the user.
    """
    if not argv:
        argv = sys.argv[1:]
    try:
        global COMMAND_LINE_FLAG
        COMMAND_LINE_FLAG = True
        parser = argparse.ArgumentParser(description=_HELP_TEXT)
        parser.add_argument(
            "command",
            nargs="?",
            default=None,
            help="One of 'ls', 'rm', 'put' or 'get'.",
        )
        parser.add_argument(
            "path",
            nargs="?",
            default=None,
            help="Use when a file needs referencing.",
        )
        parser.add_argument(
            "target",
            nargs="?",
            default=None,
            help="Use to specify a target filename.",
        )
        args = parser.parse_args(argv)
        if args.command == "ls":
            list_of_files = ls()
            if list_of_files:
                print(" ".join(list_of_files))
        elif args.command == "rm":
            if args.path:
                rm(args.path)
            else:
                print('rm: missing filename. (e.g. "ufs rm foo.txt")')
        elif args.command == "put":
            if args.path:
                put(args.path, args.target)
            else:
                print('put: missing filename. (e.g. "ufs put foo.txt")')
        elif args.command == "get":
            if args.path:
                get(args.path, args.target)
            else:
                print('get: missing filename. (e.g. "ufs get foo.txt")')
        else:
            # Display some help.
            parser.print_help()
    except Exception as ex:
        # The exception of no return. Print exception information.
        print(ex)
