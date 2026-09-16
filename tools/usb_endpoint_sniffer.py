#!/usr/bin/env python3
"""
USB Endpoint Sniffer & Analyzer for Generalplus / UVC Microscopes.
Listens to USB Request Blocks (URBs) and Interrupt Endpoints in real-time
to verify if hardware buttons trigger electrical events over the USB bus.
"""

import os
import sys
import time
import subprocess
import argparse

# If executed via sudo, include the invoking user's local Python packages
sudo_user = os.environ.get("SUDO_USER")
if sudo_user:
    home_dir = os.path.expanduser(f"~{sudo_user}")
    for pyver in ["python3.12", "python3.11", "python3.10"]:
        pkg_path = os.path.join(home_dir, ".local/lib", pyver, "site-packages")
        if os.path.exists(pkg_path) and pkg_path not in sys.path:
            sys.path.insert(0, pkg_path)


def find_microscope():
    """Finds bus and device address for Generalplus 1b3f:2002."""
    try:
        out = subprocess.check_output(["lsusb"], text=True)
        for line in out.strip().split("\n"):
            if "1b3f:2002" in line or "Generalplus" in line:
                parts = line.split()
                bus = int(parts[1])
                dev = int(parts[3].replace(":", ""))
                return bus, dev, line
    except Exception as e:
        print(f"Error executing lsusb: {e}")
    return None, None, None

def run_usbmon_sniffer(bus: int, dev_addr: int):
    """Monitors raw URBs via Linux debugfs usbmon."""
    usbmon_path = f"/sys/kernel/debug/usb/usbmon/{bus}t"
    
    if not os.path.exists(usbmon_path):
        print(f"[*] /sys/kernel/debug/usb/usbmon/{bus}t not found.")
        print("[*] Attempting to load usbmon module...")
        os.system("modprobe usbmon 2>/dev/null")
        if not os.path.exists(usbmon_path):
            print(f"[!] Error: Could not access {usbmon_path}.")
            print("    Please ensure usbmon is loaded: sudo modprobe usbmon")
            print("    And that debugfs is mounted: sudo mount -t debugfs none_debugs /sys/kernel/debug")
            return

    print(f"[*] Successfully attached to usbmon on Bus {bus}!")
    print(f"[*] Filtering packets for Device Address {dev_addr:03d} (Generalplus 1b3f:2002)")
    print("[*] Listening for events on Control (EP 0) and Interrupt (EP 0x81)...")
    print("=" * 70)
    print(">>> PULSA EL BOTÓN FÍSICO EN EL MICROSCOPIO AHORA (PRESS BUTTON NOW) <<<")
    print("=" * 70, flush=True)

    target_pattern = f":{dev_addr:03d}:"
    
    try:
        with open(usbmon_path, "r") as f:
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.01)
                    continue
                
                # Filter for our microscope device
                if target_pattern in line:
                    # usbmon format:
                    # tag timestamp event_type address:endpoint status length = data
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        ev_type = parts[2]
                        addr_ep = parts[3]
                        
                        # Filter out bulk/isoc video frames (EP 7 / 0x87) to avoid flooding
                        if ":7" in addr_ep or ":135" in addr_ep:
                            continue
                        
                        ts = time.strftime("%H:%M:%S")
                        data_part = " ".join(parts[5:]) if len(parts) > 5 else ""
                        
                        # Highlight Interrupt endpoint (EP 1 / 0x81)
                        if ":1" in addr_ep or ":129" in addr_ep:
                            print(f"\033[92;1m[{ts}] [INTERRUPT EP 0x81 EVENT!]\033[0m {line.strip()}", flush=True)
                        elif ":0" in addr_ep:
                            print(f"\033[94m[{ts}] [CONTROL EP 0]\033[0m {line.strip()}", flush=True)
                        else:
                            print(f"[{ts}] {line.strip()}", flush=True)
    except KeyboardInterrupt:
        print("\n[*] Sniffer stopped by user.")
    except PermissionError:
        print("\n[!] Permission Denied: Reading usbmon requires root privileges.")
        print(f"    Please execute: sudo python3 {sys.argv[0]}")

def run_pyusb_active_probe(bus: int, dev_addr: int):
    """Directly claims interface and queries Endpoint 0x81 using PyUSB."""
    try:
        import usb.core
        import usb.util
    except ImportError:
        print("[!] pyusb is not installed. Install via: pip install pyusb")
        return

    dev = usb.core.find(idVendor=0x1b3f, idProduct=0x2002)
    if dev is None:
        print("[!] Device 1b3f:2002 not found via PyUSB.")
        return

    print("[*] PyUSB found device 1b3f:2002.")
    
    # Detach kernel drivers (uvcvideo) on video interfaces to claim EP 0x81
    detached_interfaces = []
    for intf_num in [0, 1]:
        try:
            if dev.is_kernel_driver_active(intf_num):
                print(f"[*] Detaching kernel driver from Interface {intf_num} to claim EP 0x81...")
                dev.detach_kernel_driver(intf_num)
                detached_interfaces.append(intf_num)
        except Exception as e:
            print(f"[*] Note on interface {intf_num}: {e}")

    try:
        # Note: Do NOT call dev.set_configuration() as configuration is already active in kernel
        usb.util.claim_interface(dev, 0)
        print("[*] Successfully claimed Interface 0 (VideoControl)!")
        print("[*] Actively polling Endpoint 0x81 (Interrupt IN, max 512 bytes)...")
        print("=" * 70)
        print(">>> PULSA EL BOTÓN FÍSICO EN EL MICROSCOPIO AHORA (PRESS BUTTON NOW) <<<")
        print("=" * 70, flush=True)

        ep_addr = 0x81
        poll_count = 0
        t0 = time.time()
        last_tick = time.time()
        
        print("[*] Polling loop running. Press Ctrl+C to exit.\n", flush=True)
        while True:
            poll_count += 1
            now = time.time()
            if now - last_tick >= 1.0:
                print(f"[*] Actively polling EP 0x81... ({poll_count} requests sent, waiting for button event)", flush=True)
                last_tick = now
            try:
                # 100ms timeout
                data = dev.read(ep_addr, 512, timeout=100)
                if data:
                    hex_bytes = "".join([f"{b:02x}" for b in data])
                    print(f"\n\033[92;1m[!!! BUTTON PACKET DETECTED !!!]\033[0m Len={len(data)} Data={hex_bytes} Repr={bytes(data)!r}\n", flush=True)
            except usb.core.USBTimeoutError:
                pass
            except Exception as ex:
                print(f"\n[!] Read error: {ex}")
                break
    except KeyboardInterrupt:
        print("\n[*] Polling stopped by user.")

    except Exception as e:
        print(f"[!] Error claiming or reading device: {e}")
        print("    Ensure you run this script with sudo: sudo python3 tools/usb_endpoint_sniffer.py --active")
    finally:
        try:
            usb.util.release_interface(dev, 0)
        except Exception:
            pass
        for intf_num in detached_interfaces:
            try:
                print(f"[*] Reattaching kernel driver to Interface {intf_num}...")
                dev.attach_kernel_driver(intf_num)
            except Exception:
                pass

def main():
    parser = argparse.ArgumentParser(description="USB Endpoint Sniffer for Generalplus Microscopes")
    parser.add_argument("--active", action="store_true", help="Actively poll EP 0x81 via PyUSB instead of passive usbmon")
    args = parser.parse_args()

    bus, dev, line = find_microscope()
    if bus is None:
        print("[!] Generalplus microscope (1b3f:2002) not detected via lsusb.")
        print("    Please check that the USB cable is firmly plugged in.")
        sys.exit(1)

    print(f"[*] Found Microscope: {line}")
    print(f"[*] Location: Bus {bus:03d}, Device {dev:03d}")

    if args.active:
        run_pyusb_active_probe(bus, dev)
    else:
        run_usbmon_sniffer(bus, dev)

if __name__ == "__main__":
    main()
