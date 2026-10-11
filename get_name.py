import usb.core, usb.util

CMD = bytes.fromhex("01 01 81 00 01 00 00 00 00 00 00 00 20 00 00 00 FC 1E")

dev = usb.core.find(idVendor=0x3474, idProduct=0x43c1)
if dev is None:
    raise SystemExit("camera not found")

reattach = dev.is_kernel_driver_active(0)
if reattach:
    dev.detach_kernel_driver(0)          # unbind uvcvideo from interface 0 only
try:
    usb.util.claim_interface(dev, 0)
    n = dev.ctrl_transfer(0x41, 0x20, 0, 0, CMD)              # vendor OUT: send command
    print("sent", n, "bytes")
    print("status:", bytes(dev.ctrl_transfer(0xC1, 0x22, 0, 0, 1)).hex())
    resp = bytes(dev.ctrl_transfer(0xC1, 0x21, 0, 0, 32))     # vendor IN: read response
    print("response:", resp.hex(" "), repr(resp))
    print("status:", bytes(dev.ctrl_transfer(0xC1, 0x22, 0, 0, 1)).hex())
except usb.core.USBError as e:
    print("USB error:", e)
finally:
    usb.util.release_interface(dev, 0)
    if reattach:
        dev.attach_kernel_driver(0)      # hand interface 0 back to uvcvideo
