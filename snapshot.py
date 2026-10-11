"""Read every "Get" command from the CV series UART manual and record the camera's current settings.

Read-only. Command bytes are copied verbatim from the manual (without the UART header);
their CRCs are checked before anything is sent.
Prints a table and saves snapshot-<timestamp>.json in the current directory.
Run with: sudo python snapshot.py
"""
import json
import os
import struct
from datetime import datetime

import usb.core

from camera import crc_ok, open_device, query

OFF_ON = {0: "off", 1: "on"}
# Scene numbering from the command list sheet; the SDK sheet uses a different order.
SCENES = {0: "low temperature highlight", 1: "linear stretch", 2: "low contrast", 3: "general (default)",
          4: "high contrast", 5: "highlight", 6: "reserved 1", 7: "reserved 2", 8: "reserved 3", 9: "outline"}
PALETTES = {0: "white hot", 1: "reserved", 2: "sepia", 3: "ironbow", 4: "rainbow", 5: "night", 6: "aurora",
            7: "red hot", 8: "jungle", 9: "medical", 10: "black hot", 11: "golden red"}
# Names from the command list sheet; the SDK sheet numbers these differently (5 = SNR, 11 = YUV).
SOURCES = {0: "IR (raw detector)", 1: "KBC", 2: "TNR", 3: "SNR", 4: "DDE", 5: "YUV"}
OUTPUTS = {0x00: "USB", 0x01: "DVP", 0x02: "BT656 progressive", 0x12: "BT656 interlaced", 0x03: "MIPI"}


def text(r):
    return r.split(b"\0")[0].decode("ascii", "replace")


def u8(r):
    return r[0]


def u16(r):
    return struct.unpack_from("<H", r)[0]


def named(names):
    return lambda r: f"{r[0]} ({names.get(r[0], 'unknown')})"


def digital_output(r):
    return f"enabled={r[0]} type={OUTPUTS.get(r[1], f'unknown 0x{r[1]:02x}')} rate={r[2]} Hz"


def analog_output(r):
    return f"enabled={r[0]} format={ {0: 'NTSC', 1: 'PAL'}.get(r[1], r[1]) }"


def coord_zoom(r):
    x, y = struct.unpack_from("<HH", r)
    return f"center=({x},{y}) zoom={r[4] / 10:.1f}x"


def cursor_pos(r):
    return "({},{})".format(*struct.unpack_from("<HH", r))


# (group, label, command bytes from the manual, decoder)
COMMANDS = [
    ("Device", "Device name", "01 01 81 00 01 00 00 00 00 00 00 00 20 00 00 00 fc 1e", text),
    ("Device", "Firmware version", "01 01 81 00 02 00 00 00 00 00 00 00 0b 00 00 00 32 32", text),
    ("Device", "VID", "01 01 81 00 04 00 00 00 00 00 00 00 02 00 00 00 7b ca", lambda r: f"0x{u16(r):04x}"),
    ("Device", "PID", "01 01 81 00 05 00 00 00 00 00 00 00 02 00 00 00 0e c9", lambda r: f"0x{u16(r):04x}"),
    ("Device", "Part number", "01 01 81 00 06 00 00 00 00 00 00 00 20 00 00 00 b7 16", text),
    ("Device", "Serial number", "01 01 81 00 07 00 00 00 00 00 00 00 20 00 00 00 c2 15", text),
    ("Device", "Time since power on", "10 10 93 00 00 00 00 00 00 00 00 00 04 00 00 00 5b bb",
     lambda r: f"{struct.unpack_from('<I', r)[0]} s"),
    ("Device", "Module temperature (raw)", "10 10 91 00 00 00 00 00 00 00 00 00 02 00 00 00 00 6a", u16),
    ("Device", "Sleep state", "10 10 88 00 00 00 00 00 00 00 00 00 01 00 00 00 21 a7",
     named({0: "working", 1: "sleep"})),
    ("Device", "Boot logo", "10 10 81 00 00 00 00 00 00 00 00 00 01 00 00 00 2b 37", named(OFF_ON)),

    ("Shutter", "Auto shutter", "10 02 81 00 00 00 00 00 00 00 00 00 01 00 00 00 78 34", named(OFF_ON)),
    ("Shutter", "Auto shutter temperature threshold", "10 02 82 00 00 01 00 00 00 00 00 00 02 00 00 00 4e fa",
     lambda r: f"{u16(r)} (~{u16(r) / 32:.2f} °C per manual)"),
    ("Shutter", "Auto shutter min interval", "10 02 82 00 01 01 00 00 00 00 00 00 02 00 00 00 3b f9",
     lambda r: f"{u16(r)} s"),
    ("Shutter", "Auto shutter max interval", "10 02 82 00 02 01 00 00 00 00 00 00 02 00 00 00 a4 fc",
     lambda r: f"{u16(r)} s"),
    ("Shutter", "Anti-burn protection", "10 03 8b 00 00 00 00 00 00 00 00 00 01 00 00 00 2d 87", named(OFF_ON)),

    ("Video", "Digital video output", "10 10 86 00 00 00 00 00 00 00 00 00 04 00 00 00 68 fb", digital_output),
    ("Video", "Analog video output", "10 10 8a 00 00 00 00 00 00 00 00 00 02 00 00 00 3f ca", analog_output),
    ("Video", "Detector frame rate", "10 10 84 00 00 00 00 00 00 00 00 00 01 00 00 00 ef b1",
     lambda r: f"{r[0]} Hz"),
    ("Video", "Image data source", "10 10 85 00 00 00 00 00 00 00 00 00 01 00 00 00 8e ca", named(SOURCES)),
    ("Video", "YUV format", "10 03 8c 00 00 00 00 00 00 00 00 00 01 00 00 00 2b f7",
     named({0: "UYVY", 1: "VYUY", 2: "YUYV", 3: "YVYU"})),
    ("Video", "External sync", "10 10 8b 00 00 00 00 00 00 00 00 00 01 00 00 00 82 2a", named(OFF_ON)),
    ("Video", "DVP/I2C voltage", "10 10 87 00 00 00 00 00 00 00 00 00 01 00 00 00 4c 3c",
     named({0: "1.8 V", 1: "3.3 V"})),

    ("Display", "Freeze frame", "10 10 82 00 00 00 00 00 00 00 00 00 01 00 00 00 88 ba", named(OFF_ON)),
    ("Display", "Mirror/flip", "10 10 83 00 00 00 00 00 00 00 00 00 01 00 00 00 e9 c1",
     named({0: "none", 1: "left-right", 2: "up-down", 3: "both"})),
    ("Display", "Center zoom", "01 31 82 00 00 00 00 00 00 00 00 00 01 00 00 00 4e 02",
     lambda r: f"{r[0] / 10:.1f}x"),
    ("Display", "Coordinate zoom", "01 31 91 00 00 00 00 00 00 00 00 00 05 00 00 00 eb 83", coord_zoom),
    ("Display", "Cursor", "10 11 81 00 00 00 00 00 00 00 00 00 01 00 00 00 d7 99",
     named({0: "hidden", 1: "shown"})),
    ("Display", "Cursor position", "10 11 82 00 00 00 00 00 00 00 00 00 04 00 00 00 31 a8", cursor_pos),

    ("Image", "Scene mode", "10 04 89 00 01 00 00 00 00 00 00 00 01 00 00 00 0d 0a", named(SCENES)),
    ("Image", "Palette", "10 03 85 00 00 00 00 00 00 00 00 00 01 00 00 00 21 67", named(PALETTES)),
    ("Image", "Detail enhancement", "10 04 85 00 01 00 00 00 00 00 00 00 01 00 00 00 c3 1c", u8),
    ("Image", "Brightness", "10 04 87 00 01 00 00 00 00 00 00 00 01 00 00 00 01 ea", u8),
    ("Image", "Contrast", "10 04 8a 00 01 00 00 00 00 00 00 00 01 00 00 00 ae 87", u8),
    ("Image", "Spatial noise reduction", "10 04 8b 00 01 00 00 00 00 00 00 00 01 00 00 00 cf fc", u8),
    ("Image", "Temporal noise reduction", "10 04 8c 00 01 00 00 00 00 00 00 00 01 00 00 00 c9 8c", u8),
    ("Image", "Gamma", "10 04 8d 00 01 00 00 00 00 00 00 00 01 00 00 00 a8 f7", u8),
    ("Image", "Edge enhancement", "10 04 8e 00 00 00 00 00 00 00 00 00 01 00 00 00 7e 79", u8),
]

# Refuse to send anything unless every command is a getter with a valid CRC.
for _, label, hexcmd, _ in COMMANDS:
    cmd = bytes.fromhex(hexcmd)
    assert crc_ok(cmd), f"bad CRC: {label}"
    assert cmd[2] >= 0x80, f"not a Get command: {label}"

dev = open_device()
results = []
group = None
for grp, label, hexcmd, decode in COMMANDS:
    if grp != group:
        print(f"\n{grp}")
        group = grp
    cmd = bytes.fromhex(hexcmd)
    resp_len = struct.unpack_from("<H", cmd, 12)[0]
    entry = {"group": grp, "label": label, "command": hexcmd}
    try:
        resp = query(dev, cmd, resp_len, verbose=False)
    except usb.core.USBError as e:
        resp, entry["error"] = None, str(e)
    if resp is None:
        entry.setdefault("error", "rejected (status not done)")
        value = f"-- {entry['error']}"
    else:
        entry["raw"] = resp.hex(" ")
        try:
            value = str(decode(resp))
        except Exception as e:                          # unexpected reply shape: keep the raw bytes
            value = f"? ({e})"
        entry["value"] = value
    results.append(entry)
    print(f"  {label:<36} {value}")

name = f"snapshot-{datetime.now():%Y%m%d-%H%M%S}.json"
with open(name, "w") as f:
    json.dump(results, f, indent=2)
if "SUDO_UID" in os.environ:                            # give the file back to the user who ran sudo
    os.chown(name, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
print(f"\nSaved {name}")
