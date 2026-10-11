"""Probe why the region-of-interest command (10 10 92) is rejected.

Read-only: sends only Get commands. After each command it also reads the camera's
internal debug log, which (on the related Thermal Master P3) is returned when more
than 1 byte is read from the status register.
Run with video streaming (e.g. ffplay /dev/video0): sudo python roi_probe.py
"""
import re
import struct
import time

import usb.core

from camera import STATUS_BUSY, STATUS_DONE, build_cmd, crc_ok, open_device

LOG_LEN = 128


def text_runs(data, min_len=4):
    """Printable ASCII runs of at least min_len characters."""
    return [m.decode() for m in re.findall(rb"[ -~]{%d,}" % min_len, data)]


def read_log(dev):
    try:
        return bytes(dev.ctrl_transfer(0xC0, 0x22, 0, 0, LOG_LEN))
    except usb.core.USBError as e:
        return f"(log read failed: {e})"


def show_log(log):
    if isinstance(log, str):
        print(f"    log: {log}")
        return
    print(f"    log bytes 0-15: {log[:16].hex(' ')}")
    runs = text_runs(log)
    print(f"    log text: {' | '.join(runs) if runs else '(none)'}")


def probe(dev, label, cmd):
    assert crc_ok(cmd), f"bad CRC: {label}"
    assert cmd[2] >= 0x80, f"not a Get command: {label}"
    resp_len = struct.unpack_from("<H", cmd, 12)[0]
    print(f"\n{label}\n  cmd: {cmd.hex(' ')}")
    try:
        dev.ctrl_transfer(0x40, 0x20, 0, 0, cmd)
        trace = []
        deadline = time.monotonic() + 2.0
        while True:
            st = dev.ctrl_transfer(0xC0, 0x22, 0, 0, 1)[0]
            trace.append(st)
            if st != STATUS_BUSY or time.monotonic() > deadline:
                break
            time.sleep(0.02)
        print(f"  status: {' '.join(f'{s:02x}' for s in trace[:5])}{' ...' if len(trace) > 5 else ''}"
              f" (polled {len(trace)}x)")
        show_log(read_log(dev))
        if st == STATUS_DONE and resp_len:
            resp = bytes(dev.ctrl_transfer(0xC0, 0x21, 0, 0, resp_len))
            print(f"  response: {resp.hex(' ')}")
            if cmd[2] == 0x92 and len(resp) == 14:
                print("  min/avg/max raw {} {} {}, min at ({},{}), max at ({},{})".format(
                    *struct.unpack("<7H", resp)))
    except usb.core.USBError as e:
        print(f"  USB error: {e}")


def roi(x1, y1, x2, y2, resp_len=14):
    return build_cmd(0x10, 0x10, 0x92, para1=struct.pack("<HH", x1, y1),
                     para2=struct.pack("<HH", x2, y2), resp_len=resp_len)


TESTS = [
    ("Baseline: time since power on (known to work)", build_cmd(0x10, 0x10, 0x93, resp_len=4)),
    ("Manual example 1, verbatim incl. CRC: (0,0)-(383,287)",
     bytes.fromhex("10 10 92 00 00 00 00 00 7f 01 1f 01 0e 00 00 00 e8 0c")),
    ("Manual example 2, verbatim incl. CRC: (50,50)-(333,237)",
     bytes.fromhex("10 10 92 00 32 00 32 00 4d 01 ed 00 0e 00 00 00 34 59")),
    ("Full frame (0,0)-(255,191), reply length 14", roi(0, 0, 255, 191)),
    ("Small region (50,50)-(200,150), reply length 14", roi(50, 50, 200, 150)),
    ("Small region, reply length 15 (14 + status byte as in UART reply)", roi(50, 50, 200, 150, 15)),
    ("Small region, reply length 16", roi(50, 50, 200, 150, 16)),
    ("Baseline again: time since power on", build_cmd(0x10, 0x10, 0x93, resp_len=4)),
]

dev = open_device()
print("Log before any command:")
show_log(read_log(dev))
for label, cmd in TESTS:
    probe(dev, label, cmd)
