# 🛠️ Reverse Engineering & Forensic Diagnostics Suite

This directory contains the custom diagnostic tools, packet sniffers, and endpoint analyzers developed while reverse-engineering the **JoyHonest / Max-See / MS5B WiFi Digital Microscope** and investigating the physical hardware snapshot button across both **WiFi** and **USB** modes.

---

## 📖 The Backstory & Research Goal

The target microscope is a dual-mode device:
1. **Wireless Mode**: Connects as an ad-hoc Wi-Fi Access Point (SSID: `wifi-camera-MS5B-xxxx`).
2. **Wired Mode**: Connects as a USB UVC webcam (VID/PID: `1b3f:2002 Generalplus Technology Inc. 808 Camera`).

The goal was twofold:
- Build a native Linux viewer with sub-50 ms latency without relying on Android emulators or vendor apps.
- Determine how the physical photo button on the microscope barrel works and make it trigger snapshots natively across both WiFi and USB connections.

---

## 📡 Chapter 1: The WiFi Discovery (JoyHonest UDP Protocol)

### 1. The Breakthrough
Generic WiFi microscopes running JoyHonest firmware do not use RTSP or HTTP MJPEG on ports 80/8080. Instead, they run a proprietary UDP streaming protocol:
- **Command & Telemetry Port**: `UDP 20000`
- **Video Streaming Port**: `UDP 10900`
- **Host IP**: `192.168.29.1`

### 2. How the Hardware Button Works over WiFi
When connected over WiFi, the SoC runs an embedded RTOS that actively reads the hardware button GPIO:
1. The client initializes the session and heartbeat by sending `JHCMD\xd0\x01` every 500 ms to 1000 ms on port `20000`.
2. When the user presses the physical snapshot button on the barrel, the microscope emits a 7-byte telemetry packet on port `20000` starting with `JHCMD` (or alters telemetry flags in the 8-byte video frame headers on port `10900`).
3. By implementing a non-blocking UDP listener with a **350 ms software debounce window** in `capture_engine.py`, we achieved instant shutter triggering with a visual flash animation and automatic PNG export on every physical press.

### Related Tools:
- **`live_button_monitor.py`**: Real-time packet sniffer for ports 20000 and 10900.
- **`probe_button.py`**: Standalone listener for command port 20000 events.

---

## 🔌 Chapter 2: The USB Forensic Investigation (Generalplus 1b3f:2002)

### 1. The Hypothesis
When plugged in via USB, the device is recognized as `1b3f:2002 Generalplus Technology Inc. 808 Camera`. The USB descriptor (`lsusb -v`) presents promising declarations:
- **VideoControl Interface**: Declares Endpoint `0x81` (Interrupt IN, max packet 512 bytes).
- **VideoStreaming Interface**: Declares `bStillCaptureMethod = 2` and `bTriggerSupport = 1` (`bTriggerUsage = 0`: initiate still image capture on hardware button press).

Could we write a custom driver or userspace daemon to make the button trigger snapshots over USB as well?

### 2. Experiment 1: Active Polling on Endpoint `0x81`
In USB, devices are slaves and cannot transmit unsolicited data. The host must actively poll the endpoint.
- **Tool**: `usb_endpoint_sniffer.py --active`
- **Action**: The kernel driver was detached from Interface 0, and 611 consecutive `IN` transfer requests were submitted directly to Endpoint `0x81` while pressing and holding the button.
- **Result**: **611 / 611 Timeouts (`NAK`)**. Zero bytes returned. The FIFO buffer of Endpoint `0x81` was never populated by the hardware.

### 3. Experiment 2: Multi-Endpoint Parallel Scan
Could the button be transmitting on an auxiliary or undeclared endpoint?
- **Tool**: `usb_all_endpoints_scanner.py`
- **Action**: Spawned concurrent listener threads monitoring **all 7 candidate endpoints** simultaneously (`0x81`, `0x82`, `0x83`, `0x84`, `0x85`, `0x86`, `0x87`) for 43 seconds while repeatedly actuating the button.
- **Result**: `No events captured on any candidate endpoint`. All secondary endpoints remained completely silent.

### 4. Experiment 3: Live Video Stream Header Analysis (UVC STI Bit 5)
In the UVC specification, `bStillCaptureMethod = 2` indicates that still image triggers are transmitted **inside the active video stream on Endpoint `0x87`** via the **`UVC_STREAM_STI` flag (Bit 5)** of the 12-byte payload header.
- **Tool**: `test_uvc_still_bit.py`
- **Action**: Streamed video via OpenCV at 30 FPS while sniffing raw URBs via `usbmon` on Endpoint `0x87`.
- **Result**: `STI trigger count: 0`. The hardware never set Bit 5 in the video payload header.

---

## 🔬 Definitive Laboratory Conclusions

| Context | WiFi Mode (JoyHonest) | USB Mode (Generalplus UVC) |
| :--- | :--- | :--- |
| **SoC Firmware State** | Full embedded RTOS with networking & GPIO daemon. | Minimal Mask ROM standard UVC webcam mode. |
| **Hardware Button State** | **Active**: Sampled and broadcasted via UDP port `20000`. | **Disconnected**: GPIO sampling is halted in PC-Cam mode. |
| **USB Bus Activity on Press** | N/A | **Zero bytes** across all endpoints (`0x81`–`0x87`). |
| **Software Trigger Feasibility**| ✅ **100% Functional** in `microscope_viewer`. | ❌ **Hardware/Firmware Limitation** (no driver can fix missing silicon events). |
| **Recommended Capture Method**| Physical barrel button or `[Space]`. | **Keyboard Hotkey (`[Space]`)** or UI button. |

### Practical Engineering Takeaway
In high-magnification microscopy (500×–1000×), pressing a physical button on the microscope barrel exerts mechanical torque that shifts and blurs the optical focus. The **Spacebar hotkey (`[Space]`)** implemented in `microscope_viewer` is not only the necessary solution for USB mode, but also the ergonomically superior method for vibration-free sample inspection.

---

## 🧰 Summary of Tools in this Folder

| File | Purpose |
| :--- | :--- |
| **`live_button_monitor.py`** | Real-time diagnostic sniffer for JoyHonest WiFi telemetry (UDP 20000) and video headers (UDP 10900). |
| **`probe_button.py`** | Standalone listener for WiFi snapshot packets on port 20000. |
| **`usb_endpoint_sniffer.py`** | USB Request Block (URB) sniffer supporting passive `usbmon` and active PyUSB polling of Endpoint `0x81`. |
| **`usb_all_endpoints_scanner.py`**| Parallel multi-threaded scanner querying endpoints `0x81` through `0x87` simultaneously. |
| **`test_uvc_still_bit.py`** | Live video stream inspector decoding UVC payload headers to search for the `UVC_STREAM_STI` bit. |
| **`dlscope_upstream_viewer.py`** | Reference implementation of the legacy W05A microscope protocol (`\xee\xff\xee\xff`). |

---

## ⚖️ License

All diagnostic tools in this directory are open-source under the [MIT License](../LICENSE) © 2026 Francisco Betancourt.
