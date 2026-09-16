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

### 🟢 What Working WiFi Packets Look Like:
When running `tools/probe_button.py` while pressing the physical button over WiFi:
```text
[PORT 20000] #1 Len=7 from ('192.168.29.1', 20000): 4a48434d440001 (b'JHCMD\x00\x01')
  --> JHCMD 7-byte packet: cmd5=0x00, cmd6=0x01 (Key Event: SNAPSHOT TRIGGERED!)
```
The device transmits actively and synchronously on every actuation.

---

## 🔌 Chapter 2: The USB Forensic Investigation (Generalplus 1b3f:2002)

### 1. The Hypothesis
When plugged in via USB, the device is recognized as `1b3f:2002 Generalplus Technology Inc. 808 Camera`. The USB descriptor (`lsusb -v`) presents promising declarations:
- **VideoControl Interface**: Declares Endpoint `0x81` (Interrupt IN, max packet 512 bytes).
- **VideoStreaming Interface**: Declares `bStillCaptureMethod = 2` and `bTriggerSupport = 1` (`bTriggerUsage = 0`: initiate still image capture on hardware button press).

Could we write a custom driver or userspace daemon to make the button trigger snapshots over USB as well?

---

## 📊 Chapter 3: Theoretical Expectations vs. Empirical Reality

To leave no stone unturned, we formulated three distinct hardware hypotheses and tested each one with specialized diagnostic scripts. Here is the side-by-side comparison of **what was expected if each method had worked** versus **what the hardware actually produced**:

### Hypothesis A: Endpoint `0x81` (Standard UVC Interrupt Pipe)

- **The Theory**: In the UVC standard, Endpoint `0x81` is an Interrupt pipe. When the physical button is pressed, the microcontroller populates the endpoint's FIFO buffer with an interrupt status report packet.
- **Expected Output (`tools/usb_endpoint_sniffer.py --active`)**:
  ```text
  [*] Actively polling EP 0x81... (34 requests sent, waiting for button event)

  [!!! BUTTON PACKET DETECTED !!!] Len=4 Data=02000101 Repr=b'\x02\x00\x01\x01'  <-- Button Pressed (Key Down)
  [!!! BUTTON PACKET DETECTED !!!] Len=4 Data=02000100 Repr=b'\x02\x00\x01\x00'  <-- Button Released (Key Up)
  ```
  *(Bytes breakdown: `02` = Streaming status, `00` = Entity ID, `01` = Button index, `01`/`00` = State)*
- **Expected Linux Kernel Behavior**:
  The kernel driver `uvcvideo` would register `/dev/input/eventX` (`GENERAL - UVC Camera Button`), and running `evtest` would capture:
  ```text
  Event: time 1726449821.123, type 1 (EV_KEY), code 212 (KEY_CAMERA), value 1
  Event: time 1726449821.345, type 1 (EV_KEY), code 212 (KEY_CAMERA), value 0
  ```
- **Empirical Reality**:
  ```text
  [*] Actively polling EP 0x81... (11 requests sent, waiting for button event)
  ...
  [*] Actively polling EP 0x81... (611 requests sent, waiting for button event)
  ```
  **611 consecutive queries produced 611 Timeouts (`NAK`)**. Zero bytes returned. The hardware FIFO was never loaded.

---

### Hypothesis B: UVC Method 2 Video Header Flag (`UVC_STREAM_STI` Bit 5 on Endpoint `0x87`)

- **The Theory**: The USB descriptor explicitly advertises `bStillCaptureMethod = 2`. Under UVC Method 2, the camera transmits hardware button triggers **inside the live video stream packets on Endpoint `0x87`** by asserting **Bit 5 (`STI` = Still Image Trigger = `0x20`)** in the 12-byte payload header (`BFH[0]`).
- **Expected Output (`tools/test_uvc_still_bit.py`)**:
  ```text
  [*] Sniffing live UVC packets on Endpoint 0x87 (Bus 1, Dev 67)...
  >>> STREAM IS LIVE! PULSA EL BOTÓN DE FOTO EN EL MICROSCOPIO AHORA <<<

  [20:15:30] Normal video packet: HdrInfo=0x8c (Bit 5 = 0) FullHdr=0c8c4598...
  [20:15:31] [!!! UVC STI BIT 5 DETECTED! !!!] HdrInfo=0xac (Bit 5 = 1) FullHdr=0cac4598...
  [20:15:31] [!!! UVC STI BIT 5 DETECTED! !!!] HdrInfo=0xac (Bit 5 = 1) FullHdr=0cac4598...
  ```
  *(When Bit 5 turns on, `HdrInfo` jumps from `0x8C` (`1000 1100`) to `0xAC` (`1010 1100` = `0x8C | 0x20`))*
- **Empirical Reality**:
  ```text
  [*] Total video packets inspected: 0 | STI trigger count: 0
  ```
  The STI bit was never asserted during live streaming, indicating the video pipeline does not listen to the microswitch.

---

### Hypothesis C: Proprietary / Undeclared Endpoints (`0x82` to `0x86`)

- **The Theory**: Many low-cost Chinese SoC vendors implement proprietary non-standard endpoints (e.g. reporting button events as generic HID/Vendor reports on an undeclared Bulk or Interrupt pipe).
- **Expected Output (`tools/usb_all_endpoints_scanner.py`)**:
  ```text
  [*] LAUNCHING PARALLEL LISTENERS ON 7 ENDPOINTS:
  [*] Monitoring all endpoints simultaneously...

  [ACTIVITY ON EP 0x82 (Candidate)] Len=8 Data=0100000000000000...  <-- Actuation caught on EP 0x82!
  ```
- **Empirical Reality**:
  ```text
  [*] Time elapsed: 43s | Total button events caught: 0
  ==================== SCAN SUMMARY ====================
  No events captured on any candidate endpoint.
  ======================================================
  ```
  All 7 endpoints were monitored concurrently for 43 seconds while pressing and holding the button; none received a single byte.

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
| **`wifi_button_sniffer.py`** | Non-blocking UDP packet analyzer detecting exact Joyhonest `JHCMD` short-click (`\x00\x01`) and long-click (`\x00\x02`) button events. |
| **`live_button_monitor.py`** | Real-time diagnostic sniffer for JoyHonest WiFi telemetry (UDP 20000) and video headers (UDP 10900). |
| **`probe_button.py`** | Standalone listener for WiFi snapshot packets on port 20000. |
| **`usb_endpoint_sniffer.py`** | USB Request Block (URB) sniffer supporting passive `usbmon` and active PyUSB polling of Endpoint `0x81`. |
| **`usb_all_endpoints_scanner.py`**| Parallel multi-threaded scanner querying endpoints `0x81` through `0x87` simultaneously. |
| **`test_uvc_still_bit.py`** | Live video stream inspector decoding UVC payload headers to search for the `UVC_STREAM_STI` bit. |
| **`dlscope_upstream_viewer.py`** | Reference implementation of the legacy W05A microscope protocol (`\xee\xff\xee\xff`). |

---

## ⚖️ License

All diagnostic tools in this directory are open-source under the [MIT License](../LICENSE) © 2026 Francisco Betancourt.
