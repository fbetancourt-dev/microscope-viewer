"""
Professional GUI for Digital Microscope with USB & WiFi Dual Mode.
Includes low-latency rendering, interactive zoom/pan, measurement reticles, and filters.
"""

import os
import sys
import subprocess
import cv2
import numpy as np

from PyQt6.QtCore import Qt, QPoint, QRect, QRectF, QTimer
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QFont, QAction, QIcon, QBrush
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QSlider, QCheckBox, QGroupBox, QTabWidget,
    QFileDialog, QStatusBar, QSplitter, QScrollArea, QFrame, QMessageBox,
    QApplication
)

from capture_engine import LowLatencyCaptureThread
from stream_discovery import list_usb_cameras, get_wifi_presets, get_default_gateway


class VideoViewport(QWidget):
    """
    High-performance video display widget supporting:
    - Zero-lag frame rendering
    - Aspect ratio retention
    - Interactive digital zoom & pan (mouse wheel & drag)
    - Measurement overlays (crosshairs, grids, circles)
    - Image enhancements (brightness, contrast, sharpness, inversion)
    - Freeze-frame mode
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self.setStyleSheet("background-color: #121212;")
        self.setMouseTracking(True)

        # Raw & processed frame
        self._raw_frame: np.ndarray = None
        self._display_pixmap: QPixmap = None
        self._frozen = False
        self._frozen_frame: np.ndarray = None
        self._flash_opacity = 0.0

        # Zoom and pan
        self.zoom_factor: float = 1.0
        self.pan_offset = QPoint(0, 0)
        self._is_panning = False
        self._last_mouse_pos = QPoint(0, 0)

        # Overlays
        self.show_crosshair = True
        self.show_grid = False
        self.grid_spacing = 50  # pixels
        self.show_circles = False
        self.overlay_color = QColor("#00FF66")  # Bright neon green

        # Image processing filters
        self.brightness = 0     # -100 to 100
        self.contrast = 1.0     # 0.5 to 3.0
        self.sharpness = 0      # 0 to 5
        self.color_mode = "Normal" # Normal, Grayscale, Invert
        self.flip_h = False
        self.flip_v = False

    def trigger_shutter_flash(self):
        """Creates a momentary white flash on the viewport for photo capture feedback."""
        self._flash_opacity = 0.75
        self.update()
        QTimer.singleShot(70, self._dim_flash)

    def _dim_flash(self):
        self._flash_opacity = 0.0
        self.update()

    def update_frame(self, frame: np.ndarray):
        """Called when a new frame is delivered by the capture thread."""
        if self._frozen:
            return
        self._raw_frame = frame
        self._process_and_redraw()

    def toggle_freeze(self) -> bool:
        """Toggles freeze frame state. Returns new state."""
        self._frozen = not self._frozen
        if self._frozen and self._raw_frame is not None:
            self._frozen_frame = self._raw_frame.copy()
        return self._frozen

    def is_frozen(self) -> bool:
        return self._frozen

    def reset_zoom_pan(self):
        self.zoom_factor = 1.0
        self.pan_offset = QPoint(0, 0)
        self._process_and_redraw()

    def set_zoom(self, factor: float):
        self.zoom_factor = max(1.0, min(5.0, factor))
        if self.zoom_factor == 1.0:
            self.pan_offset = QPoint(0, 0)
        self._process_and_redraw()

    def set_overlay_color(self, hex_color: str):
        self.overlay_color = QColor(hex_color)
        self.update()

    def _apply_filters(self, img: np.ndarray) -> np.ndarray:
        """Applies brightness, contrast, sharpness, orientation, and color modes."""
        out = img

        # 1. Flip
        if self.flip_h and self.flip_v:
            out = cv2.flip(out, -1)
        elif self.flip_h:
            out = cv2.flip(out, 1)
        elif self.flip_v:
            out = cv2.flip(out, 0)

        # 2. Brightness & Contrast
        if self.brightness != 0 or self.contrast != 1.0:
            out = cv2.convertScaleAbs(out, alpha=self.contrast, beta=self.brightness)

        # 3. Sharpness (Unsharp Mask)
        if self.sharpness > 0:
            amount = self.sharpness * 0.4
            blurred = cv2.GaussianBlur(out, (0, 0), 2.0)
            out = cv2.addWeighted(out, 1.0 + amount, blurred, -amount, 0)

        # 4. Color Mode
        if self.color_mode == "Grayscale":
            gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
            out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        elif self.color_mode == "Invert":
            out = cv2.bitwise_not(out)

        return out

    def _process_and_redraw(self):
        target = self._frozen_frame if self._frozen else self._raw_frame
        if target is None:
            return

        # Apply image filters
        processed = self._apply_filters(target)

        # Convert OpenCV BGR to Qt QImage
        h, w, ch = processed.shape
        bytes_per_line = ch * w
        # QImage created directly from buffer
        qimg = QImage(processed.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
        self._display_pixmap = QPixmap.fromImage(qimg)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Fill background
        painter.fillRect(self.rect(), QColor("#121212"))

        if self._display_pixmap is None or self._display_pixmap.isNull():
            # Placeholder text
            painter.setPen(QColor("#666666"))
            painter.setFont(QFont("Sans", 14))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Microscopio no conectado\nSelecciona USB o WiFi para iniciar"
            )
            return

        # Viewport dimensions
        vw = self.width()
        vh = self.height()
        pw = self._display_pixmap.width()
        ph = self._display_pixmap.height()

        # Compute aspect ratio fit
        scale = min(vw / pw, vh / ph) * self.zoom_factor
        dest_w = pw * scale
        dest_h = ph * scale

        # Centering with pan offset
        dest_x = (vw - dest_w) / 2.0 + self.pan_offset.x()
        dest_y = (vh - dest_h) / 2.0 + self.pan_offset.y()

        dest_rect = QRectF(dest_x, dest_y, dest_w, dest_h)
        painter.drawPixmap(dest_rect.toRect(), self._display_pixmap)

        # Draw overlays
        self._draw_overlays(painter, dest_rect)

        # Draw "FROZEN" indicator if active
        if self._frozen:
            painter.setPen(QColor("#FFCC00"))
            painter.setFont(QFont("Sans", 12, QFont.Weight.Bold))
            painter.drawText(20, 30, "❄ IMAGEN CONGELADA (PAUSA)")

        # Shutter flash effect
        if self._flash_opacity > 0.0:
            painter.fillRect(self.rect(), QColor(255, 255, 255, int(self._flash_opacity * 255)))

    def _draw_overlays(self, painter: QPainter, dest_rect: QRectF):
        pen = QPen(self.overlay_color)
        pen.setWidth(1)
        painter.setPen(pen)

        cx = dest_rect.center().x()
        cy = dest_rect.center().y()

        # 1. Measurement Grid
        if self.show_grid and self.grid_spacing > 5:
            pen_grid = QPen(self.overlay_color)
            pen_grid.setWidth(1)
            pen_grid.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(pen_grid)

            # Step scaled with zoom
            step = self.grid_spacing * (dest_rect.width() / max(1, self._display_pixmap.width()))
            if step > 8:
                # Vertical lines
                x = cx
                while x < dest_rect.right():
                    painter.drawLine(int(x), int(dest_rect.top()), int(x), int(dest_rect.bottom()))
                    x += step
                x = cx - step
                while x > dest_rect.left():
                    painter.drawLine(int(x), int(dest_rect.top()), int(x), int(dest_rect.bottom()))
                    x -= step

                # Horizontal lines
                y = cy
                while y < dest_rect.bottom():
                    painter.drawLine(int(dest_rect.left()), int(y), int(dest_rect.right()), int(y))
                    y += step
                y = cy - step
                while y > dest_rect.top():
                    painter.drawLine(int(dest_rect.left()), int(y), int(dest_rect.right()), int(y))
                    y -= step

        # 2. Concentric Circles
        if self.show_circles:
            pen_circle = QPen(self.overlay_color)
            pen_circle.setWidth(1)
            painter.setPen(pen_circle)
            min_dim = min(dest_rect.width(), dest_rect.height())
            radii = [0.1, 0.2, 0.35, 0.5]
            for r in radii:
                radius = (min_dim / 2.0) * r
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))

        # 3. Reticle / Crosshair
        if self.show_crosshair:
            pen_reticle = QPen(self.overlay_color)
            pen_reticle.setWidth(1)
            painter.setPen(pen_reticle)

            # Main cross
            painter.drawLine(int(dest_rect.left()), int(cy), int(dest_rect.right()), int(cy))
            painter.drawLine(int(cx), int(dest_rect.top()), int(cx), int(dest_rect.bottom()))

            # Center target ring & dot
            painter.drawEllipse(QPoint(int(cx), int(cy)), 16, 16)
            painter.setBrush(QBrush(self.overlay_color))
            painter.drawEllipse(QPoint(int(cx), int(cy)), 2, 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)

    # Mouse navigation (Zoom & Pan)
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        old_zoom = self.zoom_factor
        if delta > 0:
            new_zoom = min(5.0, self.zoom_factor * 1.15)
        else:
            new_zoom = max(1.0, self.zoom_factor / 1.15)

        if new_zoom != old_zoom:
            self.set_zoom(new_zoom)
            # Notify parent to update slider
            main_win = self.window()
            if hasattr(main_win, "sync_zoom_slider"):
                main_win.sync_zoom_slider(new_zoom)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.zoom_factor > 1.0:
            self._is_panning = True
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._is_panning and self.zoom_factor > 1.0:
            diff = event.pos() - self._last_mouse_pos
            self.pan_offset += diff
            self._last_mouse_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event):
        # Double click toggles fullscreen
        main_win = self.window()
        if hasattr(main_win, "toggle_fullscreen"):
            main_win.toggle_fullscreen()


class MicroscopeMainWindow(QMainWindow):
    """
    Main Application Window integrating:
    - Dual Source Switcher (USB / WiFi)
    - Low-latency Engine
    - Laboratory inspection tools
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Microscopio Digital - Visor Dual USB & WiFi")
        self.resize(1180, 720)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
                color: #e0e0e0;
            }
            QGroupBox {
                border: 1px solid #333333;
                border-radius: 6px;
                margin-top: 14px;
                padding-top: 10px;
                font-weight: bold;
                color: #00E5FF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QPushButton {
                background-color: #2b2b2b;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px 12px;
                color: #f0f0f0;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #383838;
                border-color: #00E5FF;
            }
            QPushButton:pressed {
                background-color: #007788;
            }
            QComboBox, QLineEdit {
                background-color: #222222;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #333333;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00E5FF;
                border: 1px solid #0099aa;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QTabBar::tab {
                background: #252525;
                color: #aaaaaa;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #333333;
                color: #00E5FF;
                font-weight: bold;
            }
            QStatusBar {
                background: #111111;
                color: #999999;
            }
        """)

        # Worker thread
        self.capture_thread = LowLatencyCaptureThread(self)
        self.capture_thread.frame_ready.connect(self._on_frame_ready)
        self.capture_thread.status_changed.connect(self._on_status_changed)
        self.capture_thread.error_occurred.connect(self._on_error)
        self.capture_thread.snapshot_saved.connect(self._on_snapshot_saved)
        self.capture_thread.hardware_button_pressed.connect(self._on_hardware_button_pressed)
        self.capture_thread.recording_tick.connect(self._on_recording_tick)

        self.is_connected = False
        self.is_recording = False
        self.save_directory = os.path.expanduser("~/Pictures/Microscope")
        os.makedirs(self.save_directory, exist_ok=True)

        self._init_ui()
        self._populate_usb_devices()
        self._populate_wifi_presets()

        # Try auto-connecting to USB if microscope detected
        QTimer.singleShot(500, self._auto_connect_usb)

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Left: Video Viewport
        self.viewport = VideoViewport(self)
        main_layout.addWidget(self.viewport, stretch=4)

        # Right: Scrollable Control Sidebar
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedWidth(360)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(4, 0, 4, 0)
        sidebar_layout.setSpacing(10)

        # 1. Source Connection Tabs
        sidebar_layout.addWidget(self._create_source_tabs())

        # 2. Capture & Action Tools
        sidebar_layout.addWidget(self._create_capture_group())

        # 3. Zoom & Pan Controls
        sidebar_layout.addWidget(self._create_zoom_group())

        # 4. Image Enhancement Filters
        sidebar_layout.addWidget(self._create_filter_group())

        # 5. Overlays and Reticles
        sidebar_layout.addWidget(self._create_overlay_group())

        sidebar_layout.addStretch()
        scroll_area.setWidget(sidebar)
        main_layout.addWidget(scroll_area, stretch=1)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.lbl_conn_status = QLabel("🔴 Desconectado")
        self.lbl_resolution = QLabel("Res: --")
        self.lbl_fps = QLabel("FPS: 0.0")
        self.lbl_latency = QLabel("Latencia: <35ms")
        
        self.status_bar.addWidget(self.lbl_conn_status, 2)
        self.status_bar.addPermanentWidget(self.lbl_resolution, 1)
        self.status_bar.addPermanentWidget(self.lbl_fps, 1)
        self.status_bar.addPermanentWidget(self.lbl_latency, 1)

    # --- UI Builders ---
    def _create_source_tabs(self) -> QWidget:
        tabs = QTabWidget()
        self.tabs_source = tabs

        # Tab USB
        tab_usb = QWidget()
        layout_usb = QVBoxLayout(tab_usb)
        
        self.combo_usb = QComboBox()
        btn_refresh_usb = QPushButton("🔄 Actualizar Dispositivos")
        btn_refresh_usb.clicked.connect(self._populate_usb_devices)
        
        self.btn_connect_usb = QPushButton("🔌 Conectar USB")
        self.btn_connect_usb.setStyleSheet("background-color: #008855; color: white;")
        self.btn_connect_usb.clicked.connect(self._toggle_connect_usb)

        layout_usb.addWidget(QLabel("Dispositivo USB (V4L2):"))
        layout_usb.addWidget(self.combo_usb)
        layout_usb.addWidget(btn_refresh_usb)
        layout_usb.addWidget(self.btn_connect_usb)
        tabs.addTab(tab_usb, "🔌 Modo USB")

        # Tab WiFi
        tab_wifi = QWidget()
        layout_wifi = QVBoxLayout(tab_wifi)

        self.combo_wifi_presets = QComboBox()
        self.combo_wifi_presets.currentIndexChanged.connect(self._on_preset_selected)

        self.txt_wifi_url = QLineEdit()
        self.txt_wifi_url.setPlaceholderText("http://192.168.29.1:8080/?action=stream")

        btn_detect_gw = QPushButton("🌐 Autodetectar Gateway IP")
        btn_detect_gw.clicked.connect(self._detect_and_fill_gateway)

        self.btn_connect_wifi = QPushButton("📶 Conectar WiFi")
        self.btn_connect_wifi.setStyleSheet("background-color: #0066aa; color: white;")
        self.btn_connect_wifi.clicked.connect(self._toggle_connect_wifi)

        lbl_wifi_tip = QLabel(
            "<small style='color: #888888;'>"
            "<b>Instrucciones WiFi:</b><br>"
            "1. Cambia el microscopio a modo WiFi.<br>"
            "2. Conecta la laptop a la red del microscopio (ej. <i>Max-See_xxxx</i>).<br>"
            "3. Pulsa 'Autodetectar Gateway' y Conectar."
            "</small>"
        )
        lbl_wifi_tip.setWordWrap(True)

        layout_wifi.addWidget(QLabel("Preajuste de Transmisión:"))
        layout_wifi.addWidget(self.combo_wifi_presets)
        layout_wifi.addWidget(QLabel("URL del Stream:"))
        layout_wifi.addWidget(self.txt_wifi_url)
        layout_wifi.addWidget(btn_detect_gw)
        layout_wifi.addWidget(self.btn_connect_wifi)
        layout_wifi.addWidget(lbl_wifi_tip)
        tabs.addTab(tab_wifi, "📶 Modo WiFi")

        return tabs

    def _create_capture_group(self) -> QGroupBox:
        grp = QGroupBox("Herramientas de Captura")
        layout = QVBoxLayout(grp)

        # Trigger mode selector
        layout.addWidget(QLabel("Función del Botón / Atajo:"))
        self.combo_trigger_mode = QComboBox()
        self.combo_trigger_mode.addItem("📸 Captura de Foto (Snapshot)")
        self.combo_trigger_mode.addItem("🔴 Iniciar / Detener Grabación Video")
        self.combo_trigger_mode.currentIndexChanged.connect(self._sync_trigger_button)
        layout.addWidget(self.combo_trigger_mode)

        # Big unified quick trigger button
        self.btn_quick_trigger = QPushButton("⚡ DISPARADOR [Espacio]")
        self.btn_quick_trigger.clicked.connect(self._on_trigger_action)
        layout.addWidget(self.btn_quick_trigger)

        # Direct individual buttons
        h_direct = QHBoxLayout()
        btn_snapshot = QPushButton("📸 Foto")
        btn_snapshot.clicked.connect(self._take_snapshot)

        self.btn_record = QPushButton("🔴 Grabar MP4")
        self.btn_record.clicked.connect(self._toggle_recording)

        h_direct.addWidget(btn_snapshot)
        h_direct.addWidget(self.btn_record)
        layout.addLayout(h_direct)

        # Secondary tools
        h_tools = QHBoxLayout()
        self.btn_freeze = QPushButton("❄ Congelar")
        self.btn_freeze.clicked.connect(self._toggle_freeze)

        btn_gallery = QPushButton("📁 Galería")
        btn_gallery.clicked.connect(self._open_gallery)

        h_tools.addWidget(self.btn_freeze)
        h_tools.addWidget(btn_gallery)
        layout.addLayout(h_tools)

        self._record_mins = 0
        self._record_secs = 0
        self._sync_trigger_button()

        return grp

    def _create_zoom_group(self) -> QGroupBox:
        grp = QGroupBox("Zoom Digital & Encuadre")
        layout = QVBoxLayout(grp)

        h_zoom = QHBoxLayout()
        self.lbl_zoom = QLabel("1.0x")
        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setRange(10, 50)  # 1.0x to 5.0x
        self.slider_zoom.setValue(10)
        self.slider_zoom.valueChanged.connect(self._on_zoom_slider_changed)

        btn_reset_zoom = QPushButton("Restablecer")
        btn_reset_zoom.clicked.connect(self._reset_zoom)

        h_zoom.addWidget(self.slider_zoom)
        h_zoom.addWidget(self.lbl_zoom)

        layout.addLayout(h_zoom)
        layout.addWidget(btn_reset_zoom)
        
        lbl_hint = QLabel("<small style='color: #777777;'>Rueda de ratón para zoom, arrastrar para mover.</small>")
        layout.addWidget(lbl_hint)
        return grp

    def _create_filter_group(self) -> QGroupBox:
        grp = QGroupBox("Mejora de Imagen en Tiempo Real")
        layout = QVBoxLayout(grp)

        # Brightness
        layout.addWidget(QLabel("Brillo:"))
        self.slider_brightness = QSlider(Qt.Orientation.Horizontal)
        self.slider_brightness.setRange(-100, 100)
        self.slider_brightness.setValue(0)
        self.slider_brightness.valueChanged.connect(self._on_filter_changed)
        layout.addWidget(self.slider_brightness)

        # Contrast
        layout.addWidget(QLabel("Contraste:"))
        self.slider_contrast = QSlider(Qt.Orientation.Horizontal)
        self.slider_contrast.setRange(5, 30) # 0.5 to 3.0
        self.slider_contrast.setValue(10)    # 1.0
        self.slider_contrast.valueChanged.connect(self._on_filter_changed)
        layout.addWidget(self.slider_contrast)

        # Sharpness / Edge Enhancement (Unsharp Mask)
        h_sharp = QHBoxLayout()
        self.chk_sharpness = QCheckBox("Realce de Nitidez (PCB / Micro)")
        self.chk_sharpness.toggled.connect(self._on_filter_changed)
        self.slider_sharpness = QSlider(Qt.Orientation.Horizontal)
        self.slider_sharpness.setRange(1, 5)
        self.slider_sharpness.setValue(2)
        self.slider_sharpness.valueChanged.connect(self._on_filter_changed)
        layout.addWidget(self.chk_sharpness)
        layout.addWidget(self.slider_sharpness)

        # Color Mode
        layout.addWidget(QLabel("Modo de Color:"))
        self.combo_color_mode = QComboBox()
        self.combo_color_mode.addItems(["Normal", "Grayscale", "Invert"])
        self.combo_color_mode.currentIndexChanged.connect(self._on_filter_changed)
        layout.addWidget(self.combo_color_mode)

        # Flips
        h_flips = QHBoxLayout()
        self.chk_flip_h = QCheckBox("Espejo Horiz.")
        self.chk_flip_v = QCheckBox("Invertir Vert.")
        self.chk_flip_h.toggled.connect(self._on_filter_changed)
        self.chk_flip_v.toggled.connect(self._on_filter_changed)
        h_flips.addWidget(self.chk_flip_h)
        h_flips.addWidget(self.chk_flip_v)
        layout.addLayout(h_flips)

        btn_reset_filters = QPushButton("Restablecer Filtros")
        btn_reset_filters.clicked.connect(self._reset_filters)
        layout.addWidget(btn_reset_filters)

        return grp

    def _create_overlay_group(self) -> QGroupBox:
        grp = QGroupBox("Retículas y Medición")
        layout = QVBoxLayout(grp)

        self.chk_crosshair = QCheckBox("Retícula Central (Crosshair)")
        self.chk_crosshair.setChecked(True)
        self.chk_crosshair.toggled.connect(self._on_overlay_changed)
        layout.addWidget(self.chk_crosshair)

        self.chk_grid = QCheckBox("Cuadrícula de Medición (Grid)")
        self.chk_grid.toggled.connect(self._on_overlay_changed)
        layout.addWidget(self.chk_grid)

        # Grid spacing slider
        h_grid = QHBoxLayout()
        h_grid.addWidget(QLabel("Espaciado:"))
        self.slider_grid = QSlider(Qt.Orientation.Horizontal)
        self.slider_grid.setRange(20, 150)
        self.slider_grid.setValue(50)
        self.slider_grid.valueChanged.connect(self._on_overlay_changed)
        h_grid.addWidget(self.slider_grid)
        layout.addLayout(h_grid)

        self.chk_circles = QCheckBox("Círculos Concéntricos")
        self.chk_circles.toggled.connect(self._on_overlay_changed)
        layout.addWidget(self.chk_circles)

        # Color picker
        layout.addWidget(QLabel("Color de Guías:"))
        self.combo_color = QComboBox()
        self.combo_color.addItem("Verde Neón", "#00FF66")
        self.combo_color.addItem("Cian Eléctrico", "#00E5FF")
        self.combo_color.addItem("Rojo Alerta", "#FF3366")
        self.combo_color.addItem("Amarillo Ámbar", "#FFD600")
        self.combo_color.addItem("Blanco", "#FFFFFF")
        self.combo_color.currentIndexChanged.connect(self._on_color_changed)
        layout.addWidget(self.combo_color)

        return grp

    # --- Actions and Event Handlers ---
    def _populate_usb_devices(self):
        self.combo_usb.clear()
        cams = list_usb_cameras()
        if not cams:
            self.combo_usb.addItem("No se detectaron cámaras USB", "")
            return

        for cam in cams:
            self.combo_usb.addItem(cam["label"], cam["path"])

    def _populate_wifi_presets(self):
        self.combo_wifi_presets.clear()
        presets = get_wifi_presets()
        for p in presets:
            self.combo_wifi_presets.addItem(p["name"], p["url"])
        if presets and hasattr(self, "txt_wifi_url"):
            self.txt_wifi_url.setText(presets[0]["url"])

    def _auto_connect_usb(self):
        """Attempts to auto-connect to USB camera, or auto-connects to WiFi microscope if reachable."""
        connected_usb = False
        for i in range(self.combo_usb.count()):
            text = self.combo_usb.itemText(i)
            if "GENERAL" in text or "808" in text or "/dev/video0" in text:
                self.combo_usb.setCurrentIndex(i)
                self._toggle_connect_usb()
                connected_usb = True
                break

        if not connected_usb:
            # Check if WiFi microscope (JoyHonest/MS5B at 192.168.29.1) is reachable
            from stream_discovery import is_microscope_reachable
            if is_microscope_reachable("192.168.29.1"):
                if hasattr(self, "tabs_source"):
                    self.tabs_source.setCurrentIndex(1)
                self._toggle_connect_wifi()

    def _on_preset_selected(self, index: int):
        url = self.combo_wifi_presets.currentData()
        if url:
            self.txt_wifi_url.setText(url)

    def _detect_and_fill_gateway(self):
        gw = get_default_gateway()
        if gw:
            self.txt_wifi_url.setText(f"http://{gw}:8080/?action=stream")
            self.status_bar.showMessage(f"Gateway detectada: {gw}", 4000)
        else:
            QMessageBox.information(
                self,
                "Búsqueda de Gateway",
                "No se detectó una puerta de enlace activa.\n"
                "Asegúrate de estar conectado a la red WiFi del microscopio."
            )

    def _toggle_connect_usb(self):
        if self.is_connected:
            self._disconnect()
            self.btn_connect_usb.setText("🔌 Conectar USB")
            self.btn_connect_usb.setStyleSheet("background-color: #008855; color: white;")
        else:
            dev = self.combo_usb.currentData()
            if not dev:
                QMessageBox.warning(self, "Dispositivo no seleccionado", "Selecciona una cámara USB válida.")
                return
            self.capture_thread.configure_usb(dev)
            self.capture_thread.start()
            self.is_connected = True
            self.btn_connect_usb.setText("⏹ Desconectar")
            self.btn_connect_usb.setStyleSheet("background-color: #bb2222; color: white;")

    def _toggle_connect_wifi(self):
        if self.is_connected:
            self._disconnect()
            self.btn_connect_wifi.setText("📶 Conectar WiFi")
            self.btn_connect_wifi.setStyleSheet("background-color: #0066aa; color: white;")
        else:
            url = self.txt_wifi_url.text().strip()
            if not url:
                QMessageBox.warning(self, "URL Requerida", "Ingresa una URL de stream WiFi válida.")
                return
            self.capture_thread.configure_wifi(url)
            self.capture_thread.start()
            self.is_connected = True
            self.btn_connect_wifi.setText("⏹ Desconectar")
            self.btn_connect_wifi.setStyleSheet("background-color: #bb2222; color: white;")

    def _disconnect(self):
        if self.is_recording:
            self._toggle_recording()
        self.capture_thread.stop()
        self.is_connected = False
        self.lbl_conn_status.setText("🔴 Desconectado")
        self.lbl_fps.setText("FPS: 0.0")

    def _on_frame_ready(self, frame: np.ndarray, fps: float):
        self.viewport.update_frame(frame)
        self.lbl_fps.setText(f"FPS: {fps:.1f}")
        h, w = frame.shape[:2]
        self.lbl_resolution.setText(f"Res: {w}x{h}")

    def _on_status_changed(self, connected: bool, message: str):
        if connected:
            self.lbl_conn_status.setText("🟢 " + message)
        else:
            self.lbl_conn_status.setText("🔴 " + message)

    def _on_error(self, err_msg: str):
        self.status_bar.showMessage(f"Error: {err_msg}", 5000)

    def _on_trigger_action(self):
        """Executes the action currently selected in the trigger mode dropdown."""
        mode = self.combo_trigger_mode.currentText()
        if "Foto" in mode:
            self._take_snapshot()
        else:
            self._toggle_recording()

    def _sync_trigger_button(self):
        """Updates quick trigger button appearance based on current mode and recording state."""
        if not hasattr(self, "btn_quick_trigger") or not hasattr(self, "combo_trigger_mode"):
            return
        mode = self.combo_trigger_mode.currentText()
        if self.is_recording:
            self.btn_quick_trigger.setText(f"⏹ DETENER GRABACIÓN [{self._record_mins:02d}:{self._record_secs:02d}] [Espacio]")
            self.btn_quick_trigger.setStyleSheet("font-size: 13px; padding: 10px; background-color: #cc1111; color: white; font-weight: bold; border: 2px solid #ff5555;")
        elif "Foto" in mode:
            self.btn_quick_trigger.setText("📸 CAPTURAR FOTO [Espacio]")
            self.btn_quick_trigger.setStyleSheet("font-size: 13px; padding: 10px; background-color: #007799; color: white; font-weight: bold;")
        else:
            self.btn_quick_trigger.setText("🔴 INICIAR GRABACIÓN [Espacio]")
            self.btn_quick_trigger.setStyleSheet("font-size: 13px; padding: 10px; background-color: #aa2222; color: white; font-weight: bold;")

    def _take_snapshot(self):
        if not self.is_connected:
            self.status_bar.showMessage("Conecta una fuente antes de capturar fotos.", 3000)
            return
        self.viewport.trigger_shutter_flash()
        self.capture_thread.request_snapshot(self.save_directory)

    def _on_hardware_button_pressed(self, action: str):
        self.viewport.trigger_shutter_flash()
        self.status_bar.showMessage("📸 Disparo detectado desde botón físico del microscopio", 4000)

    def _on_snapshot_saved(self, path: str):
        self.status_bar.showMessage(f"📸 Foto guardada en: {os.path.basename(path)}", 5000)

    def _toggle_recording(self):
        if not self.is_connected:
            self.status_bar.showMessage("Conecta una fuente antes de grabar.", 3000)
            return

        if not self.is_recording:
            self.capture_thread.start_recording(self.save_directory)
            self.is_recording = True
            self._record_mins = 0
            self._record_secs = 0
            self.btn_record.setText("⏹ Detener [00:00]")
            self.btn_record.setStyleSheet("background-color: #cc1111; color: white; font-weight: bold;")
            self._sync_trigger_button()
        else:
            self.capture_thread.stop_recording()
            self.is_recording = False
            self.btn_record.setText("🔴 Grabar MP4")
            self.btn_record.setStyleSheet("font-size: 13px; padding: 8px;")
            self._sync_trigger_button()
            self.status_bar.showMessage("Video guardado en Galería.", 4000)

    def _on_recording_tick(self, elapsed: int, filename: str):
        self._record_mins = elapsed // 60
        self._record_secs = elapsed % 60
        self.btn_record.setText(f"⏹ Detener [{self._record_mins:02d}:{self._record_secs:02d}]")
        self._sync_trigger_button()

    def _toggle_freeze(self):
        frozen = self.viewport.toggle_freeze()
        if frozen:
            self.btn_freeze.setText("▶ Reanudar")
            self.btn_freeze.setStyleSheet("background-color: #FFCC00; color: black; font-weight: bold;")
        else:
            self.btn_freeze.setText("❄ Congelar")
            self.btn_freeze.setStyleSheet("")

    def _open_gallery(self):
        try:
            subprocess.Popen(["xdg-open", self.save_directory])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir la galería: {e}")

    # --- Zoom / Overlay / Filter Sync ---
    def _on_zoom_slider_changed(self, value: int):
        factor = value / 10.0
        self.lbl_zoom.setText(f"{factor:.1f}x")
        self.viewport.set_zoom(factor)

    def sync_zoom_slider(self, factor: float):
        self.slider_zoom.blockSignals(True)
        self.slider_zoom.setValue(int(round(factor * 10)))
        self.lbl_zoom.setText(f"{factor:.1f}x")
        self.slider_zoom.blockSignals(False)

    def _reset_zoom(self):
        self.slider_zoom.setValue(10)
        self.viewport.reset_zoom_pan()

    def _on_filter_changed(self):
        self.viewport.brightness = self.slider_brightness.value()
        self.viewport.contrast = self.slider_contrast.value() / 10.0
        self.viewport.sharpness = self.slider_sharpness.value() if self.chk_sharpness.isChecked() else 0
        self.viewport.color_mode = self.combo_color_mode.currentText()
        self.viewport.flip_h = self.chk_flip_h.isChecked()
        self.viewport.flip_v = self.chk_flip_v.isChecked()
        self.viewport._process_and_redraw()

    def _reset_filters(self):
        self.slider_brightness.setValue(0)
        self.slider_contrast.setValue(10)
        self.chk_sharpness.setChecked(False)
        self.slider_sharpness.setValue(2)
        self.combo_color_mode.setCurrentIndex(0)
        self.chk_flip_h.setChecked(False)
        self.chk_flip_v.setChecked(False)
        self._on_filter_changed()

    def _on_overlay_changed(self):
        self.viewport.show_crosshair = self.chk_crosshair.isChecked()
        self.viewport.show_grid = self.chk_grid.isChecked()
        self.viewport.grid_spacing = self.slider_grid.value()
        self.viewport.show_circles = self.chk_circles.isChecked()
        self.viewport.update()

    def _on_color_changed(self, index: int):
        hex_col = self.combo_color.currentData()
        if hex_col:
            self.viewport.set_overlay_color(hex_col)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Space:
            self._on_trigger_action()
        elif event.key() == Qt.Key.Key_S:
            self._take_snapshot()
        elif event.key() == Qt.Key.Key_R:
            self._toggle_recording()
        elif event.key() == Qt.Key.Key_C:
            self._toggle_freeze()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self._disconnect()
        event.accept()
