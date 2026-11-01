"""
Robo Island — Unified Apple iPhone 14/15 Dynamic Island + NotchNook Control Center
- Delicate, compact, and sleek ("kibar ve küçük")
- Elastic spring physics with Apple-style bounce & elasticity
- Live Digital Clock & Date
- Precision Wayland LayerShell hit-testing (clicking the notch directly opens panel!)
- 100% Responsive, perfectly aligned media controls (Play/Pause, Prev, Next with hover glow)
- Expanded Quick Shortcut Grid: Wi-Fi, Bluetooth, Night Light, Performance/GameMode
- Connected Devices: KDE Connect Phone battery & Bluetooth Earbuds battery ring
- Live Spotify track progress bar, album art, and controls
- Hardware telemetry: CPU, RAM, Volume slider
- System notifications route through the Dynamic Island with spring dropdown
- Meta+Space integration: liquid notch bloom animation!
"""
import os
import re
import subprocess
import ctypes
import time
import math
import shiboken6
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont,
                            QPixmap, QGuiApplication, QLinearGradient, QCursor, QPainterPath)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF

from graphics.ash_particles import AshCoverCanvas
from ui.visualizer import MiniVisualizer
from ui.robo_face import RoboFace
from backend.device_battery import DeviceBatteryWatcher
from backend.notification_watcher import NotificationWatcher
from backend.network_manager import NetworkManager

LIB_LAYERSHELL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "liblayershell_helper.so"
)

# ── Modes ─────────────────────────────────────────────────────────────────────
MODE_IDLE            = 1   # Notch: Sleeping/idle Robo eyes + Clock badge
MODE_MUSIC_COMPACT   = 2   # Notch: Spotify track + dancing visualizer + Clock badge
MODE_MUSIC_EXPANDED  = 3   # Notch: Ash wind particle track change (4s)
MODE_TASK_RUNNING    = 4   # Notch: Active AI task (cyan spinning eyes)
MODE_TASK_DONE       = 5   # Notch: Task completed (green happy eyes)
MODE_TASK_WAITING    = 6   # Notch: Waiting for approval (amber alert eyes)
MODE_GREETING        = 7   # Notch: "Hi, I'm Robo!"
MODE_NOTIFICATION    = 8   # Notch: System Notification banner popup (4.5s)
MODE_ACCESSORY_POPUP = 9   # Notch: Bluetooth Headset connected card (4s)
MODE_QUICK_PANEL     = 10  # NotchNook Expanded Control Center!
MODE_NOTCH_BLOOM     = 11  # Meta+Space trigger: notch liquid bloom towards radial menu!
MODE_AIRDROP_HOVER   = 12  # File drag over notch (AirDrop dropzone)
MODE_AIRDROP_SENDING = 13  # Sending file to Galaxy S25 FE
MODE_AIRDROP_SUCCESS = 14  # Sent to Phone successfully ✓

MODE_DIMS = {
    MODE_IDLE:            (165,  34),
    MODE_MUSIC_COMPACT:   (235,  34),
    MODE_MUSIC_EXPANDED:  (420, 100),
    MODE_TASK_RUNNING:    (260,  38),
    MODE_TASK_DONE:       (260,  38),
    MODE_TASK_WAITING:    (280,  42),
    MODE_GREETING:        (190,  36),
    MODE_NOTIFICATION:    (390,  76),
    MODE_ACCESSORY_POPUP: (280, 130),
    MODE_QUICK_PANEL:     (475, 204),  # Sleek refined dual-card layout
    MODE_NOTCH_BLOOM:     (360,  68),  # Meta+Space liquid bloom out of notch
    MODE_AIRDROP_HOVER:   (360,  64),  # AirDrop drop zone
    MODE_AIRDROP_SENDING: (330,  56),
    MODE_AIRDROP_SUCCESS: (320,  52),
}

ACCENT       = QColor(146, 110, 228)        # #926ee4
ACCENT_LIGHT = QColor(180, 150, 250)        # #b496fa
ACCENT_CYAN  = QColor(0,   200, 255)
ACCENT_GREEN = QColor(29,  185,  84)
BG_NOTCH     = QColor(10,  10,  15,  252)   # Deep Apple Matte Black
BG_PANEL     = QColor(12,  11,  18,  252)


# ── Apple SF Symbols Style Vector Drawers ────────────────────────────────────

def draw_apple_wifi(p: QPainter, rect: QRectF, color: QColor):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx = rect.center().x()
    cy = rect.center().y() + 2.5
    # Arc 1 (Top)
    p.drawArc(QRectF(cx - 9.0, cy - 8.5, 18.0, 15.0), 45 * 16, 90 * 16)
    # Arc 2 (Middle)
    p.drawArc(QRectF(cx - 5.5, cy - 5.0, 11.0, 9.0), 45 * 16, 90 * 16)
    # Center dot
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawEllipse(QRectF(cx - 1.5, cy + 0.5, 3.0, 3.0))
    p.restore()

def draw_apple_bluetooth(p: QPainter, rect: QRectF, color: QColor):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx = rect.center().x()
    cy = rect.center().y()
    h = 8.5
    w = 5.0
    path = QPainterPath()
    path.moveTo(cx - w, cy - h * 0.55)
    path.lineTo(cx + w, cy + h * 0.55)
    path.lineTo(cx, cy + h)
    path.lineTo(cx, cy - h)
    path.lineTo(cx + w, cy - h * 0.55)
    path.lineTo(cx - w, cy + h * 0.55)
    p.drawPath(path)
    p.restore()

def draw_apple_moon(p: QPainter, rect: QRectF, color: QColor):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    cx = rect.center().x()
    cy = rect.center().y()
    r = 7.5
    crescent = QPainterPath()
    crescent.addEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
    sub = QPainterPath()
    sub.addEllipse(QRectF(cx - r * 0.35, cy - r * 1.05, r * 1.7, r * 1.7))
    path = crescent.subtracted(sub)
    p.drawPath(path)
    p.restore()

def draw_apple_bolt(p: QPainter, rect: QRectF, color: QColor):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    cx = rect.center().x()
    cy = rect.center().y()
    path = QPainterPath()
    path.moveTo(cx + 0.5, cy - 8.5)
    path.lineTo(cx - 5.5, cy + 0.5)
    path.lineTo(cx - 0.5, cy + 0.5)
    path.lineTo(cx - 1.5, cy + 8.5)
    path.lineTo(cx + 5.5, cy - 0.5)
    path.lineTo(cx + 0.5, cy - 0.5)
    path.closeSubpath()
    p.drawPath(path)
    p.restore()

def draw_apple_speaker(p: QPainter, rect: QRectF, color: QColor, is_muted: bool):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx = rect.center().x()
    cy = rect.center().y()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    path = QPainterPath()
    path.moveTo(cx - 6.5, cy - 3.0)
    path.lineTo(cx - 3.5, cy - 3.0)
    path.lineTo(cx + 0.5, cy - 6.5)
    path.lineTo(cx + 0.5, cy + 6.5)
    path.lineTo(cx - 3.5, cy + 3.0)
    path.lineTo(cx - 6.5, cy + 3.0)
    path.closeSubpath()
    p.drawPath(path)
    if is_muted:
        p.setPen(QPen(QColor(255, 77, 109), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(int(cx + 2.5), int(cy - 4.5), int(cx + 7.5), int(cy + 4.5))
    else:
        p.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(cx - 1.5, cy - 4.0, 8.0, 8.0), -60 * 16, 120 * 16)
        p.drawArc(QRectF(cx - 0.5, cy - 6.5, 13.0, 13.0), -60 * 16, 120 * 16)
    p.restore()

def draw_apple_camera(p: QPainter, rect: QRectF, color: QColor):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx = rect.center().x()
    cy = rect.center().y()
    p.drawRoundedRect(QRectF(cx - 7.5, cy - 4.5, 15.0, 11.5), 2.5, 2.5)
    p.drawEllipse(QRectF(cx - 3.2, cy - 1.2, 6.4, 6.4))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawRoundedRect(QRectF(cx - 3.0, cy - 6.8, 6.0, 2.5), 1.0, 1.0)
    p.restore()


class DynamicIsland(QWidget):
    """Unified Dynamic Island & NotchNook Control Center."""

    def __init__(self, target_screen_name: str = "HDMI-A-1", parent=None):
        super().__init__(parent)
        self.target_screen_name = target_screen_name

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self._airdrop_filename = ""

        # Canvas bounds
        self.canvas_width  = 540
        self.canvas_height = 260
        self.setFixedSize(self.canvas_width, self.canvas_height)

        # ── Elastic Spring Physics State ──────────────────────────────────
        self._pill_width   = 0.0
        self._pill_height  = 0.0
        self._vel_w        = 0.0
        self._vel_h        = 0.0
        self.target_width  = 0.0
        self.target_height = 0.0
        self.current_mode  = MODE_IDLE

        # ── Mouse & Hover State ───────────────────────────────────────────
        self._hover_pos = QPointF(-100, -100)
        self.hovered_btn = ""
        self._is_dragging_volume = False

        # ── Spotify State ─────────────────────────────────────────────────
        self.title_text  = ""
        self.artist_text = ""
        self.album_text  = ""
        self.is_playing  = False
        self.cover_pixmap: QPixmap | None = None
        self.mini_cover_pixmap: QPixmap | None = None
        self.song_pos_s  = 0
        self.song_len_s  = 0
        self.song_ratio  = 0.0

        # ── System Telemetry & Devices ────────────────────────────────────
        self.system_volume = 50
        self.is_muted = False
        self.night_light_on = False
        self.gamemode_on = False

        # Notification state
        self.notif_app   = ""
        self.notif_title = ""
        self.notif_body  = ""

        # Accessory state
        self.acc_name = ""
        self.acc_battery = -1

        # Phone battery (KDE Connect)
        self.phone_name = "Galaxy S25 FE"
        self.phone_charge = -1
        self.phone_charging = False

        # Headset battery (Bluetooth)
        self.headset_name = ""
        self.headset_battery = -1

        # Wi-Fi & HW
        self.wifi_enabled = True
        self.connected_ssid = ""
        self.cpu_usage = 0
        self.ram_usage = 0

        # Task state
        self._task_label = ""
        self._task_dots  = 0

        # ── Sub-widgets ───────────────────────────────────────────────────
        self.cover_canvas = AshCoverCanvas(size=76, parent=self)
        self.cover_canvas.setGeometry(16, 12, 136, 76)
        self.cover_canvas.hide()

        self.visualizer = MiniVisualizer(bars_count=4, bar_color=ACCENT_GREEN, parent=self)
        self.visualizer.hide()

        self.robo = RoboFace()

        # ── Managers ──────────────────────────────────────────────────────
        self.battery_watcher = DeviceBatteryWatcher(self)
        self.battery_watcher.battery_updated.connect(self._on_battery_updated)
        self.battery_watcher.device_connected.connect(self._on_accessory_connected)

        self.notif_watcher = NotificationWatcher(self)
        self.notif_watcher.notification_received.connect(self._on_notification)
        self.notif_watcher.start()

        self.net_manager = NetworkManager(self)
        self.net_manager.telemetry_updated.connect(self._on_telemetry_updated)

        # ── Timers ────────────────────────────────────────────────────────
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(7)
        self.anim_timer.timeout.connect(self._step_dimensions)
        self.anim_timer.start()

        self.robo_timer = QTimer(self)
        self.robo_timer.setInterval(16)
        self.robo_timer.timeout.connect(self.update)
        self.robo_timer.start()

        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.setInterval(4000)
        self.collapse_timer.timeout.connect(self._on_collapse_timeout)

        self.notif_timer = QTimer(self)
        self.notif_timer.setSingleShot(True)
        self.notif_timer.setInterval(4500)
        self.notif_timer.timeout.connect(self._on_collapse_timeout)

        self.acc_timer = QTimer(self)
        self.acc_timer.setSingleShot(True)
        self.acc_timer.setInterval(4000)
        self.acc_timer.timeout.connect(self._on_collapse_timeout)

        # Audio & Progress sync timer (every 800ms)
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(800)
        self.sync_timer.timeout.connect(self._sync_audio_telemetry)
        self.sync_timer.start()

        # LayerShell Setup
        self.update_screen_position(target_screen_name)
        self.show()

        # Initial precision input region
        self._update_input_region()

        # Initial greeting
        QTimer.singleShot(800, self._show_greeting)

    # ── Precision Wayland LayerShell Hit-Testing ──────────────────────────────

    def _setup_layershell(self, target_screen):
        try:
            if not os.path.exists(LIB_LAYERSHELL_PATH):
                return False
            self.winId()
            wh = self.windowHandle()
            if not wh:
                return False
            lib = ctypes.CDLL(LIB_LAYERSHELL_PATH)
            lib.setup_layershell_window.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int
            ]
            lib.setup_layershell_window.restype = ctypes.c_bool
            ptr_wh = shiboken6.getCppPointer(wh)[0]
            ptr_sc = shiboken6.getCppPointer(target_screen)[0] if target_screen else 0
            return lib.setup_layershell_window(ptr_wh, ptr_sc, self.canvas_width, self.canvas_height, 1, 0)
        except Exception:
            return False

    def _update_input_region(self):
        try:
            if not os.path.exists(LIB_LAYERSHELL_PATH):
                return
            wh = self.windowHandle()
            if not wh:
                return
            lib = ctypes.CDLL(LIB_LAYERSHELL_PATH)
            lib.set_input_rect.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            lib.set_input_rect.restype = ctypes.c_bool

            cx = self.width() / 2.0
            x = int(cx - (self._pill_width / 2.0))
            w = int(self._pill_width)
            h = int(self._pill_height)

            ptr_wh = shiboken6.getCppPointer(wh)[0]
            lib.set_input_rect(ptr_wh, x, 0, w, h)
        except Exception:
            pass

    def set_target_screen(self, screen_name: str):
        if screen_name != self.target_screen_name:
            self.target_screen_name = screen_name
            self.update_screen_position(screen_name)

    def update_screen_position(self, screen_name: str):
        target_screen = None
        for s in QGuiApplication.screens():
            if s.name() == screen_name:
                target_screen = s
                break
        if not target_screen:
            target_screen = QGuiApplication.primaryScreen()

        success = self._setup_layershell(target_screen)
        if not success and target_screen:
            geo = target_screen.geometry()
            x = geo.x() + (geo.width() - self.canvas_width) // 2
            y = geo.y()
            self.move(x, y)

    # ── Notification & Accessory Callbacks ────────────────────────────────────

    def _on_notification(self, app_name, summary, body, icon):
        self.notif_app   = app_name
        self.notif_title = summary
        self.notif_body  = body

        if self.current_mode == MODE_QUICK_PANEL:
            return

        self.set_mode(MODE_NOTIFICATION)
        self.notif_timer.start()

    def _on_accessory_connected(self, dev_name, battery_pct):
        self.acc_name = dev_name
        self.acc_battery = battery_pct

        if self.current_mode == MODE_QUICK_PANEL:
            return

        self.set_mode(MODE_ACCESSORY_POPUP)
        self.acc_timer.start()

    def _on_battery_updated(self, data):
        phone = data.get("phone", {})
        headset = data.get("headset", {})

        self.phone_name = phone.get("name", "Telefon")
        self.phone_charge = phone.get("charge", -1)
        self.phone_charging = phone.get("is_charging", False)

        self.headset_name = headset.get("name", "")
        self.headset_battery = headset.get("battery", -1)
        self.update()

    def _on_telemetry_updated(self, data):
        self.cpu_usage = data.get("cpu", 0)
        self.ram_usage = data.get("ram", 0)
        self.wifi_enabled = data.get("wifi_enabled", True)
        self.connected_ssid = data.get("connected_ssid", "")
        self.update()

    def _sync_audio_telemetry(self):
        # 1. Volume & Mute
        try:
            res = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], capture_output=True, text=True, timeout=0.2)
            m = re.search(r'(\d+)%', res.stdout)
            if m:
                self.system_volume = int(m.group(1))
            res_mute = subprocess.run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"], capture_output=True, text=True, timeout=0.2)
            self.is_muted = ("yes" in res_mute.stdout.lower())
        except Exception:
            pass

        # 2. Spotify Track Progress
        if self.is_playing:
            try:
                p_out = subprocess.run(
                    ["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2",
                     "org.freedesktop.DBus.Properties.Get", "org.mpris.MediaPlayer2.Player", "Position"],
                    capture_output=True, text=True, timeout=0.2
                ).stdout.strip()
                if p_out.isdigit():
                    self.song_pos_s = int(p_out) // 1000000
                    if self.song_len_s > 0:
                        self.song_ratio = min(1.0, max(0.0, self.song_pos_s / float(self.song_len_s)))
            except Exception:
                pass

    # ── Meta+Space Bloom Interaction ──────────────────────────────────────────

    def trigger_notch_bloom_open(self):
        """Called when Meta+Space is pressed — notch blooms down like liquid glass!"""
        if self.current_mode == MODE_QUICK_PANEL:
            return
        self.set_mode(MODE_NOTCH_BLOOM)
        self.update()

    def trigger_notch_bloom_close(self):
        """Called when BeamRadial closes — notch retreats back into the bar."""
        if self.current_mode == MODE_NOTCH_BLOOM:
            self._on_collapse_timeout()

    def trigger_notch_bloom(self):
        """Toggle or temporary bloom."""
        if self.current_mode == MODE_NOTCH_BLOOM:
            self.trigger_notch_bloom_close()
        else:
            self.trigger_notch_bloom_open()
            QTimer.singleShot(600, self.trigger_notch_bloom_close)

    # ── Hotkey / Quick Control Center Toggle ──────────────────────────────────

    def toggle_quick_panel(self):
        if self.current_mode == MODE_QUICK_PANEL:
            self.close_quick_panel()
        else:
            self.open_quick_panel()

    def open_quick_panel(self):
        self._sync_audio_telemetry()
        self.set_mode(MODE_QUICK_PANEL)
        self.update()

    def close_quick_panel(self):
        if self.is_playing:
            self.set_mode(MODE_MUSIC_COMPACT)
        else:
            self._enter_idle()
        self.update()

    # ── Spotify Callbacks ─────────────────────────────────────────────────────

    def on_playback_status(self, status: str):
        self.is_playing = (status == "Playing")
        self.visualizer.set_playing(self.is_playing)

        if self.current_mode in (MODE_QUICK_PANEL, MODE_NOTIFICATION, MODE_ACCESSORY_POPUP):
            self.update()
            return

        if not self.is_playing:
            self._enter_idle()
        else:
            self.set_mode(MODE_MUSIC_COMPACT)

    def on_track_changed(self, track_info: dict):
        self.title_text  = track_info.get("title",  "")
        self.artist_text = track_info.get("artist", "")
        self.album_text  = track_info.get("album",  "")
        cover_path       = track_info.get("cover_path", "")

        new_pixmap = QPixmap()
        if cover_path and os.path.exists(cover_path):
            new_pixmap.load(cover_path)
            self.cover_pixmap = new_pixmap
            self.mini_cover_pixmap = new_pixmap.scaled(
                20, 20, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
            )
        else:
            self.cover_pixmap = None
            self.mini_cover_pixmap = None

        # Fetch track length
        try:
            meta = subprocess.run(
                ["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2",
                 "org.freedesktop.DBus.Properties.Get", "org.mpris.MediaPlayer2.Player", "Metadata"],
                capture_output=True, text=True, timeout=0.3
            ).stdout
            m = re.search(r'mpris:length:\s*(\d+)', meta)
            if m:
                self.song_len_s = int(m.group(1)) // 1000000
        except Exception:
            self.song_len_s = 0

        if not new_pixmap.isNull():
            self.cover_canvas.transition_to(new_pixmap)

        if self.current_mode in (MODE_QUICK_PANEL, MODE_NOTIFICATION, MODE_ACCESSORY_POPUP):
            self.update()
            return

        self.set_mode(MODE_MUSIC_EXPANDED)
        self.collapse_timer.start()

    # ── Task Callbacks ────────────────────────────────────────────────────────

    def on_task_started(self, message: str):
        self._task_label = message
        if self.current_mode != MODE_QUICK_PANEL:
            self.set_mode(MODE_TASK_RUNNING)

    def on_task_done(self, message: str):
        self._task_label = message
        if self.current_mode != MODE_QUICK_PANEL:
            self.set_mode(MODE_TASK_DONE)
            QTimer.singleShot(3500, self._on_collapse_timeout)

    def on_task_waiting(self, message: str):
        self._task_label = message
        if self.current_mode != MODE_QUICK_PANEL:
            self.set_mode(MODE_TASK_WAITING)

    def on_task_cancelled(self):
        self._task_label = ""
        if self.current_mode != MODE_QUICK_PANEL:
            self._enter_idle()

    # ── Mode Transitions ──────────────────────────────────────────────────────

    def set_mode(self, mode: int):
        self.current_mode = mode
        tw, th = MODE_DIMS.get(mode, (165, 34))
        self.target_width  = float(tw)
        self.target_height = float(th)

        if mode == MODE_IDLE:
            self.robo.set_state("idle")
        elif mode == MODE_TASK_RUNNING:
            self.robo.set_state("active")
        elif mode in (MODE_TASK_DONE, MODE_GREETING, MODE_QUICK_PANEL, MODE_NOTCH_BLOOM):
            self.robo.set_state("happy")
        elif mode == MODE_TASK_WAITING:
            self.robo.set_state("alert")

        self.cover_canvas.setVisible(mode == MODE_MUSIC_EXPANDED)
        self.visualizer.setVisible(mode in (MODE_MUSIC_COMPACT, MODE_MUSIC_EXPANDED))

        if not self.isVisible():
            self.show()

    def _enter_idle(self):
        self.robo.set_state("sleeping")
        self.set_mode(MODE_IDLE)

    def _show_greeting(self):
        self._task_label = "Hi, I'm Robo!"
        self.set_mode(MODE_GREETING)
        QTimer.singleShot(2400, self._after_greeting)

    def _after_greeting(self):
        self._task_label = ""
        if self.is_playing:
            self.set_mode(MODE_MUSIC_COMPACT)
        else:
            self._enter_idle()

    def _on_collapse_timeout(self):
        if self.current_mode == MODE_QUICK_PANEL:
            return
        if self.is_playing:
            self.set_mode(MODE_MUSIC_COMPACT)
        else:
            self._enter_idle()

    # ── Elastic Damped Spring Physics ─────────────────────────────────────────

    def _step_dimensions(self):
        stiffness = 0.22
        damping   = 0.72

        force_w = (self.target_width - self._pill_width) * stiffness
        self._vel_w = (self._vel_w + force_w) * damping
        self._pill_width += self._vel_w

        force_h = (self.target_height - self._pill_height) * stiffness
        self._vel_h = (self._vel_h + force_h) * damping
        self._pill_height += self._vel_h

        if abs(self._vel_w) > 0.05 or abs(self._vel_h) > 0.05:
            self._update_input_region()

    # ── Precision Geometry Calculations for Controls ─────────────────────────

    def _get_panel_rects(self):
        """Single source of truth for exact button and tile geometries!"""
        cx = self.width() / 2.0
        x  = cx - (self._pill_width / 2.0)
        y  = 0.0
        w  = self._pill_width
        h  = self._pill_height

        card_y = y + 36
        card_h = 156
        t1_w   = 268

        # Close button [✕]
        close_btn = QRectF(x + w - 32, y + 8, 24, 24)

        # Media controls row centered in Tile 1
        btn_y = card_y + 100
        t1_cx = x + 14 + t1_w / 2.0
        
        # Symmetrical, spacious hitboxes
        play_rect = QRectF(t1_cx - 24, btn_y - 4, 48, 48)
        prev_rect = QRectF(t1_cx - 24 - 56, btn_y - 1, 44, 42)
        next_rect = QRectF(t1_cx + 24 + 12, btn_y - 1, 44, 42)

        # Seek bar
        seek_rect = QRectF(x + 24, card_y + 74, t1_w - 20, 18)

        # System Hub Tile (t2)
        t2_x = x + 14 + t1_w + 10
        t2_w = w - t1_w - 38

        # Volume slider
        vol_rect = QRectF(t2_x + 12, card_y + 58, t2_w - 24, 18)

        # Quick Shortcut Buttons (3x2 Grid for rich controls)
        grid_y = card_y + 84
        btn_bw = (t2_w - 24 - 8) / 3.0
        btn_bh = 28

        btn_wifi = QRectF(t2_x + 12,                 grid_y,              btn_bw, btn_bh)
        btn_bt   = QRectF(t2_x + 12 + btn_bw + 4,     grid_y,              btn_bw, btn_bh)
        btn_nl   = QRectF(t2_x + 12 + (btn_bw + 4)*2, grid_y,              btn_bw, btn_bh)
        btn_game = QRectF(t2_x + 12,                 grid_y + btn_bh + 4, btn_bw, btn_bh)
        btn_mute = QRectF(t2_x + 12 + btn_bw + 4,     grid_y + btn_bh + 4, btn_bw, btn_bh)
        btn_shot = QRectF(t2_x + 12 + (btn_bw + 4)*2, grid_y + btn_bh + 4, btn_bw, btn_bh)

        return {
            "x": x, "y": y, "w": w, "h": h,
            "card_y": card_y, "card_h": card_h, "t1_w": t1_w,
            "t2_x": t2_x, "t2_w": t2_w,
            "close_btn": close_btn,
            "play_rect": play_rect,
            "prev_rect": prev_rect,
            "next_rect": next_rect,
            "seek_rect": seek_rect,
            "vol_rect": vol_rect,
            "btn_wifi": btn_wifi,
            "btn_bt": btn_bt,
            "btn_nl": btn_nl,
            "btn_game": btn_game,
            "btn_mute": btn_mute,
            "btn_shot": btn_shot,
        }

    # ── Mouse Interaction ─────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        pos = event.position()
        cx = self.width() / 2.0
        x  = cx - self._pill_width / 2.0
        y  = 0.0
        w  = self._pill_width
        h  = self._pill_height

        # 1. Clicking on Notch while resting -> Instantly Open Quick Panel!
        if self.current_mode != MODE_QUICK_PANEL:
            pill_rect = QRectF(x, 0, w, h)
            if pill_rect.contains(pos):
                self.open_quick_panel()
                event.accept()
                return
            super().mousePressEvent(event)
            return

        # ── 2. Click Handling in Expanded NotchNook Panel ─────────────────
        R = self._get_panel_rects()

        # Close button [✕]
        if R["close_btn"].adjusted(-4, -4, 4, 4).contains(pos):
            self.close_quick_panel()
            event.accept()
            return

        # Play/Pause button (with ultra-generous hitbox!)
        if R["play_rect"].adjusted(-8, -8, 8, 8).contains(pos):
            subprocess.Popen(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.PlayPause"])
            self.is_playing = not self.is_playing
            self.update()
            event.accept()
            return

        # Previous (⏮) (with ultra-generous hitbox!)
        if R["prev_rect"].adjusted(-8, -8, 8, 8).contains(pos):
            subprocess.Popen(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Previous"])
            event.accept()
            return

        # Next (⏭) (with ultra-generous hitbox!)
        if R["next_rect"].adjusted(-8, -8, 8, 8).contains(pos):
            subprocess.Popen(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Next"])
            event.accept()
            return

        # Seek bar scrub
        if R["seek_rect"].adjusted(0, -6, 0, 6).contains(pos):
            if self.song_len_s > 0:
                norm = min(1.0, max(0.0, (pos.x() - R["seek_rect"].x()) / R["seek_rect"].width()))
                target_us = int(norm * self.song_len_s * 1000000)
                try:
                    subprocess.Popen(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.SetPosition", f"/org/mpris/MediaPlayer2/Track/{self.title_text}", str(target_us)])
                    self.song_pos_s = int(norm * self.song_len_s)
                    self.song_ratio = norm
                except Exception:
                    pass
            event.accept()
            self.update()
            return

        # Volume Slider drag/click
        if R["vol_rect"].adjusted(0, -8, 0, 8).contains(pos):
            self._is_dragging_volume = True
            norm = (pos.x() - (R["vol_rect"].x() + 20)) / (R["vol_rect"].width() - 40)
            self._set_volume(int(norm * 100))
            event.accept()
            return

        # Quick Shortcut 1: Wi-Fi
        if R["btn_wifi"].adjusted(-2, -2, 2, 2).contains(pos):
            self.net_manager.toggle_wifi()
            event.accept()
            self.update()
            return

        # Quick Shortcut 2: Bluetooth
        if R["btn_bt"].adjusted(-2, -2, 2, 2).contains(pos):
            self.net_manager.toggle_bluetooth()
            event.accept()
            self.update()
            return

        # Quick Shortcut 3: Night Light (🌙)
        if R["btn_nl"].adjusted(-2, -2, 2, 2).contains(pos):
            self._toggle_night_light()
            event.accept()
            self.update()
            return

        # Quick Shortcut 4: GameMode / Performance (⚡)
        if R["btn_game"].adjusted(-2, -2, 2, 2).contains(pos):
            self.gamemode_on = not self.gamemode_on
            status = "Aktif ⚡" if self.gamemode_on else "Pasif"
            subprocess.Popen(["notify-send", "-a", "RoboIsland", "Performans Modu", status])
            event.accept()
            self.update()
            return

        # Quick Shortcut 5: Mute Audio (🔇)
        if R["btn_mute"].adjusted(-2, -2, 2, 2).contains(pos):
            subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
            self.is_muted = not self.is_muted
            event.accept()
            self.update()
            return

        # Quick Shortcut 6: Screenshot (📸)
        if R["btn_shot"].adjusted(-2, -2, 2, 2).contains(pos):
            self.close_quick_panel()
            subprocess.Popen(["spectacle", "-r"])
            event.accept()
            return

        # Clicking outside card -> close
        panel_rect = QRectF(x, y, w, h)
        if not panel_rect.contains(pos):
            self.close_quick_panel()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._hover_pos = event.position()
        if self.current_mode == MODE_QUICK_PANEL:
            R = self._get_panel_rects()
            pos = self._hover_pos

            # Update hovered button for crisp visual glow
            if R["play_rect"].adjusted(-4, -4, 4, 4).contains(pos):
                self.hovered_btn = "play"
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            elif R["prev_rect"].adjusted(-4, -4, 4, 4).contains(pos):
                self.hovered_btn = "prev"
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            elif R["next_rect"].adjusted(-4, -4, 4, 4).contains(pos):
                self.hovered_btn = "next"
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            elif R["close_btn"].adjusted(-2, -2, 2, 2).contains(pos):
                self.hovered_btn = "close"
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            elif any(r.adjusted(-2, -2, 2, 2).contains(pos) for r in (
                R["btn_wifi"], R["btn_bt"], R["btn_nl"], R["btn_game"], R["btn_mute"], R["btn_shot"]
            )):
                self.hovered_btn = "shortcut"
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.hovered_btn = ""
                self.setCursor(Qt.CursorShape.ArrowCursor)

            if self._is_dragging_volume:
                norm = (pos.x() - (R["vol_rect"].x() + 20)) / (R["vol_rect"].width() - 40)
                self._set_volume(int(norm * 100))

        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_dragging_volume = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.current_mode == MODE_QUICK_PANEL:
                self.close_quick_panel()
                event.accept()
                return
        super().keyPressEvent(event)

    # ── AirDrop Drag & Drop into Dynamic Island ──────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            urls = event.mimeData().urls()
            if urls:
                self._airdrop_filename = os.path.basename(urls[0].toLocalFile()) if urls[0].isLocalFile() else "Dosya"
                if len(urls) > 1:
                    self._airdrop_filename += f" (+{len(urls)-1})"
            self.set_mode(MODE_AIRDROP_HOVER)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        if self.current_mode == MODE_AIRDROP_HOVER:
            self._on_collapse_timeout()
        event.accept()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self._send_files_via_airdrop(paths)
        else:
            event.ignore()

    def _send_files_via_airdrop(self, paths: list):
        self.set_mode(MODE_AIRDROP_SENDING)
        self.update()

        import threading
        def worker():
            for p in paths:
                subprocess.run(
                    ["kdeconnect-cli", "-d", "4bc4747eab4e42a7874f9c704ba4927f", "--share", p],
                    capture_output=True, timeout=15
                )
            QTimer.singleShot(400, self._on_airdrop_success)

        threading.Thread(target=worker, daemon=True).start()

    def _on_airdrop_success(self):
        self.robo.set_state("happy")
        self.set_mode(MODE_AIRDROP_SUCCESS)
        self.update()
        QTimer.singleShot(3500, self._on_collapse_timeout)

    def _set_volume(self, pct: int):
        pct = max(0, min(100, pct))
        self.system_volume = pct
        try:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"], timeout=0.2)
        except Exception:
            pass
        self.update()

    def _toggle_night_light(self):
        try:
            if self.night_light_on:
                subprocess.run(["qdbus6", "org.kde.KWin", "/org/kde/KWin/NightLight", "stopPreview"], timeout=0.3)
                self.night_light_on = False
            else:
                subprocess.run(["qdbus6", "org.kde.KWin", "/org/kde/KWin/NightLight", "preview", "4500"], timeout=0.3)
                self.night_light_on = True
        except Exception:
            pass
        self.update()

    # ── Paint Engine ──────────────────────────────────────────────────────────

    def paintEvent(self, event):
        if self._pill_width <= 2.0 or self._pill_height <= 2.0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2.0
        x  = cx - (self._pill_width / 2.0)
        y  = 0.0
        w  = self._pill_width
        h  = self._pill_height
        mode = self.current_mode

        radius = min(h / 2.0, 20.0)
        pill_rect = QRectF(x, y, w, h)

        if mode == MODE_QUICK_PANEL:
            # NotchNook Glass Card
            p.setPen(QPen(QColor(146, 110, 228, 120), 1.2))
            p.setBrush(QBrush(BG_PANEL))
            p.drawRoundedRect(pill_rect, 22, 22)
            self._paint_notchnook_panel(p, x, y, w, h)

        elif mode == MODE_NOTIFICATION:
            p.setPen(QPen(ACCENT_CYAN, 1.3))
            p.setBrush(QBrush(BG_NOTCH))
            p.drawRoundedRect(pill_rect, radius, radius)
            self._paint_notification(p, x, y, w, h)

        elif mode == MODE_ACCESSORY_POPUP:
            p.setPen(QPen(QColor(255, 255, 255, 60), 1.2))
            p.setBrush(QBrush(BG_NOTCH))
            p.drawRoundedRect(pill_rect, 20, 20)
            self._paint_accessory_popup(p, x, y, w, h)

        elif mode == MODE_AIRDROP_HOVER:
            # File drag over notch (AirDrop Drop Zone)
            p.setPen(QPen(ACCENT_CYAN, 1.8))
            p.setBrush(QBrush(BG_NOTCH))
            p.drawRoundedRect(pill_rect, 20, 20)

            # Left Phone Icon
            p.setFont(QFont("Noto Sans", 14))
            p.setPen(QColor(255, 255, 255))
            p.drawText(QRectF(x + 12, y, 32, h), Qt.AlignmentFlag.AlignCenter, "📱")

            # Center text
            p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
            p.setPen(ACCENT_CYAN)
            p.drawText(QRectF(x + 46, y + 10, w - 58, 20), Qt.AlignmentFlag.AlignLeft, "Telefona Bırak (AirDrop)")
            p.setFont(QFont("Noto Sans", 8))
            p.setPen(QColor(200, 200, 220))
            fn = self._airdrop_filename if self._airdrop_filename else "Dosya"
            p.drawText(QRectF(x + 46, y + 30, w - 58, 18), Qt.AlignmentFlag.AlignLeft, fn[:28])

        elif mode == MODE_AIRDROP_SENDING:
            # Sending file to Galaxy S25 FE
            p.setPen(QPen(ACCENT, 1.5))
            p.setBrush(QBrush(BG_NOTCH))
            p.drawRoundedRect(pill_rect, 20, 20)

            self.robo.draw(p, x + 30, y + h / 2.0, eye_w=10, eye_h=8)
            p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
            p.setPen(QColor(240, 230, 255))
            p.drawText(QRectF(x + 52, y, w - 60, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Galaxy S25 FE'ye Uçuyor... 🚀")

        elif mode == MODE_AIRDROP_SUCCESS:
            # Successfully sent!
            p.setPen(QPen(ACCENT_GREEN, 1.8))
            p.setBrush(QBrush(BG_NOTCH))
            p.drawRoundedRect(pill_rect, 20, 20)

            self.robo.draw(p, x + 30, y + h / 2.0, eye_w=10, eye_h=8)
            p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
            p.setPen(ACCENT_GREEN)
            p.drawText(QRectF(x + 52, y, w - 60, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Telefona Gönderildi ✓")

        elif mode == MODE_NOTCH_BLOOM:
            # Meta+Space trigger: notch stretches down like Apple liquid glass!
            grad = QLinearGradient(x, 0, x, h)
            grad.setColorAt(0.0, BG_NOTCH)
            grad.setColorAt(0.7, QColor(24, 18, 38, 252))
            grad.setColorAt(1.0, QColor(35, 26, 56, 255))
            p.setPen(QPen(ACCENT, 1.8))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(pill_rect, 22, 22)

            # Left Robo Eyes
            self.robo.draw(p, x + 34, y + h / 2.0, eye_w=10, eye_h=8)

            # Center Label with glowing accent
            p.setFont(QFont("Noto Sans", 10, QFont.Weight.Bold))
            p.setPen(QColor(255, 255, 255))
            p.drawText(QRectF(x + 55, y, w - 100, h), Qt.AlignmentFlag.AlignCenter, "⚡ BeamRadial Merkezi")

            # Right dropdown indicator
            p.setFont(QFont("Noto Sans", 8))
            p.setPen(ACCENT_LIGHT)
            p.drawText(QRectF(x + w - 42, y, 30, h), Qt.AlignmentFlag.AlignCenter, "▼")

        else:
            # Compact Apple Dynamic Island
            p.setPen(QPen(QColor(146, 110, 228, 75), 1.1))
            p.setBrush(QBrush(BG_NOTCH))
            p.drawRoundedRect(pill_rect, radius, radius)

            if mode == MODE_IDLE:
                self._paint_notch_idle(p, x, y, w, h)
            elif mode == MODE_MUSIC_COMPACT:
                self._paint_notch_music(p, x, y, w, h)
            elif mode == MODE_MUSIC_EXPANDED:
                self._paint_notch_ash_expanded(p, x, y, w, h)
            elif mode in (MODE_TASK_RUNNING, MODE_TASK_DONE, MODE_TASK_WAITING):
                self._paint_notch_task(p, x, y, w, h, mode)
            elif mode == MODE_GREETING:
                self._paint_notch_greeting(p, x, y, w, h)

        p.end()

    # ── Render: Notch Modes (Compact & Delicate) ──────────────────────────────

    def _paint_notch_idle(self, p: QPainter, x, y, w, h):
        """Idle Notch: Left Robo Eyes, Right Live Clock."""
        self.robo.draw(p, x + 26, y + h / 2.0, eye_w=10, eye_h=7)

        # Live Digital Clock badge on right
        current_time = time.strftime("%H:%M")
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        badge_rect = QRectF(x + w - 48, y + (h - 20) / 2.0, 40, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(25, 20, 36, 200)))
        p.drawRoundedRect(badge_rect, 10, 10)
        p.setPen(QColor(240, 240, 255))
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, current_time)

    def _paint_notch_music(self, p: QPainter, x, y, w, h):
        """Music Notch: Mini cover + title + dancing visualizer bars + Clock."""
        if self.mini_cover_pixmap:
            icon_rect = QRectF(x + 8, y + (h - 20) / 2.0, 20, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self.mini_cover_pixmap))
            p.drawRoundedRect(icon_rect, 10, 10)
        else:
            grad = QLinearGradient(x + 8, y + 7, x + 28, y + 27)
            grad.setColorAt(0.0, QColor(255, 0, 128))
            grad.setColorAt(1.0, QColor(0, 200, 255))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QRectF(x + 8, y + (h - 20) / 2.0, 20, 20))

        # Dancing Audio Bars
        self.visualizer.move(int(x + 32), int(y + (h - 18) / 2.0))

        # Title
        p.setFont(QFont("Noto Sans", 8, QFont.Weight.DemiBold))
        p.setPen(QColor(240, 240, 248))
        text_rect = QRectF(x + 58, y + (h - 18) / 2.0, w - 110, 18)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title_text[:16])

        # Live Digital Clock badge on right
        current_time = time.strftime("%H:%M")
        p.setFont(QFont("Noto Sans", 8, QFont.Weight.Bold))
        badge_rect = QRectF(x + w - 46, y + (h - 20) / 2.0, 38, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(25, 20, 36, 200)))
        p.drawRoundedRect(badge_rect, 10, 10)
        p.setPen(QColor(240, 240, 255))
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, current_time)

    def _paint_notch_ash_expanded(self, p: QPainter, x, y, w, h):
        text_x = x + 104
        text_w = w - 130
        p.setFont(QFont("Noto Sans", 10, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(text_x, y + 14, text_w, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title_text[:28])

        p.setFont(QFont("Noto Sans", 8, QFont.Weight.Medium))
        p.setPen(ACCENT_LIGHT)
        p.drawText(QRectF(text_x, y + 36, text_w, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.artist_text[:32])

        self.visualizer.move(int(x + w - 30), int(y + 14))
        self.cover_canvas.move(int(x + 12), int(y + 12))

    def _paint_notch_task(self, p: QPainter, x, y, w, h, mode):
        eye_w = w * 0.32
        self.robo.draw(p, x + eye_w / 2.0, y + h / 2.0, eye_w=10, eye_h=7)
        p.setFont(QFont("Noto Sans", 8, QFont.Weight.Bold))
        p.setPen(ACCENT_CYAN if mode == MODE_TASK_RUNNING else ACCENT_GREEN)
        p.drawText(QRectF(x + eye_w + 8, y + (h - 18) / 2.0, w - eye_w - 14, 18),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._task_label[:22])

    def _paint_notch_greeting(self, p: QPainter, x, y, w, h):
        self.robo.draw(p, x + w * 0.26, y + h / 2.0, eye_w=11, eye_h=8)
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        p.setPen(ACCENT_LIGHT)
        p.drawText(QRectF(x + w * 0.44, y + (h - 20) / 2.0, w * 0.52, 20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Hi, I'm Robo!")

    def _paint_notification(self, p: QPainter, x, y, w, h):
        badge_rect = QRectF(x + 12, y + (h - 40) / 2.0, 40, 40)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(146, 110, 228, 50)))
        p.drawRoundedRect(badge_rect, 10, 10)
        p.setFont(QFont("Noto Sans", 16))
        p.setPen(QColor(255, 255, 255))
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "🔔")

        p.setFont(QFont("Noto Sans", 8, QFont.Weight.Bold))
        p.setPen(ACCENT_CYAN)
        p.drawText(QRectF(x + 60, y + 12, w - 70, 16), Qt.AlignmentFlag.AlignLeft, self.notif_app.upper()[:22])

        p.setFont(QFont("Noto Sans", 9, QFont.Weight.DemiBold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + 60, y + 28, w - 70, 18), Qt.AlignmentFlag.AlignLeft, self.notif_title[:32])

        p.setFont(QFont("Noto Sans", 8))
        p.setPen(QColor(160, 150, 180))
        p.drawText(QRectF(x + 60, y + 46, w - 70, 16), Qt.AlignmentFlag.AlignLeft, self.notif_body[:40])

    def _paint_accessory_popup(self, p: QPainter, x, y, w, h):
        p.setFont(QFont("Noto Sans", 32))
        p.drawText(QRectF(x, y + 12, w, 48), Qt.AlignmentFlag.AlignCenter, "🎧")

        p.setFont(QFont("Noto Sans", 11, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x, y + 68, w, 20), Qt.AlignmentFlag.AlignCenter, self.acc_name[:22])

        p.setFont(QFont("Noto Sans", 9))
        p.setPen(ACCENT_GREEN)
        batt_txt = f"Bağlandı • %{self.acc_battery}" if self.acc_battery > 0 else "Bağlandı ✓"
        p.drawText(QRectF(x, y + 90, w, 18), Qt.AlignmentFlag.AlignCenter, batt_txt)

    # ── Render: NotchNook Control Center (Pixel-Perfect Alignment!) ──────────

    def _paint_notchnook_panel(self, p: QPainter, x, y, w, h):
        R = self._get_panel_rects()

        # ── 1. Top Status Row: Headset + Live Clock/Date + Phone Battery + [✕]
        # Headset pill
        hs_rect = QRectF(x + 14, y + 8, 96, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(22, 18, 32, 220)))
        p.drawRoundedRect(hs_rect, 11, 11)
        p.setFont(QFont("Noto Sans", 9))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + 18, y + 8, 18, 22), Qt.AlignmentFlag.AlignCenter, "🎧")
        bx = x + 40
        by = y + 14
        p.setPen(QPen(QColor(40, 35, 55), 2))
        p.drawArc(QRectF(bx, by, 10, 10), 0, 360 * 16)
        pct = self.headset_battery if self.headset_battery > 0 else 99
        p.setPen(QPen(ACCENT_GREEN, 2))
        p.drawArc(QRectF(bx, by, 10, 10), 90 * 16, -int((pct / 100.0) * 360 * 16))
        p.setFont(QFont("Noto Sans", 7, QFont.Weight.Bold))
        p.setPen(QColor(200, 190, 220))
        p.drawText(QRectF(bx + 14, y + 8, 40, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"%{pct}")

        # Center: Live Digital Clock & Date
        clock_txt = time.strftime("%H:%M") + "  •  " + time.strftime("%d %b %a")
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        p.setPen(QColor(240, 240, 255))
        p.drawText(QRectF(x + 115, y + 8, w - 230, 22), Qt.AlignmentFlag.AlignCenter, clock_txt)

        # Phone battery via KDE Connect
        ph_rect = QRectF(x + w - 146, y + 8, 106, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(22, 18, 32, 220)))
        p.drawRoundedRect(ph_rect, 11, 11)
        p.setFont(QFont("Noto Sans", 9))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + w - 144, y + 8, 18, 22), Qt.AlignmentFlag.AlignCenter, "📱")
        pbx = x + w - 122
        pby = y + 14
        p.setPen(QPen(QColor(40, 35, 55), 2))
        p.drawArc(QRectF(pbx, pby, 10, 10), 0, 360 * 16)
        ph_pct = self.phone_charge if self.phone_charge >= 0 else 6
        p.setPen(QPen(ACCENT_GREEN if ph_pct > 20 else QColor(255, 77, 109), 2))
        p.drawArc(QRectF(pbx, pby, 10, 10), 90 * 16, -int((ph_pct / 100.0) * 360 * 16))
        p.setFont(QFont("Noto Sans", 7, QFont.Weight.Bold))
        p.setPen(QColor(200, 190, 220))
        p_str = f"%{ph_pct}" + (" ⚡" if self.phone_charging else "")
        p.drawText(QRectF(pbx + 14, y + 8, 48, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, p_str)

        # Close button [✕]
        c_hover = (self.hovered_btn == "close")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 77, 109, 220) if c_hover else QColor(35, 30, 48, 180)))
        p.drawRoundedRect(R["close_btn"], 6, 6)
        p.setFont(QFont("Noto Sans", 8, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(R["close_btn"], Qt.AlignmentFlag.AlignCenter, "✕")

        # ── 2. Split Content: Card 1 (Media Player) & Card 2 (System Quick Hub)
        card_y = R["card_y"]
        card_h = R["card_h"]

        # ── TILE 1: Media Player (Width = 280px) ───────────────────────────
        t1_rect = QRectF(x + 14, card_y, R["t1_w"], card_h)
        p.setPen(QPen(QColor(80, 70, 110, 50), 1))
        p.setBrush(QBrush(QColor(18, 16, 26, 240)))
        p.drawRoundedRect(t1_rect, 16, 16)

        # Album Cover with Spotify badge
        art_rect = QRectF(x + 24, card_y + 12, 54, 54)
        if self.cover_pixmap and not self.cover_pixmap.isNull():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self.cover_pixmap.scaled(54, 54, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)))
            p.drawRoundedRect(art_rect, 10, 10)
        else:
            grad = QLinearGradient(art_rect.topLeft(), art_rect.bottomRight())
            grad.setColorAt(0.0, QColor(255, 0, 128))
            grad.setColorAt(1.0, QColor(0, 180, 255))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(art_rect, 10, 10)

        # Title & Artist
        p.setFont(QFont("Noto Sans", 10, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        title = self.title_text if self.title_text else "Television / So Far So"
        p.drawText(QRectF(x + 86, card_y + 14, R["t1_w"] - 94, 20), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title[:24])

        p.setFont(QFont("Noto Sans", 8))
        p.setPen(ACCENT_LIGHT)
        artist = self.artist_text if self.artist_text else "Rex Orange County"
        p.drawText(QRectF(x + 86, card_y + 34, R["t1_w"] - 94, 16), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, artist[:26])

        # Seek / Progress Bar
        bar_x = R["seek_rect"].x()
        bar_y = R["seek_rect"].y() + 6
        bar_w = R["seek_rect"].width()

        # Time labels
        p.setFont(QFont("Noto Sans", 7, QFont.Weight.Bold))
        p.setPen(QColor(140, 130, 160))
        cur_min = self.song_pos_s // 60
        cur_sec = self.song_pos_s % 60
        p.drawText(QRectF(bar_x, bar_y - 12, 40, 12), Qt.AlignmentFlag.AlignLeft, f"{cur_min}:{cur_sec:02d}")

        len_min = self.song_len_s // 60
        len_sec = self.song_len_s % 60
        p.drawText(QRectF(bar_x + bar_w - 40, bar_y - 12, 40, 12), Qt.AlignmentFlag.AlignRight, f"{len_min}:{len_sec:02d}")

        # Bar track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(40, 35, 55)))
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, 4), 2, 2)

        # Bar fill
        fill_w = bar_w * self.song_ratio
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, 4), 2, 2)

        # ── Media Control Buttons (100% Matching Geometry!) ───────────────
        # Prev Button
        prev_h = (self.hovered_btn == "prev")
        if prev_h:
            p.setBrush(QBrush(QColor(255, 255, 255, 25)))
            p.drawRoundedRect(R["prev_rect"], 8, 8)
        p.setFont(QFont("Noto Sans", 14))
        p.setPen(QColor(255, 255, 255))
        p.drawText(R["prev_rect"], Qt.AlignmentFlag.AlignCenter, "⏮")

        # Large Inverted Play/Pause Button
        play_h = (self.hovered_btn == "play")
        p.setPen(Qt.PenStyle.NoPen)
        if play_h:
            # Subtle glowing aura on hover
            p.setBrush(QBrush(QColor(180, 150, 250, 120)))
            p.drawEllipse(R["play_rect"].adjusted(-3, -3, 3, 3))
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(R["play_rect"])
        p.setFont(QFont("Noto Sans", 14, QFont.Weight.Bold))
        p.setPen(QColor(10, 10, 16))
        p.drawText(R["play_rect"], Qt.AlignmentFlag.AlignCenter, "⏸" if self.is_playing else "▶")

        # Next Button
        next_h = (self.hovered_btn == "next")
        if next_h:
            p.setBrush(QBrush(QColor(255, 255, 255, 25)))
            p.drawRoundedRect(R["next_rect"], 8, 8)
        p.setFont(QFont("Noto Sans", 14))
        p.setPen(QColor(255, 255, 255))
        p.drawText(R["next_rect"], Qt.AlignmentFlag.AlignCenter, "⏭")

        # ── TILE 2: Quick System Hub ──────────────────────────────────────
        t2_rect = QRectF(R["t2_x"], card_y, R["t2_w"], card_h)
        p.setPen(QPen(QColor(80, 70, 110, 50), 1))
        p.setBrush(QBrush(QColor(18, 16, 26, 240)))
        p.drawRoundedRect(t2_rect, 16, 16)

        t2_x = R["t2_x"]
        t2_w = R["t2_w"]

        # CPU bar
        p.setFont(QFont("Noto Sans", 7, QFont.Weight.Bold))
        p.setPen(QColor(160, 150, 180))
        p.drawText(QRectF(t2_x + 10, card_y + 12, 26, 12), Qt.AlignmentFlag.AlignLeft, "CPU")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(35, 30, 48)))
        p.drawRoundedRect(QRectF(t2_x + 38, card_y + 16, t2_w - 68, 4), 2, 2)
        p.setBrush(QBrush(ACCENT_CYAN))
        p.drawRoundedRect(QRectF(t2_x + 38, card_y + 16, (t2_w - 68) * (self.cpu_usage / 100.0), 4), 2, 2)
        p.setPen(QColor(200, 190, 220))
        p.drawText(QRectF(t2_x + t2_w - 28, card_y + 12, 24, 12), Qt.AlignmentFlag.AlignRight, f"{self.cpu_usage}%")

        # RAM bar
        p.setPen(QColor(160, 150, 180))
        p.drawText(QRectF(t2_x + 10, card_y + 30, 26, 12), Qt.AlignmentFlag.AlignLeft, "RAM")
        p.setBrush(QBrush(QColor(35, 30, 48)))
        p.drawRoundedRect(QRectF(t2_x + 38, card_y + 34, t2_w - 68, 4), 2, 2)
        p.setBrush(QBrush(ACCENT))
        p.drawRoundedRect(QRectF(t2_x + 38, card_y + 34, (t2_w - 68) * (self.ram_usage / 100.0), 4), 2, 2)
        p.setPen(QColor(200, 190, 220))
        p.drawText(QRectF(t2_x + t2_w - 28, card_y + 30, 24, 12), Qt.AlignmentFlag.AlignRight, f"{self.ram_usage}%")

        # Volume Slider
        p.setFont(QFont("Noto Sans", 8))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(t2_x + 8, card_y + 50, 16, 16), Qt.AlignmentFlag.AlignCenter, "🔉")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(35, 30, 48)))
        p.drawRoundedRect(QRectF(t2_x + 28, card_y + 56, t2_w - 62, 5), 2.5, 2.5)
        v_fill = (t2_w - 62) * (self.system_volume / 100.0)
        p.setBrush(QBrush(ACCENT_GREEN))
        p.drawRoundedRect(QRectF(t2_x + 28, card_y + 56, v_fill, 5), 2.5, 2.5)
        p.setFont(QFont("Noto Sans", 7, QFont.Weight.Bold))
        p.setPen(QColor(200, 190, 220))
        p.drawText(QRectF(t2_x + t2_w - 30, card_y + 50, 26, 16), Qt.AlignmentFlag.AlignRight, f"{self.system_volume}%")

        # ── Apple iOS / macOS Control Center Style Quick Shortcut Grid ─────────────
        btn_round = 8.5
        apple_glass = QColor(255, 255, 255, 26)       # Translucent Apple frosted glass
        apple_border = QColor(255, 255, 255, 35)
        apple_blue = QColor(0, 122, 255, 235)         # iOS Vivid Blue
        apple_amber = QColor(255, 149, 0, 235)        # iOS Night Shift Amber
        apple_green = QColor(52, 199, 89, 235)        # iOS Performance Green
        apple_red = QColor(255, 59, 48, 235)          # iOS Red

        # 1. Wi-Fi
        p.setPen(QPen(apple_border, 1.0))
        p.setBrush(QBrush(apple_blue if self.wifi_enabled else apple_glass))
        p.drawRoundedRect(R["btn_wifi"], btn_round, btn_round)
        draw_apple_wifi(p, R["btn_wifi"], QColor(255, 255, 255) if self.wifi_enabled else QColor(190, 190, 210))

        # 2. Bluetooth
        p.setPen(QPen(apple_border, 1.0))
        p.setBrush(QBrush(apple_blue if self.net_manager.bt_enabled else apple_glass))
        p.drawRoundedRect(R["btn_bt"], btn_round, btn_round)
        draw_apple_bluetooth(p, R["btn_bt"], QColor(255, 255, 255) if self.net_manager.bt_enabled else QColor(190, 190, 210))

        # 3. Night Light (Apple Night Shift Moon)
        p.setPen(QPen(apple_border, 1.0))
        p.setBrush(QBrush(apple_amber if self.night_light_on else apple_glass))
        p.drawRoundedRect(R["btn_nl"], btn_round, btn_round)
        draw_apple_moon(p, R["btn_nl"], QColor(255, 255, 255) if self.night_light_on else QColor(190, 190, 210))

        # 4. Performance / GameMode (Apple Bolt)
        p.setPen(QPen(apple_border, 1.0))
        p.setBrush(QBrush(apple_green if self.gamemode_on else apple_glass))
        p.drawRoundedRect(R["btn_game"], btn_round, btn_round)
        draw_apple_bolt(p, R["btn_game"], QColor(255, 255, 255) if self.gamemode_on else QColor(190, 190, 210))

        # 5. Mute Audio (Apple Speaker Wave / Mute)
        p.setPen(QPen(apple_border, 1.0))
        p.setBrush(QBrush(apple_red if self.is_muted else apple_glass))
        p.drawRoundedRect(R["btn_mute"], btn_round, btn_round)
        draw_apple_speaker(p, R["btn_mute"], QColor(255, 255, 255) if self.is_muted else QColor(190, 190, 210), self.is_muted)

        # 6. Screenshot (Apple Camera / Viewfinder)
        p.setPen(QPen(apple_border, 1.0))
        p.setBrush(QBrush(apple_glass))
        p.drawRoundedRect(R["btn_shot"], btn_round, btn_round)
        draw_apple_camera(p, R["btn_shot"], QColor(220, 220, 240))
