#!/usr/bin/env python3
"""W05A WiFi Microscope Viewer

Connects to a MaiKeLong W05A microscope over WiFi and displays the live
MJPEG stream.  Also supports offline replay of pcap captures.

Protocol notes (eeffeeff UDP):
  - Port 10005: command channel (device info, license)
  - Port 10006: stream registration
  - Port 10007: heartbeat (device → client, client ACKs with empty UDP)
  - Port 10900: JPEG stream (registered via CMD 4)
  - Stream packets: 16-byte header + JPEG payload
    byte 0:    fixed 0x01
    byte 1:    8-bit sequence counter
    byte 2:    frame counter (wraps at 256)
    byte 3:    last-packet flag (1 = final packet of frame)
    bytes 4-5: packet index within frame (LE uint16, 1-based)
    bytes 10-11: device ID (0x86cd)
    bytes 12-13: width  (LE uint16)
    bytes 14-15: height (LE uint16)
    bytes 16+:   JPEG fragment
"""

import argparse
import socket
import struct
import subprocess
import threading
import time

import cv2
import numpy as np

MICROSCOPE_IP = "192.168.1.1"
CMD_PORT   = 10005
STREAM_REG = 10006
STREAM_RX  = 10900
HB_PORT    = 10007

MAGIC = b"\xee\xff\xee\xff"

# Suppress libjpeg "Corrupt JPEG data" warnings on stderr
import os as _os
if not _os.environ.get("DLSCOPE_JPEG_WARNINGS"):
    import ctypes, ctypes.util
    _libc = ctypes.CDLL(ctypes.util.find_library("c"))
    _stderr_fd = 2
    _devnull = _os.open(_os.devnull, _os.O_WRONLY)
    _saved_stderr = _os.dup(_stderr_fd)

    def _suppress_stderr():
        _os.dup2(_devnull, _stderr_fd)

    def _restore_stderr():
        _os.dup2(_saved_stderr, _stderr_fd)
else:
    def _suppress_stderr(): pass
    def _restore_stderr(): pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def make_cmd(seq: int, cmd: int, param: int) -> bytes:
    return struct.pack("<4sHHI", MAGIC, seq, cmd, param)


# ---------------------------------------------------------------------------
# device info
# ---------------------------------------------------------------------------

def parse_device_info(data: bytes) -> dict | None:
    """Parse a CMD 1 response into a device-info dict."""
    if len(data) < 140 or data[:4] != MAGIC:
        return None
    cmd = struct.unpack_from("<H", data, 6)[0]
    if cmd != 1:
        return None
    payload = data[8:]

    def _str(start: int, length: int) -> str:
        return payload[start:start + length].split(b"\x00")[0].decode("ascii", errors="replace")

    return {
        "manufacturer": _str(5, 32),
        "model":        _str(37, 32),
        "firmware":     _str(69, 16),
        "device_id":    _str(85, 32),
    }


# ---------------------------------------------------------------------------
# connection management
# ---------------------------------------------------------------------------

def register_stream(sock: socket.socket) -> dict | None:
    """Send the three registration commands and return device info if received."""
    sock.sendto(make_cmd(0, 1, 1), (MICROSCOPE_IP, CMD_PORT))
    sock.sendto(make_cmd(1, 2, 1), (MICROSCOPE_IP, CMD_PORT))
    sock.sendto(
        struct.pack("<4sHHHHI", MAGIC, 2, 4, 1, 2, STREAM_RX),
        (MICROSCOPE_IP, STREAM_REG),
    )

    # Try to read the device-info response (non-blocking-ish)
    old_timeout = sock.gettimeout()
    sock.settimeout(1.0)
    info = None
    try:
        for _ in range(5):
            data, _ = sock.recvfrom(512)
            info = parse_device_info(data)
            if info:
                break
    except TimeoutError:
        pass
    sock.settimeout(old_timeout)
    return info


def start_heartbeat(sock: socket.socket, stop_event: threading.Event,
                    snap_event: threading.Event) -> threading.Thread:
    """Reply to device heartbeats with empty UDP ACKs on port 10007.

    The device sends eeffeeff CMD 9 packets to port 10007 roughly every
    second.  The DLScope app replies with empty UDP packets.  Without
    these ACKs the device may throttle or drop the stream.

    Also monitors heartbeat byte 8 for the hardware snap button — when
    it transitions from 0 to 1, sets snap_event so the main loop can
    save the current frame.
    """
    hb_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    hb_sock.bind(("", HB_PORT))
    hb_sock.settimeout(1.0)

    def _loop():
        last_btn = 0
        while not stop_event.is_set():
            try:
                data, addr = hb_sock.recvfrom(256)
                if data[:4] == MAGIC:
                    hb_sock.sendto(b"", (MICROSCOPE_IP, HB_PORT))
                    # Snap button detection: byte 8 = 1 while pressed
                    if len(data) > 8:
                        btn = data[8]
                        if btn == 1 and last_btn == 0:
                            snap_event.set()
                        last_btn = btn
            except TimeoutError:
                pass
        hb_sock.close()

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# packet sources
# ---------------------------------------------------------------------------

def live_packets(sock: socket.socket):
    """Yield (data, addr) from a live UDP socket, re-registering on timeout."""
    while True:
        try:
            yield sock.recvfrom(65535)
        except TimeoutError:
            log("Timeout — re-registering stream...")
            register_stream(sock)


def replay_packets(pcap_file: str, speed: float = 0.0):
    """Yield (data, addr) by replaying stream packets from a pcap via tshark."""
    log(f"Replaying {pcap_file} (speed={'realtime' if speed else 'max'})")
    result = subprocess.run(
        ["tshark", "-r", pcap_file,
         "-Y", "udp.srcport == 10006",
         "-T", "fields",
         "-e", "frame.time_relative",
         "-e", "data.data"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"tshark failed: {result.stderr.strip()}")

    lines = [l for l in result.stdout.splitlines() if "\t" in l]
    log(f"Loaded {len(lines)} stream packets from pcap")

    prev_t = None
    addr = (MICROSCOPE_IP, STREAM_REG)

    for line in lines:
        t_str, hex_data = line.split("\t", 1)
        if not hex_data:
            continue
        t = float(t_str)
        if speed > 0 and prev_t is not None:
            delay = (t - prev_t) / speed
            if delay > 0:
                time.sleep(delay)
        prev_t = t
        yield bytes.fromhex(hex_data), addr

    log("Replay finished")


# ---------------------------------------------------------------------------
# main display loop
# ---------------------------------------------------------------------------

def run(packets, is_live: bool = False, skip_dirty: bool = False,
        snap_event: threading.Event | None = None) -> None:
    buf          = b""
    pkts         = 0
    frames       = 0
    failed       = 0
    dirty_count  = 0
    t_stat       = time.time()
    last_seq     = None
    last_frame   = None
    expect_idx   = 1
    frame_dirty  = False

    for data, addr in packets:
        pkts += 1

        # skip command responses mixed into the stream socket
        if data[:4] == MAGIC:
            continue

        if len(data) <= 16:
            continue

        seq       = data[1]
        frame_num = data[2]
        last_flag = data[3]
        pkt_idx   = struct.unpack_from("<H", data, 4)[0]
        payload   = data[16:]

        # ---- sequence gap detection (for stats only) ----
        if last_seq is not None and seq != (last_seq + 1) & 0xFF:
            pass  # counted via frame_dirty
        last_seq = seq

        # ---- new frame started before previous finished ----
        if last_frame is not None and frame_num != last_frame:
            if buf:
                buf = b""
            expect_idx = 1
            frame_dirty = False
        last_frame = frame_num

        # ---- mid-frame packet gap ----
        if pkt_idx != expect_idx:
            frame_dirty = True
        expect_idx = pkt_idx + 1

        buf += payload

        if last_flag != 1:
            continue

        # ---- end of frame ----
        frame_size  = len(buf)
        expect_idx  = 1

        if buf[:2] != b"\xff\xd8":
            failed += 1
            buf = b""
            frame_dirty = False
            continue

        _suppress_stderr()
        frame = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
        _restore_stderr()
        buf = b""

        if frame is None:
            failed += 1
            frame_dirty = False
            continue

        frames += 1
        if frame_dirty:
            dirty_count += 1
            frame_dirty = False
            if skip_dirty:
                continue

        h, w = frame.shape[:2]

        if frames == 1:
            log(f"Streaming {w}x{h}")
        elif frames % 100 == 0:
            elapsed = time.time() - t_stat
            fps = 100 / elapsed if elapsed > 0 else 0
            log(f"{w}x{h} | {fps:.1f} fps | {frame_size//1024}K | frames={frames} failed={failed} dirty={dirty_count}")
            t_stat = time.time()

        cv2.imshow("W05A Microscope", frame)

        # Hardware snap button
        if snap_event and snap_event.is_set():
            snap_event.clear()
            fname = f"snap_{int(time.time())}.png"
            cv2.imwrite(fname, frame)
            log(f"SNAP saved {fname}")

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            fname = f"frame_{frames:05d}.png"
            cv2.imwrite(fname, frame)
            log(f"Saved {fname}")

    log(f"Done — frames={frames} failed={failed} dirty={dirty_count} packets={pkts}")
    cv2.destroyAllWindows()


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="W05A WiFi Microscope Viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Keys: Q = quit, S = save current frame as PNG",
    )
    parser.add_argument("--replay", metavar="PCAP",
                        help="replay a pcap file instead of live stream")
    parser.add_argument("--speed", type=float, default=0.0,
                        help="replay speed (1.0 = realtime, 0 = max)")
    parser.add_argument("--skip-dirty", action="store_true",
                        help="drop frames with missing packets (cleaner but lower fps)")
    args = parser.parse_args()

    skip_dirty = getattr(args, 'skip_dirty', False)

    if args.replay:
        run(replay_packets(args.replay, speed=args.speed), skip_dirty=skip_dirty)
        return

    log("Connecting to W05A microscope...")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("", STREAM_RX))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
        sock.settimeout(5.0)

        info = register_stream(sock)
        if info:
            log(f"  Manufacturer : {info['manufacturer']}")
            log(f"  Model        : {info['model']}")
            log(f"  Firmware     : {info['firmware']}")
            log(f"  Device ID    : {info['device_id']}")
        else:
            log("  (device info not received)")

        stop_hb = threading.Event()
        snap_event = threading.Event()
        start_heartbeat(sock, stop_hb, snap_event)
        log("Heartbeat responder started")

        log("Keys: Q = quit, S = save frame | Hardware snap button supported")
        try:
            run(live_packets(sock), is_live=True, skip_dirty=skip_dirty,
                snap_event=snap_event)
        finally:
            stop_hb.set()


if __name__ == "__main__":
    main()
