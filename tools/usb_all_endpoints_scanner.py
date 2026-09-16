#!/usr/bin/env python3
"""
Multi-Endpoint USB Scanner for Generalplus 1b3f:2002 Microscope.
Scans and listens to all possible IN endpoints (0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87)
and analyzes Video Payload Headers (UVC STI Bit 5) to locate hardware button triggers.
"""

import os
import sys
import time
import subprocess
import threading

# Auto-inject user site-packages if run with sudo
sudo_user = os.environ.get("SUDO_USER")
if sudo_user:
    home_dir = os.path.expanduser(f"~{sudo_user}")
    for pyver in ["python3.12", "python3.11", "python3.10"]:
        pkg_path = os.path.join(home_dir, ".local/lib", pyver, "site-packages")
        if os.path.exists(pkg_path) and pkg_path not in sys.path:
            sys.path.insert(0, pkg_path)

import usb.core
import usb.util

running = True

def inspect_descriptors():
    dev = usb.core.find(idVendor=0x1b3f, idProduct=0x2002)
    if not dev:
        print("[!] Microscope (1b3f:2002) not found.")
        return None
    
    print(f"[*] Found Microscope at Bus {dev.bus:03d} Device {dev.address:03d}")
    print("\n--- DETECTED INTERFACES & ENDPOINTS ---")
    active_endpoints = []
    
    for cfg in dev:
        for intf in cfg:
            print(f"Interface {intf.bInterfaceNumber} (Class={intf.bInterfaceClass}, SubClass={intf.bInterfaceSubClass}):")
            for ep in intf:
                direction = "IN" if (ep.bEndpointAddress & 0x80) else "OUT"
                ep_type = ["Control", "Isochronous", "Bulk", "Interrupt"][ep.bmAttributes & 3]
                print(f"   --> Endpoint 0x{ep.bEndpointAddress:02x} ({direction}, Type={ep_type}, MaxPacket={ep.wMaxPacketSize}, Interval={ep.bInterval})")
                if direction == "IN":
                    active_endpoints.append((intf.bInterfaceNumber, ep.bEndpointAddress, ep_type, ep.wMaxPacketSize))
    print("---------------------------------------\n")
    return dev, active_endpoints

def poll_endpoint(dev, intf_num, ep_addr, ep_type, max_pkt, results_log):
    global running
    poll_count = 0
    while running:
        poll_count += 1
        try:
            # Short timeout so threads yield
            data = dev.read(ep_addr, max_pkt or 512, timeout=80)
            if data:
                # Check for UVC Still Image Bit in video stream (0x87)
                # UVC Payload Header: Byte 1 Bit 5 is STI (Still Image Trigger)
                sti_flag = ""
                if len(data) >= 2 and (data[1] & 0x20):
                    sti_flag = " [*** UVC STILL IMAGE BIT 5 DETECTED! ***]"

                hex_data = bytes(data[:32]).hex()
                msg = f"\033[92;1m[ACTIVITY ON EP 0x{ep_addr:02x} ({ep_type})]\033[0m Len={len(data)}{sti_flag} Data={hex_data}..."
                print(f"\n{msg}", flush=True)
                results_log.append((ep_addr, len(data), hex_data))
        except usb.core.USBTimeoutError:
            pass
        except Exception as e:
            # Expected if endpoint is inactive
            pass
        time.sleep(0.01)

def main():
    global running
    res = inspect_descriptors()
    if not res:
        sys.exit(1)
    
    dev, active_endpoints = res

    # Detach kernel drivers from all interfaces
    detached = []
    for intf_num, _, _, _ in active_endpoints:
        if intf_num not in detached:
            try:
                if dev.is_kernel_driver_active(intf_num):
                    print(f"[*] Detaching kernel driver from Interface {intf_num}...")
                    dev.detach_kernel_driver(intf_num)
                    detached.append(intf_num)
            except Exception as e:
                print(f"[*] Note on detaching interface {intf_num}: {e}")

    # Also test potential hidden/undeclared endpoints from 0x81 to 0x87
    all_candidate_eps = list(active_endpoints)
    known_ep_addrs = [ep[1] for ep in active_endpoints]
    for candidate in [0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87]:
        if candidate not in known_ep_addrs:
            all_candidate_eps.append((0, candidate, "Candidate", 512))

    claimed_interfaces = []
    for intf_num in set(ep[0] for ep in all_candidate_eps):
        try:
            usb.util.claim_interface(dev, intf_num)
            claimed_interfaces.append(intf_num)
            print(f"[*] Successfully claimed Interface {intf_num}")
        except Exception as e:
            print(f"[!] Could not claim interface {intf_num}: {e}")

    print("\n" + "=" * 75)
    print(f"[*] LAUNCHING PARALLEL LISTENERS ON {len(all_candidate_eps)} ENDPOINTS:")
    for _, ep_addr, ep_type, _ in all_candidate_eps:
        print(f"    - Endpoint 0x{ep_addr:02x} ({ep_type})")
    print("=" * 75)
    print(">>> PULSA Y MANTÉN PRESIONADO EL BOTÓN DE FOTO EN EL MICROSCOPIO AHORA <<<")
    print(">>> (PRESS AND HOLD THE MICROSCOPE BUTTON MULTIPLE TIMES) <<<")
    print("=" * 75)
    print("[*] Monitoring all endpoints simultaneously... Press Ctrl+C to stop.\n", flush=True)

    results_log = []
    threads = []
    for intf_num, ep_addr, ep_type, max_pkt in all_candidate_eps:
        t = threading.Thread(
            target=poll_endpoint,
            args=(dev, intf_num, ep_addr, ep_type, max_pkt, results_log),
            daemon=True
        )
        t.start()
        threads.append(t)

    t0 = time.time()
    try:
        while True:
            elapsed = int(time.time() - t0)
            sys.stdout.write(f"\r[*] Time elapsed: {elapsed}s | Total button events caught: {len(results_log)} ")
            sys.stdout.flush()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[*] Stopping all listeners...")
        running = False

    time.sleep(0.3)
    
    # Cleanup & reattach drivers
    for intf_num in claimed_interfaces:
        try:
            usb.util.release_interface(dev, intf_num)
        except Exception:
            pass
    for intf_num in detached:
        try:
            print(f"[*] Reattaching kernel driver to Interface {intf_num}...")
            dev.attach_kernel_driver(intf_num)
        except Exception:
            pass

    print("\n==================== SCAN SUMMARY ====================")
    if results_log:
        print(f"\033[92;1mSUCCESS! Captured {len(results_log)} events:\033[0m")
        for ep, length, hex_preview in results_log:
            print(f"  - EP 0x{ep:02x}: Len={length} Data={hex_preview}")
    else:
        print("\033[93mNo events captured on any candidate endpoint.\033[0m")
    print("======================================================")

if __name__ == "__main__":
    main()
