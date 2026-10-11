# thermal-camera

Notes and scripts for a USB thermal camera (USB ID `3474:43c1`). The goal was to send
commands from the vendor command list while the video keeps streaming, and to find out
whether the camera can report temperatures.

> [!WARNING]
> Use these scripts and the command list at your own risk. Some commands change the camera
> permanently or can cut its USB video (see [Commands to avoid](#commands-to-avoid)). The
> included scripts only read settings, but they were tested on a single camera.

## The camera

| | |
|---|---|
| USB ID | `3474:43c1`, manufacturer string "Thermal Cam Co.,Ltd", product "Camera" |
| Sold as | **UV256** by Hdaniee (Shenzhen Chengen Thermovision) |
| Module | Raytron **WN2-256**, also sold as **Mini2 256** (same module, the manuals are identical) |
| Reports itself as | name `Camera WN2256`, part number `WN2256`, firmware `00.00.02.04` |
| Sensor | 256×192, 12 µm, 8–14 µm, uncooled VOx |
| Type | **Imaging only** ("observation type"); no temperature measurement |
| Shutter | Mechanical; clicks when the stream starts and recalibrates periodically (often after power-up, less once warm). The video blanks for a moment each time. |
| Firmware OS | RT-Thread (the debug log shows the `msh />` shell prompt) |

The temperature-measuring version is the separate **WN2T**, announced in March 2026.
This camera was bought in November 2024.

## USB interfaces

The descriptors only show a standard UVC camera: one Video Control and one Video
Streaming interface, both bound to `uvcvideo`. There is no serial port, HID interface or
UVC extension unit.

- `/dev/video0`: YUYV 256×192 at 25 or 50 fps
- `/dev/video1`: UVC metadata

The video is an **8-bit grayscale image with automatic contrast**: the chroma bytes are
always 128, and brightness is stretched to fill the range for whatever is in view, so a
grey level does not correspond to a fixed temperature. The first ~25 frames after the
stream starts are black (initial shutter calibration).

## Command channel over USB

The camera accepts the commands from the command list
([cv系列的UART手册-英文版.xlsx](cv系列的UART手册-英文版.xlsx)) as **vendor control transfers**,
even though the descriptors don't advertise them. The protocol was first documented for
the Thermal Master P3, which uses the same vendor ID.

| Step | bmRequestType | bRequest | Data |
|---|---|---|---|
| Send command | `0x40` | `0x20` | 18 bytes |
| Read status | `0xC0` | `0x22` | 1 byte: `02` = done, `03` after reading the reply, `04` = rejected |
| Read reply | `0xC0` | `0x21` | reply length from the command |

- **Command format:** the 16-byte command block from the manual plus a CRC-16/XMODEM
  checksum (little-endian), **without** the UART header `55 43 49 12 00`.
- **Reply format:** raw data only, without the UART framing (`BE AA … EB AA`).
- **Device recipient (`0x40`/`0xC0`):** these requests work while `uvcvideo` keeps
  streaming; tested with `ffplay` running, no dropped frames.
- **Interface recipient (`0x41`/`0xC1`):** also works, but requires detaching
  `uvcvideo`, which stops the video.
- **Needs root:** the scripts must run with `sudo` (or a udev rule granting access).

Some replies depend on an active video stream. Without a program receiving video, the
digital output reads as off and the image data source query is rejected. **Run commands
with a video client open**, e.g. `ffplay /dev/video0`.

## What works

Current settings, read with `snapshot.py` (2026-10-11, factory state):

| Setting | Value |
|---|---|
| Digital video output | USB, 50 Hz (only while streaming) |
| Detector frame rate | 50 Hz |
| Analog video output | enabled, PAL |
| Image data source | 0 (reported as raw detector, but the actual output is the processed image) |
| Palette / scene mode | white hot / general |
| Brightness, contrast, detail, gamma, noise reduction | 50 each |
| Edge enhancement | 0 |
| Zoom | 1.0×, centered at (127,95) |
| Auto shutter | reported "off" (threshold 56 ≈ 1.75 °C, interval 5–300 s), although the shutter clearly recalibrates automatically |

The full snapshots are in `snapshot-*.json`.

**Module temperature** (`10 10 91`) returns a live value that rises slowly as the camera
warms up (raw ~10300–10700). The manual says °C × 100, which would mean ~105 °C and is
implausible; the unit is unclear (°F × 100 would give ~40 °C, but that is unconfirmed).
It's the module's internal temperature anyway, not the scene.

## What doesn't work

**Region-of-interest temperatures** (`10 10 92`, min/avg/max and hot/cold spots) are
rejected (status `04` → `00`) in every variant tried:

- the manual's example commands copied byte for byte, so the checksum isn't the cause
- full frame, a small region, and out-of-range coordinates
- reply lengths 14, 15 and 16
- with and without video streaming

The firmware doesn't implement temperature measurement, consistent with the module being
imaging-only.

**Y16 temperature output** exists on other Raytron modules, but only in their
temperature-measuring versions. For example, the
[TC2-C manual](https://www.raytron-microelectronics.com/wp-content/uploads/2024/07/TC2-C-Uncooled-Infrared-Thermal-Module-Product-Manual_V2.0_20240808.pdf)
lists "YUV422 (image data) / Y16 (temperature data)" for its measuring version (`SWR`).
Neither the WN2 manual, the WN2 datasheet nor the command list mentions Y16, and this
camera only offers YUYV.

## Scripts

All scripts are read-only: they send only "Get" commands. Run them with
`sudo python <script>` and `ffplay /dev/video0` open in another terminal.

| Script | Purpose |
|---|---|
| [get_name.py](get_name.py) | First test: device name via the interface (detaches `uvcvideo`) |
| [get_name_dev.py](get_name_dev.py) | Device name via the device recipient (video keeps running) |
| [read_temps.py](read_temps.py) | Module temperature, uptime, video settings, region attempts |
| [camera.py](camera.py) | Shared module: checksum, command builder, `query()` with status polling |
| [roi_probe.py](roi_probe.py) | Region-command variants plus a read of the debug log |
| [snapshot.py](snapshot.py) | Reads 37 settings and saves them to `snapshot-<timestamp>.json` |

## Commands to avoid

Some commands in the list change the camera permanently or can cut the USB video:

- **Saving:** `10 10 51` (parameter save), `10 10 49` (save output format) and all
  calibration saves
- **Parameter restore** `10 10 52`: according to Mini2_USB, it can lose the video feed;
  recovery needs Hdaniee's Windows software, which isn't available online
- **Factory calibration:** K value, dead-pixel and "pot lid" (lens) calibration,
  including clear and restore
- **Firmware update mode** `01 01 42`
- **Disabling digital output** or switching it to DVP/BT656/MIPI (`10 10 46`)
- **YUV format** `10 03 4D` (changes the byte order of the video)
- **Sleep** `10 10 48` (afterwards the camera only responds to wake-up)

Image settings such as palette, contrast and zoom are probably lost on power-off unless
saved, but this hasn't been tested yet.

## Open ideas

- **Video-based hotspot tool:** relative warm and cold spots from the image. These can't
  be converted to °C because of the automatic contrast.
- **Debug shell:** the module's second UART (UART1, 3.3 V) likely exposes the RT-Thread
  `msh` shell. This would require opening the housing.
- **Ask for the vendor software:** see below.

## Vendor software

There is no public download of the Windows host software or SDK (searched 2026-10-11).
It's only available on request from:

- **Hdaniee** (seller of the UV256): contact addresses are on the
  [Hdaniee UV page](https://www.hdaniee.com/uv.html).
  According to Mini2_USB, their Windows software can restore the camera's parameters.
- **Auvidea** (Germany), which sells the same camera as
  [UV256-4](https://auvidea.eu/product/uv256-4mm-usb-thermal-camera-upgraded-interfaces/).
  Their [product brief](https://auvidea.eu/download/D70111-70112_v1.2.pdf) lists "USB serial
  communication with user PC (host)" and an SDK for Windows, Linux and Android, on request.
- **Raytron**, the module maker. Their other module manuals say SDKs are available from
  technical support.

Questions worth asking: the SDK or host software for `3474:43c1` with firmware
`00.00.02.04`, and whether any firmware for this module supports temperature measurement.

## References

- [Raytron WN2 product manual](https://www.raytron-microelectronics.com/wp-content/uploads/2024/07/WN2-Series-Observation-Type-Uncooled-Infrared-Module-Product-Manual_V2.0_20250304.pdf)
- [Raytron WN2T (temperature-measuring version)](https://www.raytron-microelectronics.com/uncooled-lwir-modules/wn2t-temperature-measurement-thermal-module)
- [Jacob-OTW/Mini2_USB](https://github.com/Jacob-OTW/Mini2_USB): Python library for this
  camera family (send-only), with the Hdaniee command list and the Mini2 manual
- [jvdillon/p3-ir-camera](https://github.com/jvdillon/p3-ir-camera): USB protocol of the
  Thermal Master P3 (same vendor ID, same control requests)

## Disclaimer

The scripts and this README were written with the help of an AI assistant (Claude by
Anthropic). The findings come from tests run on one camera and from public sources, and may
be incomplete or wrong for other units or firmware versions. Commands that change the
camera are at your own risk.
