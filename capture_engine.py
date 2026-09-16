"""
Low-latency capture engine for USB (V4L2) and WiFi (HTTP/RTSP) microscope video streams.
Employs dedicated grabber threads and single-slot frame dropping to ensure <50ms latency.
"""

import os
import time
import datetime
import threading
import socket
import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker


class LowLatencyCaptureThread(QThread):
    # Signals emitted to UI
    frame_ready = pyqtSignal(np.ndarray, float)       # frame (BGR), fps
    status_changed = pyqtSignal(bool, str)            # connected, message
    error_occurred = pyqtSignal(str)                  # error string
    snapshot_saved = pyqtSignal(str)                  # saved file path
    hardware_button_pressed = pyqtSignal(str)         # trigger action ("snapshot")
    recording_tick = pyqtSignal(int, str)             # seconds elapsed, filename

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mutex = QMutex()
        self.running = False
        
        # Source configuration
        self.is_usb = True
        self.usb_path = "/dev/video0"
        self.wifi_url = ""
        self.is_jh_udp = False
        self.jh_host = "192.168.29.1"
        self.jh_cmd_port = 20000
        self.jh_data_port = 10900
        
        # Performance & metrics
        self.fps = 0.0
        self.frame_count = 0
        self.dropped_frames = 0
        self.width = 640
        self.height = 480
        
        # Snapshot trigger
        self._snapshot_requested = False
        self._snapshot_dir = ""
        self._last_button_time = 0.0
        
        # Video recording
        self._recording = False
        self._video_writer = None
        self._record_filename = ""
        self._record_start_time = 0.0
        self._last_tick_time = 0.0

    def configure_usb(self, device_path: str):
        """Sets target device to local USB V4L2 node."""
        with QMutexLocker(self.mutex):
            self.is_usb = True
            self.is_jh_udp = False
            self.usb_path = device_path

    def configure_wifi(self, stream_url: str):
        """Sets target device to network HTTP / RTSP or JoyHonest UDP stream."""
        with QMutexLocker(self.mutex):
            self.is_usb = False
            raw_url = stream_url.strip()
            self.wifi_url = raw_url

            low = raw_url.lower()
            if low.startswith("jhcmd://") or low.startswith("udp://") or "192.168.29." in low or "ms5" in low or ":20000" in low:
                self.is_jh_udp = True
                clean = raw_url.replace("jhcmd://", "").replace("udp://", "").split("/")[0]
                if ":" in clean:
                    parts = clean.split(":")
                    self.jh_host = parts[0] or "192.168.29.1"
                    try:
                        self.jh_cmd_port = int(parts[1])
                    except ValueError:
                        self.jh_cmd_port = 20000
                else:
                    self.jh_host = clean or "192.168.29.1"
                    self.jh_cmd_port = 20000
                self.jh_data_port = 10900
            else:
                self.is_jh_udp = False

    def request_snapshot(self, output_dir: str):
        """Triggers saving the next available frame to disk."""
        with QMutexLocker(self.mutex):
            self._snapshot_dir = output_dir
            self._snapshot_requested = True

    def start_recording(self, output_dir: str):
        """Begins recording incoming frames to an MP4 video file."""
        with QMutexLocker(self.mutex):
            if self._recording:
                return
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self._record_filename = os.path.join(output_dir, f"microscope_{timestamp}.mp4")
            self._recording = True
            self._record_start_time = time.time()
            self._last_tick_time = time.time()

    def stop_recording(self):
        """Stops active video recording and finalizes container."""
        with QMutexLocker(self.mutex):
            self._recording = False
            if self._video_writer is not None:
                self._video_writer.release()
                self._video_writer = None

    def stop(self):
        """Stops the capture worker thread."""
        with QMutexLocker(self.mutex):
            self.running = False
        self.wait(1500)

    def _open_capture(self) -> cv2.VideoCapture:
        """Opens and tunes the video capture instance for minimum buffering."""
        if self.is_usb:
            # Use V4L2 backend directly
            cap = cv2.VideoCapture(self.usb_path, cv2.CAP_V4L2)
            if not cap.isOpened():
                # Fallback to default backend
                cap = cv2.VideoCapture(self.usb_path)
            
            if cap.isOpened():
                # Buffer size 1 to ensure zero queue lag
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
            return cap
        else:
            # Low latency FFmpeg network options
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "fflags;nobuffer|flags;low_delay|probesize;32|analyzeduration;0|max_delay;0"
            )
            cap = cv2.VideoCapture(self.wifi_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap

    def run(self):
        self.running = True
        if not self.is_usb and self.is_jh_udp:
            self._run_jh_udp()
        else:
            self._run_opencv_capture()

    def _run_jh_udp(self):
        """
        Dedicated JoyHonest / Max-See / MS5B UDP streaming receiver.
        Binds to UDP 20000 (status/control) and 10900 (JPEG data stream).
        """
        host = self.jh_host
        cmd_port = self.jh_cmd_port
        data_port = self.jh_data_port

        self.status_changed.emit(False, f"Conectando a microscopio UDP ({host}:{cmd_port})...")

        try:
            status_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            status_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            status_sock.bind(("0.0.0.0", cmd_port))
            status_sock.settimeout(0.05)
        except Exception as e:
            self.error_occurred.emit(f"No se pudo abrir socket de control en puerto {cmd_port}: {e}")
            self.status_changed.emit(False, f"Error socket control ({cmd_port})")
            return

        try:
            data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
            data_sock.bind(("0.0.0.0", data_port))
            data_sock.settimeout(0.5)
        except Exception as e:
            status_sock.close()
            self.error_occurred.emit(f"No se pudo abrir socket de datos en puerto {data_port}: {e}")
            self.status_changed.emit(False, f"Error socket datos ({data_port})")
            return

        status_sock.setblocking(False)
        status_sock.sendto(b"JHCMD\x10\x00", (host, cmd_port))
        status_sock.sendto(b"JHCMD\x20\x00", (host, cmd_port))
        status_sock.sendto(b"JHCMD\xd0\x01", (host, cmd_port))
        status_sock.sendto(b"JHCMD\xd0\x01", (host, cmd_port))

        self.status_changed.emit(True, f"Conectado a MS5B WiFi ({host})")

        frame_buf = bytearray()
        last_hb = time.time()
        fps_count = 0
        fps_start = time.time()
        consecutive_timeouts = 0

        while self.running:
            now = time.time()

            # Heartbeat every 0.5s and poll status flags
            if now - last_hb >= 0.5:
                try:
                    status_sock.sendto(b"JHCMD\xd0\x01", (host, cmd_port))
                    status_sock.sendto(b"JHCMD\x10\x00", (host, cmd_port))
                except Exception:
                    pass
                last_hb = now

            # Poll status socket non-blocking for events
            try:
                sdata, saddr = status_sock.recvfrom(512)
                if sdata:
                    # Ignore device identity broadcast (105 bytes)
                    if not (len(sdata) == 105 and sdata.startswith(b"JHCMD \x00")):
                        if now - self._last_button_time >= 0.35:
                            self._last_button_time = now
                            print(f"[HW-BUTTON] Triggered from port 20000: len={len(sdata)} data={sdata[:16].hex()}", flush=True)
                            self.hardware_button_pressed.emit("snapshot")
                            with QMutexLocker(self.mutex):
                                self._snapshot_requested = True
            except (BlockingIOError, TimeoutError):
                pass
            except Exception:
                pass

            # Receive packet from data socket
            try:
                pdata, _ = data_sock.recvfrom(2048)
                consecutive_timeouts = 0
            except TimeoutError:
                consecutive_timeouts += 1
                if consecutive_timeouts > 10:
                    try:
                        status_sock.sendto(b"JHCMD\xd0\x01", (host, cmd_port))
                    except Exception:
                        pass
                    consecutive_timeouts = 0
                continue
            except Exception:
                break

            if len(pdata) <= 8:
                continue

            pkt_idx = pdata[3]

            # Detect hardware button flags embedded in video packet headers (bytes 6 and 7)
            if pkt_idx == 0 and (pdata[6] != 0 or pdata[7] != 0):
                if now - self._last_button_time >= 0.35:
                    self._last_button_time = now
                    print(f"[HW-BUTTON] Triggered from video header: pdata[6]={pdata[6]} pdata[7]={pdata[7]}", flush=True)
                    self.hardware_button_pressed.emit("snapshot")
                    with QMutexLocker(self.mutex):
                        self._snapshot_requested = True

            # When packet 0 arrives, finalize and decode preceding frame
            if pkt_idx == 0:
                if len(frame_buf) > 0 and frame_buf[:2] == b"\xff\xd8":
                    frame = cv2.imdecode(np.frombuffer(frame_buf, np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        h, w = frame.shape[:2]
                        self.width, self.height = w, h

                        fps_count += 1
                        if now - fps_start >= 1.0:
                            self.fps = round(fps_count / (now - fps_start), 1)
                            fps_count = 0
                            fps_start = now

                        # Handle snapshot
                        with QMutexLocker(self.mutex):
                            if self._snapshot_requested:
                                self._snapshot_requested = False
                                save_dir = self._snapshot_dir or os.path.expanduser("~/Pictures/Microscope")
                                os.makedirs(save_dir, exist_ok=True)
                                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
                                save_path = os.path.join(save_dir, f"micro_{timestamp}.png")
                                cv2.imwrite(save_path, frame)
                                self.snapshot_saved.emit(save_path)

                        # Handle video recording
                        with QMutexLocker(self.mutex):
                            if self._recording:
                                if self._video_writer is None:
                                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                                    rec_fps = 20.0 if self.fps < 10 else self.fps
                                    self._video_writer = cv2.VideoWriter(
                                        self._record_filename, fourcc, rec_fps, (w, h)
                                    )
                                if self._video_writer is not None:
                                    self._video_writer.write(frame)

                                elapsed = int(now - self._record_start_time)
                                if now - self._last_tick_time >= 0.5:
                                    self._last_tick_time = now
                                    self.recording_tick.emit(elapsed, self._record_filename)

                        # Emit frame to GUI
                        self.frame_ready.emit(frame, self.fps)

                frame_buf = bytearray()

            frame_buf.extend(pdata[8:])

        # Clean shutdown: send stop command
        try:
            status_sock.sendto(b"JHCMD\xd0\x02", (host, cmd_port))
        except Exception:
            pass

        status_sock.close()
        data_sock.close()

        with QMutexLocker(self.mutex):
            if self._video_writer is not None:
                self._video_writer.release()
                self._video_writer = None

        self.status_changed.emit(False, "Desconectado.")

    def _run_opencv_capture(self):
        """
        OpenCV VideoCapture pipeline for USB (V4L2) and standard HTTP/RTSP streams.
        """
        while self.running:
            source_desc = self.usb_path if self.is_usb else self.wifi_url
            self.status_changed.emit(False, f"Conectando a {source_desc}...")
            
            cap = self._open_capture()
            if not cap or not cap.isOpened():
                self.status_changed.emit(False, f"No se pudo abrir la fuente: {source_desc}")
                # Wait before retry
                for _ in range(20):
                    if not self.running:
                        break
                    time.sleep(0.1)
                continue

            self.status_changed.emit(True, f"Conectado a {source_desc}")
            
            # FPS tracking
            fps_count = 0
            fps_start = time.time()
            consecutive_errors = 0
            
            # Update width and height from capture
            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
            self.width, self.height = actual_w, actual_h

            while self.running:
                # Direct read
                ret, frame = cap.read()
                
                if not ret or frame is None:
                    consecutive_errors += 1
                    if consecutive_errors > 30:
                        self.error_occurred.emit("Flujo de video interrumpido o desconectado.")
                        break
                    time.sleep(0.01)
                    continue
                
                consecutive_errors = 0
                now = time.time()
                fps_count += 1
                
                if now - fps_start >= 1.0:
                    self.fps = round(fps_count / (now - fps_start), 1)
                    fps_count = 0
                    fps_start = now

                # Handle snapshot
                with QMutexLocker(self.mutex):
                    if self._snapshot_requested:
                        self._snapshot_requested = False
                        save_dir = self._snapshot_dir or os.path.expanduser("~/Pictures/Microscope")
                        os.makedirs(save_dir, exist_ok=True)
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
                        save_path = os.path.join(save_dir, f"micro_{timestamp}.png")
                        cv2.imwrite(save_path, frame)
                        self.snapshot_saved.emit(save_path)

                # Handle video recording
                with QMutexLocker(self.mutex):
                    if self._recording:
                        if self._video_writer is None:
                            h, w = frame.shape[:2]
                            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                            rec_fps = 30.0 if self.fps < 10 else self.fps
                            self._video_writer = cv2.VideoWriter(
                                self._record_filename, fourcc, rec_fps, (w, h)
                            )
                        
                        if self._video_writer is not None:
                            self._video_writer.write(frame)
                            
                        elapsed = int(now - self._record_start_time)
                        if now - self._last_tick_time >= 0.5:
                            self._last_tick_time = now
                            self.recording_tick.emit(elapsed, self._record_filename)

                # Emit immediate frame to GUI
                self.frame_ready.emit(frame, self.fps)

            # Cleanup video capture and writer
            if cap:
                cap.release()
            with QMutexLocker(self.mutex):
                if self._video_writer is not None:
                    self._video_writer.release()
                    self._video_writer = None

            if self.running:
                time.sleep(1.0)

        self.status_changed.emit(False, "Desconectado.")
