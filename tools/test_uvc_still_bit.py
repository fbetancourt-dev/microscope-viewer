#!/usr/bin/env python3
"""
UVC Stream Header Inspector (Endpoint 0x87 / STI Bit 5 Detector).
Tests whether the physical button sets the UVC Still Image trigger flag (Bit 5: STI)
inside the live video stream packets on Endpoint 0x87.
"""

import os
import sys
import time
import subprocess
import threading

# If executed via sudo, include the invoking user's local Python packages
sudo_user = os.environ.get("SUDO_USER")
if sudo_user:
    home_dir = os.path.expanduser(f"~{sudo_user}")
    for pyver in ["python3.12", "python3.11", "python3.10"]:
        pkg_path = os.path.join(home_dir, ".local/lib", pyver, "site-packages")
        if os.path.exists(pkg_path) and pkg_path not in sys.path:
            sys.path.insert(0, pkg_path)

import cv2

def find_device():
    try:
        out = subprocess.check_output(["lsusb"], text=True)
        for line in out.strip().split("\n"):
            if "1b3f:2002" in line or "Generalplus" in line:
                parts = line.split()
                return int(parts[1]), int(parts[3].replace(":", ""))
    except Exception:
        pass
    return 1, None

def monitor_usbmon(bus, dev_addr, stop_event):
    usbmon_path = f"/sys/kernel/debug/usb/usbmon/{bus}t"
    if not os.path.exists(usbmon_path):
        print("[!] Error: usbmon not available. Run: sudo modprobe usbmon")
        return

    pattern = f":{dev_addr:03d}:" if dev_addr else ""
    sti_detected_count = 0
    total_pkts = 0

    print(f"[*] Sniffing live UVC packets on Endpoint 0x87 (Bus {bus}, Dev {dev_addr})...")
    print("=" * 70)
    print(">>> STREAM IS LIVE! PULSA EL BOTÓN DE FOTO EN EL MICROSCOPIO AHORA <<<")
    print("=" * 70, flush=True)

    try:
        with open(usbmon_path, "r") as f:
            while not stop_event.is_set():
                line = f.readline()
                if not line:
                    time.sleep(0.005)
                    continue

                if pattern and pattern not in line:
                    continue

                # Filter for endpoint 7 (0x87 Video Stream)
                if ":7" not in line and ":135" not in line:
                    continue

                parts = line.strip().split()
                if len(parts) >= 6 and "=" in parts:
                    eq_idx = parts.index("=")
                    if eq_idx + 1 < len(parts):
                        data_hex = parts[eq_idx + 1]
                        if len(data_hex) >= 4:
                            total_pkts += 1
                            # Byte 0: Header length (usually 0c)
                            # Byte 1: Header info flags (BFH[0])
                            try:
                                hdr_len = int(data_hex[0:2], 16)
                                hdr_info = int(data_hex[2:4], 16)

                                # Check Bit 5: STI (Still Image Trigger)
                                if hdr_info & 0x20:
                                    sti_detected_count += 1
                                    ts = time.strftime("%H:%M:%S")
                                    print(f"\n\033[92;1m[{ts}] [!!! UVC STI BIT 5 DETECTED! !!!]\033[0m HdrInfo=0x{hdr_info:02x} FullHdr={data_hex[:24]}", flush=True)
                            except ValueError:
                                pass

    except Exception as e:
        print(f"[!] Sniffer error: {e}")

    print(f"\n[*] Total video packets inspected: {total_pkts} | STI trigger count: {sti_detected_count}")

def main():
    bus, dev_addr = find_device()
    print(f"[*] Target device: Bus {bus}, Address {dev_addr}")
    
    if not os.path.exists("/dev/video0"):
        print("[!] /dev/video0 not found! Ensure uvcvideo is attached and scanner is stopped (Ctrl+C).")
        sys.exit(1)

    print("[*] Opening /dev/video0 via OpenCV to activate Endpoint 0x87 streaming...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[!] Could not open /dev/video0. Is another app using it?")
        sys.exit(1)

    stop_event = threading.Event()
    sniffer_thread = threading.Thread(target=monitor_usbmon, args=(bus, dev_addr, stop_event), daemon=True)
    sniffer_thread.start()

    t0 = time.time()
    try:
        while time.time() - t0 < 30.0:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        cap.release()
        time.sleep(0.2)

if __name__ == "__main__":
    main()
