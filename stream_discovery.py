"""
Device discovery and network stream utilities for digital microscopes.
Supports V4L2 USB camera enumeration and WiFi Gateway IP auto-detection.
"""

import os
import glob
import subprocess
import re
from typing import List, Dict, Optional


def get_default_gateway() -> Optional[str]:
    """
    Detects the default IPv4 gateway of the active network interface.
    When connected to a microscope's WiFi hotspot, the gateway IP is typically
    the IP address of the microscope itself (e.g., 192.168.29.1 or 192.168.10.1).
    """
    try:
        res = subprocess.run(
            ["ip", "route", "show", "default"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0
        )
        for line in res.stdout.splitlines():
            match = re.search(r"default via ([\d\.]+)", line)
            if match:
                return match.group(1)
    except Exception:
        pass

    try:
        with open("/proc/net/route", "r") as f:
            for line in f.readlines()[1:]:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    hex_gw = fields[2]
                    octets = [str(int(hex_gw[i:i+2], 16)) for i in (6, 4, 2, 0)]
                    gw = ".".join(octets)
                    if gw != "0.0.0.0":
                        return gw
    except Exception:
        pass

    return None


def is_microscope_reachable(ip: str = "192.168.29.1", port: int = 20000, timeout: float = 0.5) -> bool:
    """
    Checks if a WiFi microscope is responding to ICMP ping or UDP probing.
    """
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(b"JHCMD\x10\x00", (ip, port))
        s.close()
        # Fast route check
        res = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return res.returncode == 0
    except Exception:
        return False


def get_wifi_presets(gateway_ip: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Returns common preset streaming URLs used by WiFi digital microscopes
    (Max-See, MS5B, Inskam, Jiusion, Depstech, Generic GP/Anyka).
    """
    gw = gateway_ip or get_default_gateway() or "192.168.29.1"
    
    return [
        {
            "name": "Max-See / MS5B (UDP: 192.168.29.1:20000)",
            "url": "jhcmd://192.168.29.1:20000"
        },
        {
            "name": f"Max-See / MS5B (UDP Gateway: {gw}:20000)",
            "url": f"jhcmd://{gw}:20000"
        },
        {
            "name": f"Gateway Detectada ({gw}:8080 MJPEG HTTP)",
            "url": f"http://{gw}:8080/?action=stream"
        },
        {
            "name": "Generalplus / Max-See (HTTP: 192.168.29.1:8080)",
            "url": "http://192.168.29.1:8080/?action=stream"
        },
        {
            "name": "Inskam RTSP (rtsp://192.168.10.1:7070/webcam)",
            "url": "rtsp://192.168.10.1:7070/webcam"
        },
        {
            "name": "Inskam HTTP (http://192.168.10.123:8080/?action=stream)",
            "url": "http://192.168.10.123:8080/?action=stream"
        },
        {
            "name": f"Gateway Detectada ({gw} HTTP Puerto 80)",
            "url": f"http://{gw}/?action=stream"
        },
        {
            "name": f"ESP32-CAM / Generic ({gw}:81/stream)",
            "url": f"http://{gw}:81/stream"
        },
        {
            "name": "Personalizada (Custom URL)",
            "url": ""
        }
    ]


def list_usb_cameras() -> List[Dict[str, str]]:
    """
    Lists all available V4L2 video capture devices.
    Filters out metadata-only nodes (e.g., /dev/video1 for UVC metadata).
    """
    cameras = []
    
    id_map = {}
    for link in glob.glob("/dev/v4l/by-id/*"):
        try:
            target = os.path.realpath(link)
            id_map[target] = os.path.basename(link)
        except Exception:
            pass

    for dev_path in sorted(glob.glob("/dev/video*")):
        try:
            dev_idx = os.path.basename(dev_path)
            sys_path = f"/sys/class/video4linux/{dev_idx}"
            if not os.path.exists(sys_path):
                continue
            
            name_file = os.path.join(sys_path, "name")
            card_name = "Camera"
            if os.path.exists(name_file):
                with open(name_file, "r") as f:
                    card_name = f.read().strip()
            
            # Skip metadata endpoint
            if "index1" in id_map.get(dev_path, "") and "index0" not in id_map.get(dev_path, ""):
                continue

            label = f"{card_name} ({dev_path})"
            if "GENERAL" in card_name or "Microscope" in card_name or "808" in card_name:
                label = f"🔬 {card_name} [{dev_path}]"

            cameras.append({
                "path": dev_path,
                "name": card_name,
                "label": label,
                "symlink": id_map.get(dev_path, "")
            })
        except Exception:
            pass

    return cameras
