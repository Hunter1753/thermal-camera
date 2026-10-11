"""USB command channel for the 3474:43c1 thermal camera (Raytron WN2-256).

Commands are the 16-byte blocks + CRC from the CV series UART manual, without the
UART header 55 43 49 12 00, sent as vendor control transfers to the device. The
device recipient lets uvcvideo keep streaming while commands are sent.
"""
import struct
import time

import usb.core

VID, PID = 0x3474, 0x43C1
WIDTH, HEIGHT = 256, 192

STATUS_DONE, STATUS_BUSY = 0x02, 0x04    # 0x04 assumed to mean "still processing"


def crc16_xmodem(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc


def build_cmd(cls, idx, sub, para1=b"\0" * 4, para2=b"\0" * 4, resp_len=0):
    body = bytes([cls, idx, sub, 0]) + para1 + para2 + struct.pack("<H", resp_len) + b"\0\0"
    return body + struct.pack("<H", crc16_xmodem(body))


def crc_ok(cmd):
    return len(cmd) == 18 and struct.pack("<H", crc16_xmodem(cmd[:16])) == cmd[16:]


# Sanity check against commands copied verbatim from the manual.
assert build_cmd(0x01, 0x01, 0x81, para1=b"\x01\0\0\0", resp_len=0x20) == bytes.fromhex(
    "01 01 81 00 01 00 00 00 00 00 00 00 20 00 00 00 FC 1E")
assert build_cmd(0x10, 0x10, 0x91, resp_len=2) == bytes.fromhex(
    "10 10 91 00 00 00 00 00 00 00 00 00 02 00 00 00 00 6A")
assert build_cmd(0x10, 0x10, 0x92, para1=bytes.fromhex("32 00 32 00"),
                 para2=bytes.fromhex("4d 01 ed 00"), resp_len=14) == bytes.fromhex(
    "10 10 92 00 32 00 32 00 4d 01 ed 00 0e 00 00 00 34 59")


def open_device():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        raise SystemExit("camera not found")
    return dev


def query(dev, cmd, resp_len, timeout=2.0, verbose=True):
    """Send cmd, wait until the camera reports done, return the response (None on failure)."""
    dev.ctrl_transfer(0x40, 0x20, 0, 0, cmd)                  # vendor OUT to device: send command
    seen = []
    deadline = time.monotonic() + timeout
    while True:
        st = dev.ctrl_transfer(0xC0, 0x22, 0, 0, 1)[0]
        if not seen or seen[-1][0] != st:
            seen.append([st, 0])
        seen[-1][1] += 1
        if st != STATUS_BUSY or time.monotonic() > deadline:
            break
        time.sleep(0.02)
    trace = " -> ".join(f"{s:02x}" + (f" x{n}" if n > 1 else "") for s, n in seen)
    if st != STATUS_DONE:
        if verbose:
            print(f"  status {trace}: not done, response not read (would be stale)")
        return None
    resp = bytes(dev.ctrl_transfer(0xC0, 0x21, 0, 0, resp_len))
    st2 = dev.ctrl_transfer(0xC0, 0x22, 0, 0, 1)[0]
    if verbose:
        print(f"  status {trace} / {st2:02x}  raw: {resp.hex(' ')}")
    return resp
