import usb.core

CMD = bytes.fromhex("01 01 81 00 01 00 00 00 00 00 00 00 20 00 00 00 FC 1E")

dev = usb.core.find(idVendor=0x3474, idProduct=0x43c1)
if dev is None:
    raise SystemExit("camera not found")

# No detach/claim: uvcvideo keeps interface 0, so video can keep streaming.
print("uvcvideo bound to interface 0:", dev.is_kernel_driver_active(0))
try:
    n = dev.ctrl_transfer(0x40, 0x20, 0, 0, CMD)              # vendor OUT to device: send command
    print("sent", n, "bytes")
    print("status:", bytes(dev.ctrl_transfer(0xC0, 0x22, 0, 0, 1)).hex())
    resp = bytes(dev.ctrl_transfer(0xC0, 0x21, 0, 0, 32))     # vendor IN from device: read response
    print("response:", resp.hex(" "), repr(resp))
    print("status:", bytes(dev.ctrl_transfer(0xC0, 0x22, 0, 0, 1)).hex())
except usb.core.USBError as e:
    print("USB error:", e)
print("uvcvideo bound to interface 0:", dev.is_kernel_driver_active(0))
