"""
Robo Island — Unified Apple iPhone 14/15 Dynamic Island + Quick Control Panel
Matches user's reference designs:
  - Tab 0: Media Player (Image 2 style with large white round Play/Pause button, seek bar, album art)
  - Tab 1: Wi-Fi Manager (Image 4 style with switch & active/available network cards)
  - Tab 2: Widgets & Battery (Image 5 style with Weather, CPU/RAM bars, KDE Connect Phone & BT Headset battery)
  - Accessory Pop-up Card (Image 3 style when Bluetooth earbuds connect)
  - Live System Notification banner directly from the Dynamic Island!
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
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal

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
MODE_IDLE            = 1   # Notch: Sleeping/idle Robo eyes + temp badge
MODE_MUSIC_COMPACT   = 2   # Notch: Spotify track + dancing visualizer + temp badge
MODE_MUSIC_EXPANDED  = 3   # Notch: Ash wind particle track change (4.5s)
MODE_TASK_RUNNING    = 4   # Notch: Active AI task (cyan spinning eyes)
MODE_TASK_DONE       = 5   # Notch: Task completed (green happy eyes)
MODE_TASK_WAITING    = 6   # Notch: Waiting for approval (amber alert eyes)
MODE_GREETING        = 7   # Notch: "Hi, I'm Robo!"
MODE_NOTIFICATION    = 8   # Notch: System Notification banner popup (4.5s)
MODE_ACCESSORY_POPUP = 9   # Notch: Bluetooth Headset connected card (4s)
MODE_QUICK_PANEL     = 10  # Full Expanded Control Panel (Carousel tabs)

MODE_DIMS = {
    MODE_IDLE:            (180,  38),
    MODE_MUSIC_COMPACT:   (240,  38),
    MODE_MUSIC_EXPANDED:  (440, 110),
    MODE_TASK_RUNNING:    (280,  44),
    MODE_TASK_DONE:       (280,  44),
    MODE_TASK_WAITING:    (300,  48),
    MODE_GREETING:        (210,  42),
    MODE_NOTIFICATION:    (420,  80),
    MODE_ACCESSORY_POPUP: (300, 150),
    MODE_QUICK_PANEL:     (480, 265),
}

ACCENT       = QColor(146, 110, 228)        # #926ee4
ACCENT_LIGHT = QColor(180, 150, 250)        # #b496fa
ACCENT_CYAN  = QColor(0,   200, 255)
ACCENT_GREEN = QColor(29,  185,  84)
BG_NOTCH     = QColor(11,  11,  16,  252)   # Apple matte black
BG_PANEL     = QColor(14,  13,  22,  252)


class DynamicIsland(QWidget):
    """Unified Dynamic Island, Notification Engine & Multi-tab Control Center."""

    def __init__(self, target_screen_name: str = "HDMI-A-1", parent=None):
        super().__init__(parent)
        self.target_screen_name = target_screen_name

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        # Canvas bounds (large enough for expanded panel)
        self.canvas_width  = 560
        self.canvas_height = 300
        self.setFixedSize(self.canvas_width, self.canvas_height)

        # ── Animated pill dimensions ──────────────────────────────────────
        self._pill_width  = 0.0
        self._pill_height = 0.0
        self.target_width  = 0.0
        self.target_height = 0.0
        self.current_mode  = MODE_IDLE
        self._previous_mode = MODE_IDLE

        # Carousel page index for Quick Panel (0: Media, 1: Wi-Fi, 2: Widgets & Battery)
        self.current_page = 0

        # ── Mouse & Hover state ───────────────────────────────────────────
        self._hover_pos = QPointF(-100, -100)
        self._is_dragging_volume = False

        # ── Spotify state ─────────────────────────────────────────────────
        self.title_text  = ""
        self.artist_text = ""
        self.album_text  = ""
        self.is_playing  = False
        self.cover_pixmap: QPixmap | None = None
        self.mini_cover_pixmap: QPixmap | None = None

        # ── System Telemetry & Devices ────────────────────────────────────
        self.system_volume = 50
        self.is_muted = False
        self.night_light_on = False
        self.gamemode_on = False

        # Notification state
        self.notif_app   = ""
        self.notif_title = ""
        self.notif_body  = ""
        self.notif_icon  = ""

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
        self.networks = []
        self.cpu_usage = 0
        self.ram_usage = 0
        self.weather_temp = "19°"
        self.weather_cond = "Açık"

        # Task state
        self._task_label = ""
        self._task_dots  = 0

        # ── Sub-widgets ───────────────────────────────────────────────────
        self.cover_canvas = AshCoverCanvas(size=84, parent=self)
        self.cover_canvas.setGeometry(16, 12, 144, 84)
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
        self.collapse_timer.setInterval(4500)
        self.collapse_timer.timeout.connect(self._on_collapse_timeout)

        self.notif_timer = QTimer(self)
        self.notif_timer.setSingleShot(True)
        self.notif_timer.setInterval(5000)
        self.notif_timer.timeout.connect(self._on_collapse_timeout)

        self.acc_timer = QTimer(self)
        self.acc_timer.setSingleShot(True)
        self.acc_timer.setInterval(4000)
        self.acc_timer.timeout.connect(self._on_collapse_timeout)

        # Telemetry sync
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(2000)
        self.sync_timer.timeout.connect(self._sync_audio_telemetry)
        self.sync_timer.start()

        # LayerShell Setup
        self.update_screen_position(target_screen_name)
        self.show()
        self.set_click_through(True)

        # Initial greeting
        QTimer.singleShot(800, self._show_greeting)

    # ── LayerShell & Click-Through ────────────────────────────────────────────

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

    def set_click_through(self, enable: bool):
        try:
            if not os.path.exists(LIB_LAYERSHELL_PATH):
                return
            wh = self.windowHandle()
            if not wh:
                return
            lib = ctypes.CDLL(LIB_LAYERSHELL_PATH)
            lib.set_click_through.argtypes = [ctypes.c_void_p, ctypes.c_bool]
            lib.set_click_through.restype = ctypes.c_bool
            ptr_wh = shiboken6.getCppPointer(wh)[0]
            lib.set_click_through(ptr_wh, enable)
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
        self.notif_icon  = icon

        # Don't interrupt open control panel
        if self.current_mode == MODE_QUICK_PANEL:
            return

        self.set_mode(MODE_NOTIFICATION)
        self.notif_timer.start()
        print(f"[RoboIsland] Notification from {app_name}: {summary}")

    def _on_accessory_connected(self, dev_name, battery_pct):
        self.acc_name = dev_name
        self.acc_battery = battery_pct

        if self.current_mode == MODE_QUICK_PANEL:
            return

        self.set_mode(MODE_ACCESSORY_POPUP)
        self.acc_timer.start()
        print(f"[RoboIsland] Accessory connected: {dev_name} ({battery_pct}%)")

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
        self.weather_temp = data.get("weather_temp", "19°")
        self.weather_cond = data.get("weather_cond", "Açık")
        self.wifi_enabled = data.get("wifi_enabled", True)
        self.connected_ssid = data.get("connected_ssid", "")
        self.networks = data.get("networks", [])
        self.update()

    def _sync_audio_telemetry(self):
        try:
            res = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], capture_output=True, text=True, timeout=0.3)
            m = re.search(r'(\d+)%', res.stdout)
            if m:
                self.system_volume = int(m.group(1))
            res_mute = subprocess.run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"], capture_output=True, text=True, timeout=0.3)
            self.is_muted = ("yes" in res_mute.stdout.lower())
        except Exception:
            pass

    # ── Hotkey / Quick Control Panel Toggle ───────────────────────────────────

    def toggle_quick_panel(self):
        if self.current_mode == MODE_QUICK_PANEL:
            self.close_quick_panel()
        else:
            self.open_quick_panel()

    def open_quick_panel(self):
        self._previous_mode = self.current_mode
        self._sync_audio_telemetry()
        self.set_mode(MODE_QUICK_PANEL)
        self.set_click_through(False)  # MOUSE INTERACTIVE!
        self.update()

    def close_quick_panel(self):
        self.set_click_through(True)   # CLICK-THROUGH RESTORED!
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
                22, 22, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
            )
        else:
            self.cover_pixmap = None
            self.mini_cover_pixmap = None

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
            QTimer.singleShot(4000, self._on_collapse_timeout)

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
        tw, th = MODE_DIMS.get(mode, (180, 38))
        self.target_width  = float(tw)
        self.target_height = float(th)

        if mode == MODE_IDLE:
            self.robo.set_state("idle")
        elif mode == MODE_TASK_RUNNING:
            self.robo.set_state("active")
        elif mode in (MODE_TASK_DONE, MODE_GREETING, MODE_QUICK_PANEL):
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
        QTimer.singleShot(2600, self._after_greeting)

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

    def _step_dimensions(self):
        diff_w = self.target_width  - self._pill_width
        diff_h = self.target_height - self._pill_height
        if abs(diff_w) > 0.5 or abs(diff_h) > 0.5:
            self._pill_width  += diff_w * 0.18
            self._pill_height += diff_h * 0.18
            self.update()
        else:
            self._pill_width  = self.target_width
            self._pill_height = self.target_height
            self.update()

    # ── Mouse Interaction in Quick Panel ──────────────────────────────────────

    def mousePressEvent(self, event):
        if self.current_mode != MODE_QUICK_PANEL:
            # Clicking the compact notch opens the control panel!
            pos = event.position()
            cx = self.width() / 2.0
            x  = cx - self._pill_width / 2.0
            pill_rect = QRectF(x, 0, self._pill_width, self._pill_height)
            if pill_rect.contains(pos):
                self.open_quick_panel()
                event.accept()
                return
            super().mousePressEvent(event)
            return

        pos = event.position()
        cx = self.width() / 2.0
        x  = cx - self._pill_width / 2.0
        y  = 0.0
        w  = self._pill_width
        h  = self._pill_height

        # 1. Top Icons: Wi-Fi, Bluetooth, Airplane, Eco, Settings [✕]
        icon_w = 34
        gap = 8
        start_x = x + 16

        # Wi-Fi icon -> switch to Tab 1
        wifi_rect = QRectF(start_x, y + 10, icon_w, icon_w)
        if wifi_rect.contains(pos):
            self.current_page = 1
            event.accept()
            self.update()
            return

        # BT icon -> toggle bluetooth
        bt_rect = QRectF(start_x + (icon_w + gap), y + 10, icon_w, icon_w)
        if bt_rect.contains(pos):
            self.net_manager.toggle_bluetooth()
            event.accept()
            self.update()
            return

        # Airplane icon
        air_rect = QRectF(start_x + (icon_w + gap) * 2, y + 10, icon_w, icon_w)
        if air_rect.contains(pos):
            self.net_manager.toggle_airplane()
            event.accept()
            self.update()
            return

        # Eco / GameMode icon
        eco_rect = QRectF(start_x + (icon_w + gap) * 3, y + 10, icon_w, icon_w)
        if eco_rect.contains(pos):
            self.gamemode_on = not self.gamemode_on
            event.accept()
            self.update()
            return

        # Settings / Close [✕] icon on far right
        close_rect = QRectF(x + w - 44, y + 10, icon_w, icon_w)
        if close_rect.contains(pos):
            self.close_quick_panel()
            event.accept()
            return

        # 2. Bottom Carousel Dots Indicator (Tab 0, 1, 2)
        dot_y = y + h - 20
        dot_cx = x + w / 2.0
        for i in range(3):
            dot_rect = QRectF(dot_cx - 24 + i * 16, dot_y, 16, 16)
            if dot_rect.contains(pos):
                self.current_page = i
                event.accept()
                self.update()
                return

        # ── Page-Specific Interaction ─────────────────────────────────────
        if self.current_page == 0:
            # TAB 0: Media Player
            # Controls: Prev, Play/Pause, Next
            ctrl_y = y + 76
            prev_rect = QRectF(x + w - 146, ctrl_y, 34, 34)
            play_rect = QRectF(x + w - 104, ctrl_y - 4, 42, 42)
            next_rect = QRectF(x + w - 54,  ctrl_y, 34, 34)

            if prev_rect.contains(pos):
                subprocess.run(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Previous"], timeout=0.3)
                event.accept()
                return

            if play_rect.contains(pos):
                subprocess.run(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.PlayPause"], timeout=0.3)
                self.is_playing = not self.is_playing
                self.update()
                event.accept()
                return

            if next_rect.contains(pos):
                subprocess.run(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Next"], timeout=0.3)
                event.accept()
                return

            # Seek / Volume bar click
            bar_rect = QRectF(x + 106, y + 144, w - 130, 20)
            if bar_rect.contains(pos):
                norm = (pos.x() - (x + 106)) / (w - 130)
                pct = int(norm * 100)
                try:
                    subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"], timeout=0.3)
                    self.system_volume = pct
                except Exception:
                    pass
                event.accept()
                self.update()
                return

        elif self.current_page == 1:
            # TAB 1: Wi-Fi Manager
            # Wi-Fi switch toggle
            sw_rect = QRectF(x + w - 66, y + 54, 46, 24)
            if sw_rect.contains(pos):
                self.net_manager.toggle_wifi()
                event.accept()
                self.update()
                return

        elif self.current_page == 2:
            # TAB 2: Widgets & Battery
            pass

        # Clicking outside card -> close
        panel_rect = QRectF(x, y, w, h)
        if not panel_rect.contains(pos):
            self.close_quick_panel()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._hover_pos = event.position()
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_pos = QPointF(-100, -100)
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.current_mode == MODE_QUICK_PANEL:
                self.close_quick_panel()
                event.accept()
                return
        super().keyPressEvent(event)

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
        radius = min(h / 2.0, 24.0)

        pill_rect = QRectF(x, y, w, h)

        if mode == MODE_QUICK_PANEL:
            # Quick Control Center Panel
            p.setPen(QPen(QColor(146, 110, 228, 140), 1.4))
            p.setBrush(QBrush(BG_PANEL))
            p.drawRoundedRect(pill_rect, radius, radius)
            self._paint_quick_panel(p, x, y, w, h)

        elif mode == MODE_NOTIFICATION:
            # System Notification Banner
            p.setPen(QPen(ACCENT_CYAN, 1.4))
            p.setBrush(QBrush(BG_NOTCH))
            p.drawRoundedRect(pill_rect, radius, radius)
            self._paint_notification(p, x, y, w, h)

        elif mode == MODE_ACCESSORY_POPUP:
            # Bluetooth Accessory Connected Popup (AirPods / Galaxy Buds style)
            p.setPen(QPen(QColor(255, 255, 255, 60), 1.4))
            p.setBrush(QBrush(BG_NOTCH))
            p.drawRoundedRect(pill_rect, 22, 22)
            self._paint_accessory_popup(p, x, y, w, h)

        else:
            # Resting iPhone Dynamic Island Notch
            p.setPen(QPen(QColor(146, 110, 228, 80), 1.2))
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

    # ── Render: Resting Notch Modes ───────────────────────────────────────────

    def _paint_notch_idle(self, p: QPainter, x, y, w, h):
        """Idle Notch: Left Robo Eyes, Right Weather / Battery pill."""
        self.robo.draw(p, x + 30, y + h / 2.0, eye_w=12, eye_h=8)

        # Weather / Battery badge on right
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        badge_rect = QRectF(x + w - 50, y + (h - 22) / 2.0, 42, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(30, 25, 45, 180)))
        p.drawRoundedRect(badge_rect, 11, 11)
        p.setPen(QColor(240, 240, 255))
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self.weather_temp)

    def _paint_notch_music(self, p: QPainter, x, y, w, h):
        """Music Notch: Mini cover / gradient dot + dancing visualizer bars + weather badge."""
        if self.mini_cover_pixmap:
            icon_rect = QRectF(x + 10, y + (h - 22) / 2.0, 22, 22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self.mini_cover_pixmap))
            p.drawRoundedRect(icon_rect, 11, 11)
        else:
            # Gradient dot
            grad = QLinearGradient(x + 10, y + 8, x + 30, y + 28)
            grad.setColorAt(0.0, QColor(255, 0, 128))
            grad.setColorAt(1.0, QColor(0, 200, 255))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QRectF(x + 10, y + (h - 20) / 2.0, 20, 20))

        # Dancing Audio Bars
        self.visualizer.move(int(x + 36), int(y + (h - 18) / 2.0))

        # Title
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.DemiBold))
        p.setPen(QColor(240, 240, 248))
        text_rect = QRectF(x + 64, y + (h - 18) / 2.0, w - 120, 18)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title_text[:16])

        # Temperature badge on right (Image 1 style: "19°")
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        badge_rect = QRectF(x + w - 48, y + (h - 22) / 2.0, 40, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(30, 25, 45, 180)))
        p.drawRoundedRect(badge_rect, 11, 11)
        p.setPen(QColor(240, 240, 255))
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self.weather_temp)

    def _paint_notch_ash_expanded(self, p: QPainter, x, y, w, h):
        text_x = x + 116
        text_w = w - 150
        p.setFont(QFont("Noto Sans", 11, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(text_x, y + 16, text_w, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title_text[:28])

        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Medium))
        p.setPen(ACCENT_LIGHT)
        p.drawText(QRectF(text_x, y + 40, text_w, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.artist_text[:32])

        self.visualizer.move(int(x + w - 34), int(y + 16))
        self.cover_canvas.move(int(x + 14), int(y + 13))

    def _paint_notch_task(self, p: QPainter, x, y, w, h, mode):
        eye_w = w * 0.35
        self.robo.draw(p, x + eye_w / 2.0, y + h / 2.0, eye_w=12, eye_h=8)
        p.setFont(QFont("Noto Sans", 8, QFont.Weight.Bold))
        p.setPen(ACCENT_CYAN if mode == MODE_TASK_RUNNING else ACCENT_GREEN)
        p.drawText(QRectF(x + eye_w + 10, y + (h - 18) / 2.0, w - eye_w - 16, 18),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._task_label[:24])

    def _paint_notch_greeting(self, p: QPainter, x, y, w, h):
        self.robo.draw(p, x + w * 0.28, y + h / 2.0, eye_w=13, eye_h=9)
        p.setFont(QFont("Noto Sans", 10, QFont.Weight.Bold))
        p.setPen(ACCENT_LIGHT)
        p.drawText(QRectF(x + w * 0.46, y + (h - 20) / 2.0, w * 0.50, 20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Hi, I'm Robo!")

    # ── Render: Notification Banner ───────────────────────────────────────────

    def _paint_notification(self, p: QPainter, x, y, w, h):
        # App Badge Icon (Bell / App)
        badge_rect = QRectF(x + 14, y + (h - 44) / 2.0, 44, 44)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(146, 110, 228, 60)))
        p.drawRoundedRect(badge_rect, 12, 12)
        p.setFont(QFont("Noto Sans", 18))
        p.setPen(QColor(255, 255, 255))
        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "🔔")

        # App Name + Notification Summary
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        p.setPen(ACCENT_CYAN)
        p.drawText(QRectF(x + 68, y + 14, w - 80, 18), Qt.AlignmentFlag.AlignLeft, self.notif_app.upper()[:24])

        p.setFont(QFont("Noto Sans", 10, QFont.Weight.DemiBold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + 68, y + 32, w - 80, 20), Qt.AlignmentFlag.AlignLeft, self.notif_title[:32])

        p.setFont(QFont("Noto Sans", 8))
        p.setPen(QColor(170, 160, 190))
        p.drawText(QRectF(x + 68, y + 52, w - 80, 18), Qt.AlignmentFlag.AlignLeft, self.notif_body[:44])

    # ── Render: Bluetooth Accessory Connected Popup (Görsel 3 Tarzı) ──────────

    def _paint_accessory_popup(self, p: QPainter, x, y, w, h):
        # Earbuds 3D Emoji / Render Center
        p.setFont(QFont("Noto Sans", 38))
        p.drawText(QRectF(x, y + 16, w, 56), Qt.AlignmentFlag.AlignCenter, "🎧")

        # Device Name
        p.setFont(QFont("Noto Sans", 12, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x, y + 82, w, 22), Qt.AlignmentFlag.AlignCenter, self.acc_name[:24])

        # Subtext: "Connected • 85%"
        p.setFont(QFont("Noto Sans", 10))
        p.setPen(ACCENT_LIGHT)
        batt_txt = f"Bağlandı • %{self.acc_battery}" if self.acc_battery > 0 else "Bağlandı ✓"
        p.drawText(QRectF(x, y + 108, w, 20), Qt.AlignmentFlag.AlignCenter, batt_txt)

    # ── Render: Quick Control Center (Görsel 2, 4, 5 Çoklu Sayfa) ────────────

    def _paint_quick_panel(self, p: QPainter, x, y, w, h):
        mx = self._hover_pos.x()
        my = self._hover_pos.y()

        # ── Top Bar: Quick Action Buttons (Görsellerdeki üst sıra) ────────
        icon_w = 34
        gap = 8
        start_x = x + 16

        # 1. 📶 Wi-Fi
        b_wifi = QRectF(start_x, y + 10, icon_w, icon_w)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(ACCENT if (self.current_page == 1 or self.wifi_enabled) else QColor(30, 25, 45, 180)))
        p.drawRoundedRect(b_wifi, 17, 17)
        p.setFont(QFont("Noto Sans", 12))
        p.setPen(QColor(255, 255, 255))
        p.drawText(b_wifi, Qt.AlignmentFlag.AlignCenter, "📶")

        # 2. ᛒ Bluetooth
        b_bt = QRectF(start_x + (icon_w + gap), y + 10, icon_w, icon_w)
        p.setBrush(QBrush(QColor(0, 122, 255, 220) if self.net_manager.bt_enabled else QColor(30, 25, 45, 180)))
        p.drawRoundedRect(b_bt, 17, 17)
        p.drawText(b_bt, Qt.AlignmentFlag.AlignCenter, "ᛒ")

        # 3. ✈ Airplane
        b_air = QRectF(start_x + (icon_w + gap) * 2, y + 10, icon_w, icon_w)
        p.setBrush(QBrush(QColor(255, 150, 0, 220) if self.net_manager.airplane_mode else QColor(30, 25, 45, 180)))
        p.drawRoundedRect(b_air, 17, 17)
        p.drawText(b_air, Qt.AlignmentFlag.AlignCenter, "✈")

        # 4. ⚡ Eco / GameMode
        b_eco = QRectF(start_x + (icon_w + gap) * 3, y + 10, icon_w, icon_w)
        p.setBrush(QBrush(ACCENT_GREEN if self.gamemode_on else QColor(30, 25, 45, 180)))
        p.drawRoundedRect(b_eco, 17, 17)
        p.drawText(b_eco, Qt.AlignmentFlag.AlignCenter, "⚡")

        # 5. ⚙ Settings / Close on far right
        b_close = QRectF(x + w - 44, y + 10, icon_w, icon_w)
        b_close_hover = b_close.contains(mx, my)
        p.setBrush(QBrush(QColor(255, 77, 109, 200) if b_close_hover else QColor(35, 30, 50, 180)))
        p.drawRoundedRect(b_close, 17, 17)
        p.drawText(b_close, Qt.AlignmentFlag.AlignCenter, "✕")

        # ── Carousel Content per Page ─────────────────────────────────────
        if self.current_page == 0:
            self._paint_page_media(p, x, y, w, h)
        elif self.current_page == 1:
            self._paint_page_wifi(p, x, y, w, h)
        elif self.current_page == 2:
            self._paint_page_widgets(p, x, y, w, h)

        # ── Bottom Carousel Dots Indicator `• • •` (Görsel 2 ve 5 gibi) ───
        dot_y = y + h - 16
        dot_cx = x + w / 2.0
        for i in range(3):
            is_active = (i == self.current_page)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255) if is_active else QColor(80, 70, 100)))
            rw = 18 if is_active else 6
            p.drawRoundedRect(QRectF(dot_cx - 24 + i * 16, dot_y, rw, 5), 2.5, 2.5)

    # ── Page 0: Media Player (Görsel 2) ───────────────────────────────────────

    def _paint_page_media(self, p: QPainter, x, y, w, h):
        # Album cover (Image 2 style with glowing gradient)
        art_rect = QRectF(x + 24, y + 62, 84, 84)
        if self.cover_pixmap and not self.cover_pixmap.isNull():
            p.setPen(QPen(QColor(146, 110, 228, 80), 1))
            p.setBrush(QBrush(self.cover_pixmap.scaled(84, 84, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)))
            p.drawRoundedRect(art_rect, 14, 14)
        else:
            grad = QLinearGradient(art_rect.topLeft(), art_rect.bottomRight())
            grad.setColorAt(0.0, QColor(255, 0, 128))
            grad.setColorAt(1.0, QColor(0, 180, 255))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(art_rect, 14, 14)

        # Track Title & Artist
        p.setFont(QFont("Noto Sans", 13, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        title = self.title_text if self.title_text else "Night Drive"
        p.drawText(QRectF(x + 124, y + 66, w - 240, 24), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title[:26])

        p.setFont(QFont("Noto Sans", 10))
        p.setPen(ACCENT_LIGHT)
        artist = self.artist_text if self.artist_text else "Neon Coast"
        p.drawText(QRectF(x + 124, y + 92, w - 240, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, artist[:30])

        # Media Controls: Prev, Large White Play/Pause Button, Next (Image 2)
        ctrl_y = y + 74
        p.setFont(QFont("Noto Sans", 14))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + w - 146, ctrl_y, 34, 34), Qt.AlignmentFlag.AlignCenter, "⏮")

        # Big White Round Play/Pause Button (Inverted circle with black symbol)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(QRectF(x + w - 104, ctrl_y - 4, 42, 42))
        p.setFont(QFont("Noto Sans", 16, QFont.Weight.Bold))
        p.setPen(QColor(10, 10, 16))
        p.drawText(QRectF(x + w - 104, ctrl_y - 4, 42, 42), Qt.AlignmentFlag.AlignCenter, "⏸" if self.is_playing else "▶")

        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + w - 54, ctrl_y, 34, 34), Qt.AlignmentFlag.AlignCenter, "⏭")

        # Green Progress / Volume Bar (Image 2 style)
        bar_x = x + 124
        bar_y = y + 130
        bar_w = w - 150
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(40, 35, 55)))
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, 5), 2.5, 2.5)

        fill_w = bar_w * (self.system_volume / 100.0)
        p.setBrush(QBrush(ACCENT_GREEN))
        p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, 5), 2.5, 2.5)

        # Volume / Status percentage
        p.setFont(QFont("Noto Sans", 8, QFont.Weight.Bold))
        p.setPen(QColor(180, 170, 200))
        p.drawText(QRectF(bar_x, bar_y + 10, 100, 16), Qt.AlignmentFlag.AlignLeft, f"Ses: %{self.system_volume}")

    # ── Page 1: Wi-Fi Manager (Görsel 4) ──────────────────────────────────────

    def _paint_page_wifi(self, p: QPainter, x, y, w, h):
        # Title "Wi-Fi"
        p.setFont(QFont("Noto Sans", 12, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + 24, y + 54, 100, 24), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Wi-Fi")

        # Toggle Switch (Blue active switch like Image 4)
        sw_rect = QRectF(x + w - 66, y + 54, 46, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 122, 255) if self.wifi_enabled else QColor(50, 45, 65)))
        p.drawRoundedRect(sw_rect, 12, 12)
        thumb_x = (x + w - 42) if self.wifi_enabled else (x + w - 64)
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(QRectF(thumb_x, y + 56, 20, 20))

        # Networks List (Cards like Image 4)
        card_y = y + 88
        card_h = 36
        card_w = w - 48

        if not self.networks and self.connected_ssid:
            self.networks = [{"ssid": self.connected_ssid, "active": True}]

        for idx, net in enumerate(self.networks[:3]):
            ny = card_y + idx * (card_h + 8)
            r = QRectF(x + 24, ny, card_w, card_h)

            if net.get("active"):
                # Active Green Bordered Card
                p.setPen(QPen(ACCENT_GREEN, 1.4))
                p.setBrush(QBrush(QColor(10, 40, 25, 200)))
                p.drawRoundedRect(r, 10, 10)
                p.setFont(QFont("Noto Sans", 10, QFont.Weight.Bold))
                p.setPen(QColor(255, 255, 255))
                p.drawText(QRectF(x + 54, ny, card_w - 140, card_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, net.get("ssid", ""))
                p.setFont(QFont("Noto Sans", 9))
                p.setPen(ACCENT_GREEN)
                p.drawText(QRectF(x + card_w - 70, ny, 80, card_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, "Bağlı ✓")
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(25, 22, 38, 200)))
                p.drawRoundedRect(r, 10, 10)
                p.setFont(QFont("Noto Sans", 10))
                p.setPen(QColor(220, 220, 235))
                p.drawText(QRectF(x + 54, ny, card_w - 140, card_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, net.get("ssid", ""))
                p.setFont(QFont("Noto Sans", 9))
                p.setPen(QColor(140, 130, 160))
                p.drawText(QRectF(x + card_w - 70, ny, 80, card_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, "Kayıtlı")

            p.setFont(QFont("Noto Sans", 12))
            p.setPen(ACCENT_GREEN if net.get("active") else QColor(140, 130, 160))
            p.drawText(QRectF(x + 32, ny, 20, card_h), Qt.AlignmentFlag.AlignCenter, "📶")

    # ── Page 2: Widgets & Battery (Görsel 5 + KDE Connect & Bluetooth) ────────

    def _paint_page_widgets(self, p: QPainter, x, y, w, h):
        tile_y = y + 56
        tile_w = (w - 56) / 2.0
        tile_h = 76

        # 1. Left Tile: Weather (Görsel 5 gibi: 3D Icon + 19°C + London · Cloudy)
        t1_rect = QRectF(x + 24, tile_y, tile_w, tile_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(25, 22, 38, 220)))
        p.drawRoundedRect(t1_rect, 14, 14)

        p.setFont(QFont("Noto Sans", 24))
        p.drawText(QRectF(x + 32, tile_y + 12, 44, 44), Qt.AlignmentFlag.AlignCenter, "⛅")

        p.setFont(QFont("Noto Sans", 14, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + 82, tile_y + 16, tile_w - 68, 22), Qt.AlignmentFlag.AlignLeft, self.weather_temp)

        p.setFont(QFont("Noto Sans", 8))
        p.setPen(QColor(150, 140, 170))
        p.drawText(QRectF(x + 82, tile_y + 40, tile_w - 68, 18), Qt.AlignmentFlag.AlignLeft, f"CachyOS · {self.weather_cond}")

        # 2. Right Tile: Hardware Telemetry (Görsel 5 gibi: CPU 17%, RAM 43%)
        t2_rect = QRectF(x + 32 + tile_w, tile_y, tile_w, tile_h)
        p.drawRoundedRect(t2_rect, 14, 14)

        # CPU row
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        p.setPen(QColor(160, 150, 180))
        p.drawText(QRectF(x + 44 + tile_w, tile_y + 16, 32, 16), Qt.AlignmentFlag.AlignLeft, "CPU")
        p.setBrush(QBrush(QColor(40, 35, 55)))
        p.drawRoundedRect(QRectF(x + 82 + tile_w, tile_y + 22, tile_w - 96, 6), 3, 3)
        p.setBrush(QBrush(ACCENT_CYAN))
        p.drawRoundedRect(QRectF(x + 82 + tile_w, tile_y + 22, (tile_w - 96) * (self.cpu_usage / 100.0), 6), 3, 3)
        p.drawText(QRectF(x + tile_w * 2 + 18, tile_y + 16, 36, 16), Qt.AlignmentFlag.AlignRight, f"{self.cpu_usage}%")

        # RAM row
        p.setPen(QColor(160, 150, 180))
        p.drawText(QRectF(x + 44 + tile_w, tile_y + 44, 32, 16), Qt.AlignmentFlag.AlignLeft, "RAM")
        p.setBrush(QBrush(QColor(40, 35, 55)))
        p.drawRoundedRect(QRectF(x + 82 + tile_w, tile_y + 50, tile_w - 96, 6), 3, 3)
        p.setBrush(QBrush(ACCENT_GREEN))
        p.drawRoundedRect(QRectF(x + 82 + tile_w, tile_y + 50, (tile_w - 96) * (self.ram_usage / 100.0), 6), 3, 3)
        p.drawText(QRectF(x + tile_w * 2 + 18, tile_y + 44, 36, 16), Qt.AlignmentFlag.AlignRight, f"{self.ram_usage}%")

        # 3. Bottom Row: KDE Connect Phone Battery & Bluetooth Headset Battery!
        b_card_y = tile_y + tile_h + 10
        b_card_rect = QRectF(x + 24, b_card_y, w - 48, 54)
        p.setBrush(QBrush(QColor(22, 19, 34, 220)))
        p.drawRoundedRect(b_card_rect, 12, 12)

        # Phone Section (Left)
        p.setFont(QFont("Noto Sans", 16))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + 36, b_card_y + 10, 32, 34), Qt.AlignmentFlag.AlignCenter, "📱")

        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        p.drawText(QRectF(x + 72, b_card_y + 10, 130, 18), Qt.AlignmentFlag.AlignLeft, self.phone_name[:18])

        p.setFont(QFont("Noto Sans", 8))
        phone_pct_str = f"%{self.phone_charge}" if self.phone_charge >= 0 else "Bağlı Değil"
        if self.phone_charging:
            phone_pct_str += " ⚡ Şarj Oluyor"
        p.setPen(ACCENT_GREEN if self.phone_charge > 20 else QColor(255, 77, 109))
        p.drawText(QRectF(x + 72, b_card_y + 28, 130, 16), Qt.AlignmentFlag.AlignLeft, phone_pct_str)

        # Headset Section (Right)
        mid_x = x + w / 2.0
        p.setPen(QPen(QColor(60, 50, 80, 80), 1))
        p.drawLine(int(mid_x), int(b_card_y + 8), int(mid_x), int(b_card_y + 46))

        p.setFont(QFont("Noto Sans", 16))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(mid_x + 14, b_card_y + 10, 32, 34), Qt.AlignmentFlag.AlignCenter, "🎧")

        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        headset_lbl = self.headset_name if self.headset_name else "Galaxy Buds2"
        p.drawText(QRectF(mid_x + 50, b_card_y + 10, 130, 18), Qt.AlignmentFlag.AlignLeft, headset_lbl[:18])

        p.setFont(QFont("Noto Sans", 8))
        headset_pct_str = f"%{self.headset_battery}" if self.headset_battery >= 0 else ("Bağlı" if self.headset_name else "Bağlı Değil")
        p.setPen(ACCENT_GREEN if self.headset_battery > 20 else (ACCENT_LIGHT if self.headset_battery >= 0 else QColor(140, 130, 160)))
        p.drawText(QRectF(mid_x + 50, b_card_y + 28, 130, 16), Qt.AlignmentFlag.AlignLeft, headset_pct_str)
