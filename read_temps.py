"""Read module temperature and image min/avg/max over USB while UVC video keeps streaming.

Read-only: sends only "Get" commands from the CV series UART manual.
Run with: sudo python read_temps.py
"""
import struct

from camera import HEIGHT, WIDTH, build_cmd, open_device, query

dev = open_device()

print("Module temperature (10 10 91):")
resp = query(dev, build_cmd(0x10, 0x10, 0x91, resp_len=2), 2)
if resp is not None:
    raw = struct.unpack("<H", resp)[0]
    print(f"  {raw} -> {raw / 100:.2f} °C (internal sensor, ±10 °C per manual)")

print("Time since power on (10 10 93):")
resp = query(dev, build_cmd(0x10, 0x10, 0x93, resp_len=4), 4)
if resp is not None:
    print(f"  {struct.unpack('<I', resp)[0]} s")

# Names from the command list sheet; the SDK sheet numbers these differently (5 = SNR, 11 = YUV).
SOURCES = {0: "IR (raw detector)", 1: "KBC", 2: "TNR", 3: "SNR", 4: "DDE", 5: "YUV"}
print("Image data source (10 10 85):")
resp = query(dev, build_cmd(0x10, 0x10, 0x85, resp_len=1), 1)
if resp is not None:
    print(f"  {resp[0]} -> {SOURCES.get(resp[0], 'unknown')}")

OUTPUTS = {0x00: "USB", 0x01: "DVP", 0x02: "BT656 progressive", 0x12: "BT656 interlaced", 0x03: "MIPI"}
print("Digital video output (10 10 86):")
resp = query(dev, build_cmd(0x10, 0x10, 0x86, resp_len=4), 4)
if resp is not None:
    enabled, kind, rate = resp[0], resp[1], resp[2]
    print(f"  enabled={enabled} type={OUTPUTS.get(kind, f'unknown 0x{kind:02x}')} rate={rate} Hz")


def region_stats(x1, y1, x2, y2):
    print(f"Region min/avg/max (10 10 92), region ({x1},{y1})-({x2},{y2}):")
    cmd = build_cmd(0x10, 0x10, 0x92,
                    para1=struct.pack("<HH", x1, y1),
                    para2=struct.pack("<HH", x2, y2),
                    resp_len=14)
    resp = query(dev, cmd, 14)
    if resp is not None:
        t_min, t_avg, t_max, min_x, min_y, max_x, max_y = struct.unpack("<7H", resp)
        print(f"  min raw {t_min} at ({min_x},{min_y})")
        print(f"  avg raw {t_avg}")
        print(f"  max raw {t_max} at ({max_x},{max_y})")
        print("  (raw units unknown; needs calibration against a known temperature)")


region_stats(0, 0, WIDTH - 1, HEIGHT - 1)
region_stats(16, 16, 239, 175)
