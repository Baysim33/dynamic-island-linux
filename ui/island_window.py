"""
Robo Island — Unified Apple iPhone 14/15 Dynamic Island + Quick Control Panel
Combines:
  1. Default Resting Mode (iPhone Notch / Dynamic Island):
     - Sits flush at top center of main 240Hz monitor
     - AI Robot Eyes (RoboFace: blinking, breathing, reacting to tasks)
     - Compact Spotify Now Playing pill + dancing visualizer bars
     - Ash Wind Particle transition on track change
     - 100% Click-Through: mouse clicks pass directly through to windows behind!
  2. Quick Control Panel (Hızlı Panel - Hotkey ile Açılan):
     - Triggered by Ctrl+Alt+Space (or Ctrl+Alt+` / Ctrl+Alt+P / CLI --toggle-panel)
     - Notch smoothly expands downwards into an Apple Control Center-style panel
     - Click-Through is disabled (fully interactive)
     - Robo AI Assistant status & header
     - Media controls: Album art, Title, Artist, Prev (⏮), Play/Pause (▶/⏸), Next (⏭)
     - Interactive volume slider (drag/click to adjust PulseAudio/PipeWire volume)
     - Quick system toggles: Night Light (🌙), GameMode (⚡), Mute (🔇), Close (✕)
     - Pressing Escape, clicking [✕], clicking outside, or pressing hotkey again collapses back to Notch & click-through!
"""
import os
import re
import subprocess
import ctypes
import time
import shiboken6
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont,
                            QPixmap, QGuiApplication, QLinearGradient, QCursor)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal

from graphics.ash_particles import AshCoverCanvas
from ui.visualizer import MiniVisualizer
from ui.robo_face import RoboFace

LIB_LAYERSHELL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "liblayershell_helper.so"
)

# ── Modes ─────────────────────────────────────────────────────────────────────
MODE_HIDDEN          = 0
MODE_IDLE            = 1   # Notch: Sleeping/idle Robo eyes
MODE_MUSIC_COMPACT   = 2   # Notch: Spotify track + dancing visualizer
MODE_MUSIC_EXPANDED  = 3   # Notch: Ash wind particle track change
MODE_TASK_RUNNING    = 4   # Notch: Active AI task (cyan spinning eyes)
MODE_TASK_DONE       = 5   # Notch: Task completed (green happy eyes)
MODE_TASK_WAITING    = 6   # Notch: Waiting for approval (amber alert eyes)
MODE_GREETING        = 7   # Notch: "Hi, I'm Robo!"
MODE_QUICK_PANEL     = 8   # Expanded Interactive Control Panel!

MODE_DIMS = {
    MODE_HIDDEN:         (0,    0),
    MODE_IDLE:           (160,  38),
    MODE_MUSIC_COMPACT:  (240,  38),
    MODE_MUSIC_EXPANDED: (440, 110),
    MODE_TASK_RUNNING:   (280,  44),
    MODE_TASK_DONE:      (280,  44),
    MODE_TASK_WAITING:   (300,  48),
    MODE_GREETING:       (210,  42),
    MODE_QUICK_PANEL:    (480, 255),
}

ACCENT       = QColor(146, 110, 228)        # #926ee4
ACCENT_LIGHT = QColor(180, 150, 250)        # #b496fa
ACCENT_CYAN  = QColor(0,   200, 255)
BG_NOTCH     = QColor(11,  11,  16,  252)   # iPhone matte black
BG_PANEL     = QColor(13,  12,  22,  250)


class DynamicIsland(QWidget):
    """Unified Dynamic Island & Quick Control Panel for KDE Wayland."""

    def __init__(self, target_screen_name: str = "HDMI-A-1", parent=None):
        super().__init__(parent)
        self.target_screen_name = target_screen_name

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        # Canvas bounds (large enough for expanded panel)
        self.canvas_width  = 540
        self.canvas_height = 290
        self.setFixedSize(self.canvas_width, self.canvas_height)

        # ── Animated pill dimensions ──────────────────────────────────────
        self._pill_width  = 0.0
        self._pill_height = 0.0
        self.target_width  = 0.0
        self.target_height = 0.0
        self.current_mode  = MODE_IDLE
        self._previous_mode = MODE_IDLE

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

        # ── System states ─────────────────────────────────────────────────
        self.system_volume = 50   # 0 - 100 %
        self.is_muted = False
        self.night_light_on = False
        self.gamemode_on = False

        # ── Task state ────────────────────────────────────────────────────
        self._task_label   = ""
        self._task_dots    = 0
        self._greeting_done = False

        # ── Sub-widgets ───────────────────────────────────────────────────
        self.cover_canvas = AshCoverCanvas(size=84, parent=self)
        self.cover_canvas.setGeometry(16, 12, 144, 84)
        self.cover_canvas.hide()

        self.visualizer = MiniVisualizer(bars_count=4, bar_color=QColor(29, 185, 84), parent=self)
        self.visualizer.hide()

        self.robo = RoboFace()

        # ── Timers ────────────────────────────────────────────────────────
        # Spring animation physics (7ms ~ 144-240fps)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(7)
        self.anim_timer.timeout.connect(self._step_dimensions)
        self.anim_timer.start()

        # 60fps render tick for animated eyes & visualizer
        self.robo_timer = QTimer(self)
        self.robo_timer.setInterval(16)
        self.robo_timer.timeout.connect(self.update)
        self.robo_timer.start()

        # Song change auto-collapse (4.5s)
        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.setInterval(4500)
        self.collapse_timer.timeout.connect(self._on_collapse_timeout)

        # Task done auto-dismiss (4s)
        self.task_done_timer = QTimer(self)
        self.task_done_timer.setSingleShot(True)
        self.task_done_timer.setInterval(4000)
        self.task_done_timer.timeout.connect(self._on_task_done_timeout)

        # Animated dots timer
        self.dots_timer = QTimer(self)
        self.dots_timer.setInterval(500)
        self.dots_timer.timeout.connect(self._step_dots)

        # System telemetry sync timer (volume, mute)
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(2000)
        self.sync_timer.timeout.connect(self._sync_system_telemetry)
        self.sync_timer.start()
        self._sync_system_telemetry()

        # ── LayerShell Setup ──────────────────────────────────────────────
        self._layershell_ok = False
        self.update_screen_position(target_screen_name)
        self.show()

        # Enable click-through initially (so resting notch doesn't block clicks)
        self.set_click_through(True)

        # Show initial greeting
        QTimer.singleShot(800, self._show_greeting)

    # ── LayerShell & Click-Through C++ Integration ────────────────────────────

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
            # AnchorTop = 1, exclusive_zone = 0 (overlay)
            ok = lib.setup_layershell_window(ptr_wh, ptr_sc, self.canvas_width, self.canvas_height, 1, 0)
            self._layershell_ok = ok
            return ok
        except Exception as e:
            print(f"[DynamicIsland] LayerShell error: {e}")
            return False

    def set_click_through(self, enable: bool):
        """
        True  → Input region is empty: all clicks pass through to background.
        False → Input region is full: island receives clicks interactively.
        """
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
        except Exception as e:
            print(f"[DynamicIsland] set_click_through error: {e}")

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

    # ── Hotkey / Quick Control Panel Toggle ───────────────────────────────────

    def toggle_quick_panel(self):
        """Called by hotkey (Ctrl+Alt+Space) or CLI --toggle-panel"""
        if self.current_mode == MODE_QUICK_PANEL:
            self.close_quick_panel()
        else:
            self.open_quick_panel()

    def open_quick_panel(self):
        self._previous_mode = self.current_mode
        self._sync_system_telemetry()
        self.set_mode(MODE_QUICK_PANEL)
        self.set_click_through(False)  # INTERACTION ACTIVE!
        self.update()
        print("[DynamicIsland] Quick Control Panel OPENED (Interactive)")

    def close_quick_panel(self):
        self.set_click_through(True)   # CLICK-THROUGH RESTORED!
        if self.is_playing:
            self.set_mode(MODE_MUSIC_COMPACT)
        else:
            self._enter_idle()
        self.update()
        print("[DynamicIsland] Quick Control Panel CLOSED (Click-Through)")

    # ── System Telemetry (Volume, Mute, Night Light) ──────────────────────────

    def _sync_system_telemetry(self):
        # 1. Volume
        try:
            res = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                                 capture_output=True, text=True, timeout=0.4)
            m = re.search(r'(\d+)%', res.stdout)
            if m:
                self.system_volume = int(m.group(1))
        except Exception:
            pass

        # 2. Mute
        try:
            res = subprocess.run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
                                 capture_output=True, text=True, timeout=0.4)
            self.is_muted = ("yes" in res.stdout.lower())
        except Exception:
            pass

        # 3. Night Light
        try:
            res = subprocess.run([
                "qdbus6", "org.kde.KWin", "/org/kde/KWin/NightLight",
                "org.kde.KWin.NightLight.running"
            ], capture_output=True, text=True, timeout=0.4)
            self.night_light_on = (res.stdout.strip() == "true")
        except Exception:
            pass

    def _set_volume(self, pct: int):
        pct = max(0, min(100, pct))
        self.system_volume = pct
        self.is_muted = False
        try:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"], timeout=0.4)
        except Exception:
            pass
        self.update()

    def _toggle_mute(self):
        try:
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], timeout=0.4)
            self.is_muted = not self.is_muted
        except Exception:
            pass
        self.update()

    def _toggle_night_light(self):
        try:
            # KDE 6 NightLight preview/toggle
            if self.night_light_on:
                subprocess.run(["qdbus6", "org.kde.KWin", "/org/kde/KWin/NightLight", "stopPreview"], timeout=0.4)
                self.night_light_on = False
            else:
                subprocess.run(["qdbus6", "org.kde.KWin", "/org/kde/KWin/NightLight", "preview", "4500"], timeout=0.4)
                self.night_light_on = True
        except Exception:
            pass
        self.update()

    def _toggle_gamemode(self):
        self.gamemode_on = not self.gamemode_on
        try:
            status_text = "Aktif ⚡" if self.gamemode_on else "Pasif"
            subprocess.run(["notify-send", "-a", "RoboIsland", "GameMode", f"Performans Modu {status_text}"], timeout=0.4)
        except Exception:
            pass
        self.update()

    # ── Spotify Media Callbacks ───────────────────────────────────────────────

    def on_playback_status(self, status: str):
        self.is_playing = (status == "Playing")
        self.visualizer.set_playing(self.is_playing)

        if self.current_mode == MODE_QUICK_PANEL:
            self.update()
            return

        if self.current_mode in (MODE_TASK_RUNNING, MODE_TASK_WAITING):
            return

        if not self.is_playing and self.current_mode not in (MODE_MUSIC_EXPANDED, MODE_TASK_DONE):
            self._enter_idle()
        elif self.is_playing and self.current_mode in (MODE_HIDDEN, MODE_IDLE):
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
                22, 22,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            self.cover_pixmap = None
            self.mini_cover_pixmap = None

        if not new_pixmap.isNull():
            self.cover_canvas.transition_to(new_pixmap)

        if self.current_mode == MODE_QUICK_PANEL:
            self.update()
            return

        if self.current_mode in (MODE_TASK_RUNNING, MODE_TASK_WAITING):
            return

        # Trigger Ash Wind Particle Expansion
        self.set_mode(MODE_MUSIC_EXPANDED)
        self.collapse_timer.start()

    # ── Task Callbacks ────────────────────────────────────────────────────────

    def on_task_started(self, message: str):
        self._task_label = message
        self._task_dots  = 0
        self.collapse_timer.stop()
        self.task_done_timer.stop()
        self.dots_timer.start()
        if self.current_mode != MODE_QUICK_PANEL:
            self.set_mode(MODE_TASK_RUNNING)

    def on_task_done(self, message: str):
        self._task_label = message
        self.dots_timer.stop()
        if self.current_mode != MODE_QUICK_PANEL:
            self.set_mode(MODE_TASK_DONE)
            self.task_done_timer.start()

    def on_task_waiting(self, message: str):
        self._task_label = message
        self.dots_timer.stop()
        if self.current_mode != MODE_QUICK_PANEL:
            self.set_mode(MODE_TASK_WAITING)

    def on_task_cancelled(self):
        self._task_label = ""
        self.dots_timer.stop()
        self.task_done_timer.stop()
        if self.current_mode != MODE_QUICK_PANEL:
            self._enter_idle()

    # ── Mode Management ───────────────────────────────────────────────────────

    def set_mode(self, mode: int):
        self.current_mode = mode
        tw, th = MODE_DIMS.get(mode, (160, 38))
        self.target_width  = float(tw)
        self.target_height = float(th)

        # Update Robo Eyes
        if mode == MODE_IDLE:
            self.robo.set_state("idle")
        elif mode == MODE_TASK_RUNNING:
            self.robo.set_state("active")
        elif mode == MODE_TASK_DONE:
            self.robo.set_state("happy")
        elif mode == MODE_TASK_WAITING:
            self.robo.set_state("alert")
        elif mode in (MODE_GREETING, MODE_QUICK_PANEL):
            self.robo.set_state("happy")

        # Sub-widgets
        show_cover = (mode == MODE_MUSIC_EXPANDED)
        show_viz   = (mode in (MODE_MUSIC_COMPACT, MODE_MUSIC_EXPANDED))
        self.cover_canvas.setVisible(show_cover)
        self.visualizer.setVisible(show_viz)

        if not self.isVisible():
            self.show()
            self.raise_()

    def _enter_idle(self):
        self.robo.set_state("sleeping")
        self.set_mode(MODE_IDLE)

    def _show_greeting(self):
        if self._greeting_done:
            return
        self._greeting_done = True
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

    def _on_task_done_timeout(self):
        if self.current_mode == MODE_QUICK_PANEL:
            return
        if self.is_playing:
            self.set_mode(MODE_MUSIC_COMPACT)
        else:
            self._enter_idle()

    def _step_dots(self):
        self._task_dots = (self._task_dots + 1) % 4
        self.update()

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

    # ── Mouse Interaction (Active only in Quick Panel) ────────────────────────

    def mousePressEvent(self, event):
        if self.current_mode != MODE_QUICK_PANEL:
            super().mousePressEvent(event)
            return

        pos = event.position()
        cx = self.width() / 2.0
        x  = cx - self._pill_width / 2.0
        y  = 0.0
        w  = self._pill_width
        h  = self._pill_height

        # 1. Close Button [✕] (top right)
        close_rect = QRectF(x + w - 38, y + 10, 26, 26)
        if close_rect.contains(pos):
            self.close_quick_panel()
            event.accept()
            return

        # 2. Media Controls: Prev, Play/Pause, Next
        prev_rect = QRectF(x + 230, y + 84, 32, 32)
        play_rect = QRectF(x + 272, y + 80, 40, 40)
        next_rect = QRectF(x + 322, y + 84, 32, 32)

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

        # 3. Volume Slider Drag / Click
        vol_track_rect = QRectF(x + 50, y + 148, w - 120, 16)
        if vol_track_rect.contains(pos):
            self._is_dragging_volume = True
            norm = (pos.x() - (x + 50)) / (w - 120)
            self._set_volume(int(norm * 100))
            event.accept()
            return

        # 4. Quick Toggles
        # 🌙 Night Light
        nl_rect = QRectF(x + 40, y + 195, 120, 36)
        if nl_rect.contains(pos):
            self._toggle_night_light()
            event.accept()
            return

        # ⚡ GameMode
        gm_rect = QRectF(x + 180, y + 195, 120, 36)
        if gm_rect.contains(pos):
            self._toggle_gamemode()
            event.accept()
            return

        # 🔇 Mute
        mu_rect = QRectF(x + 320, y + 195, 120, 36)
        if mu_rect.contains(pos):
            self._toggle_mute()
            event.accept()
            return

        # Clicking outside the panel card → close panel!
        panel_rect = QRectF(x, y, w, h)
        if not panel_rect.contains(pos):
            self.close_quick_panel()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._hover_pos = event.position()
        if self.current_mode == MODE_QUICK_PANEL and self._is_dragging_volume:
            cx = self.width() / 2.0
            x  = cx - self._pill_width / 2.0
            w  = self._pill_width
            norm = (event.position().x() - (x + 50)) / (w - 120)
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

        # Apple notch / dynamic island radius
        radius = min(h / 2.0, 24.0)
        pill_rect = QRectF(x, y, w, h)

        # ── 1. Background Pill Drawing ────────────────────────────────────
        if mode == MODE_QUICK_PANEL:
            # Control Center Glassmorphism
            grad = QLinearGradient(x, y, x, y + h)
            grad.setColorAt(0.0, QColor(16, 14, 26, 252))
            grad.setColorAt(1.0, QColor(10, 10, 18, 252))
            p.setPen(QPen(QColor(146, 110, 228, 160), 1.4))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(pill_rect, radius, radius)
            self._paint_quick_panel(p, x, y, w, h)

        else:
            # iPhone Dynamic Island Notch Pill
            p.setPen(QPen(QColor(146, 110, 228, 90), 1.2))
            p.setBrush(QBrush(BG_NOTCH))
            p.drawRoundedRect(pill_rect, radius, radius)

            if mode == MODE_IDLE and self._pill_width > 60:
                self._paint_idle(p, x, y, w, h)
            elif mode == MODE_MUSIC_COMPACT and self._pill_width > 120:
                self._paint_music_compact(p, x, y, w, h)
            elif mode == MODE_MUSIC_EXPANDED and self._pill_width > 300:
                self._paint_music_expanded(p, x, y, w, h)
            elif mode in (MODE_TASK_RUNNING, MODE_TASK_DONE, MODE_TASK_WAITING) and self._pill_width > 160:
                self._paint_task(p, x, y, w, h, mode)
            elif mode == MODE_GREETING and self._pill_width > 120:
                self._paint_greeting(p, x, y, w, h)

        p.end()

    # ── Paint: Quick Control Panel (Hızlı Panel) ──────────────────────────────

    def _paint_quick_panel(self, p: QPainter, x, y, w, h):
        mx = self._hover_pos.x()
        my = self._hover_pos.y()

        # ── Header: Robo Face + Title + Close Button [✕] ──────────────────
        self.robo.draw(p, x + 30, y + 24, eye_w=12, eye_h=8)

        p.setFont(QFont("Noto Sans", 10, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + 50, y + 14, 200, 20), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Robo Asistan")

        p.setFont(QFont("Noto Sans", 8))
        p.setPen(ACCENT_LIGHT)
        status_txt = self._task_label if self._task_label else ("Müzik Çalıyor" if self.is_playing else "Hazır • Çentik Aktif")
        p.drawText(QRectF(x + 145, y + 15, 200, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"• {status_txt}")

        # Close button [✕]
        close_rect = QRectF(x + w - 38, y + 10, 24, 24)
        close_hover = close_rect.contains(mx, my)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 77, 109, 220) if close_hover else QColor(40, 35, 55, 180)))
        p.drawRoundedRect(close_rect, 6, 6)
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(close_rect, Qt.AlignmentFlag.AlignCenter, "✕")

        # Divider line
        p.setPen(QPen(QColor(80, 70, 110, 70), 1.0))
        p.drawLine(int(x + 20), int(y + 44), int(x + w - 20), int(y + 44))

        # ── Media Player Section (y: 52..136) ─────────────────────────────
        # Album Art
        art_rect = QRectF(x + 24, y + 54, 70, 70)
        p.setPen(QPen(QColor(146, 110, 228, 90), 1.0))
        if self.cover_pixmap and not self.cover_pixmap.isNull():
            p.setBrush(QBrush(self.cover_pixmap.scaled(70, 70, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)))
        else:
            p.setBrush(QBrush(QColor(25, 22, 38)))
        p.drawRoundedRect(art_rect, 10, 10)

        # Track info
        p.setFont(QFont("Noto Sans", 11, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        title = self.title_text if self.title_text else "Müzik Çalmıyor"
        p.drawText(QRectF(x + 106, y + 56, w - 120, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title[:30])

        p.setFont(QFont("Noto Sans", 9))
        p.setPen(ACCENT_LIGHT)
        artist = self.artist_text if self.artist_text else "Spotify / Medya Oynatıcı"
        p.drawText(QRectF(x + 106, y + 78, w - 120, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, artist[:34])

        # Media Buttons: Previous (⏮), Play/Pause (▶ / ⏸), Next (⏭)
        prev_rect = QRectF(x + 106, y + 100, 32, 28)
        play_rect = QRectF(x + 146, y + 98, 44, 32)
        next_rect = QRectF(x + 198, y + 100, 32, 28)

        prev_hover = prev_rect.contains(mx, my)
        play_hover = play_rect.contains(mx, my)
        next_hover = next_rect.contains(mx, my)

        # Prev
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(146, 110, 228, 60) if prev_hover else QColor(30, 25, 45, 140)))
        p.drawRoundedRect(prev_rect, 6, 6)
        p.setFont(QFont("Noto Sans", 12))
        p.setPen(QColor(255, 255, 255))
        p.drawText(prev_rect, Qt.AlignmentFlag.AlignCenter, "⏮")

        # Play/Pause
        p.setBrush(QBrush(QColor(180, 150, 250) if play_hover else ACCENT))
        p.drawRoundedRect(play_rect, 8, 8)
        p.setFont(QFont("Noto Sans", 14))
        p.setPen(QColor(10, 10, 16))
        p.drawText(play_rect, Qt.AlignmentFlag.AlignCenter, "⏸" if self.is_playing else "▶")

        # Next
        p.setBrush(QBrush(QColor(146, 110, 228, 60) if next_hover else QColor(30, 25, 45, 140)))
        p.drawRoundedRect(next_rect, 6, 6)
        p.setFont(QFont("Noto Sans", 12))
        p.setPen(QColor(255, 255, 255))
        p.drawText(next_rect, Qt.AlignmentFlag.AlignCenter, "⏭")

        # ── Volume Slider Bar (y: 142..174) ───────────────────────────────
        vol_x = x + 48
        vol_y = y + 154
        vol_w = w - 110
        vol_h = 6

        p.setFont(QFont("Noto Sans", 10))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x + 22, vol_y - 8, 24, 20), Qt.AlignmentFlag.AlignCenter, "🔇" if self.is_muted else "🔉")

        # Slider background track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(40, 35, 55)))
        p.drawRoundedRect(QRectF(vol_x, vol_y, vol_w, vol_h), 3, 3)

        # Filled volume track
        fill_w = vol_w * (self.system_volume / 100.0) if not self.is_muted else 0
        p.setBrush(QBrush(ACCENT))
        p.drawRoundedRect(QRectF(vol_x, vol_y, fill_w, vol_h), 3, 3)

        # Handle knob
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(QRectF(vol_x + fill_w - 6, vol_y - 4, 14, 14))

        # Percentage text
        p.setFont(QFont("Noto Sans", 8, QFont.Weight.Bold))
        p.setPen(QColor(200, 190, 230))
        vol_str = "MUTED" if self.is_muted else f"{self.system_volume}%"
        p.drawText(QRectF(vol_x + vol_w + 10, vol_y - 7, 44, 20), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, vol_str)

        # ── Quick System Toggles (y: 190..232) ────────────────────────────
        btn_y = y + 192
        btn_w = (w - 60) / 3.0
        btn_h = 36

        # 1. 🌙 Gece Işığı
        b1_rect = QRectF(x + 20, btn_y, btn_w, btn_h)
        b1_hover = b1_rect.contains(mx, my)
        b1_bg = ACCENT if self.night_light_on else (QColor(146, 110, 228, 50) if b1_hover else QColor(25, 20, 38, 200))
        p.setPen(QPen(ACCENT, 1) if self.night_light_on else QPen(QColor(80, 70, 110, 90), 1))
        p.setBrush(QBrush(b1_bg))
        p.drawRoundedRect(b1_rect, 8, 8)
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Bold))
        p.setPen(QColor(10, 10, 16) if self.night_light_on else QColor(240, 240, 255))
        p.drawText(b1_rect, Qt.AlignmentFlag.AlignCenter, "🌙 Gece Işığı")

        # 2. ⚡ GameMode
        b2_rect = QRectF(x + 20 + btn_w + 10, btn_y, btn_w, btn_h)
        b2_hover = b2_rect.contains(mx, my)
        b2_bg = ACCENT_CYAN if self.gamemode_on else (QColor(0, 200, 255, 50) if b2_hover else QColor(25, 20, 38, 200))
        p.setPen(QPen(ACCENT_CYAN, 1) if self.gamemode_on else QPen(QColor(80, 70, 110, 90), 1))
        p.setBrush(QBrush(b2_bg))
        p.drawRoundedRect(b2_rect, 8, 8)
        p.setPen(QColor(10, 10, 16) if self.gamemode_on else ACCENT_CYAN)
        p.drawText(b2_rect, Qt.AlignmentFlag.AlignCenter, "⚡ Performans")

        # 3. 🔇 Sessize Al
        b3_rect = QRectF(x + 20 + (btn_w + 10) * 2, btn_y, btn_w, btn_h)
        b3_hover = b3_rect.contains(mx, my)
        b3_bg = QColor(255, 77, 109, 200) if self.is_muted else (QColor(146, 110, 228, 50) if b3_hover else QColor(25, 20, 38, 200))
        p.setPen(QPen(QColor(255, 77, 109), 1) if self.is_muted else QPen(QColor(80, 70, 110, 90), 1))
        p.setBrush(QBrush(b3_bg))
        p.drawRoundedRect(b3_rect, 8, 8)
        p.setPen(QColor(255, 255, 255))
        mute_label = "🔊 Sesi Aç" if self.is_muted else "🔇 Sessize Al"
        p.drawText(b3_rect, Qt.AlignmentFlag.AlignCenter, mute_label)

    # ── Paint: Notch Modes (Compact Resting States) ───────────────────────────

    def _paint_idle(self, p: QPainter, x, y, w, h):
        """iPhone Notch with animated sleeping/idle Robo eyes."""
        self.robo.draw(p, x + w / 2.0, y + h / 2.0, eye_w=12, eye_h=8)

    def _paint_music_compact(self, p: QPainter, x, y, w, h):
        """Compact Apple Island with Album / Spotify icon + Track + Dancing Visualizer."""
        if self.mini_cover_pixmap:
            icon_rect = QRectF(x + 10, y + (h - 22) / 2.0, 22, 22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self.mini_cover_pixmap))
            p.drawRoundedRect(icon_rect, 11, 11)
        else:
            p.setFont(QFont("Noto Sans", 11, QFont.Weight.Bold))
            p.setPen(QColor(29, 185, 84))
            p.drawText(QRectF(x + 10, y + 4, 20, 20), Qt.AlignmentFlag.AlignCenter, "●")

        # Title
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.DemiBold))
        p.setPen(QColor(240, 240, 248))
        text_rect = QRectF(x + 38, y + (h - 18) / 2.0, w - 74, 18)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title_text[:22])

        # Visualizer
        self.visualizer.move(int(x + w - 30), int(y + (h - 18) / 2.0))

    def _paint_music_expanded(self, p: QPainter, x, y, w, h):
        """Expanded track change with Ash Wind particle disintegration."""
        text_x = x + 116
        text_w = w - 150

        p.setFont(QFont("Noto Sans", 11, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(text_x, y + 16, text_w, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title_text[:28])

        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Medium))
        p.setPen(ACCENT_LIGHT)
        p.drawText(QRectF(text_x, y + 40, text_w, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.artist_text[:32])

        if self.album_text:
            p.setFont(QFont("Noto Sans", 8))
            p.setPen(QColor(140, 140, 165))
            p.drawText(QRectF(text_x, y + 60, text_w, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.album_text[:34])

        self.visualizer.move(int(x + w - 34), int(y + 16))
        self.cover_canvas.move(int(x + 14), int(y + 13))

    def _paint_task(self, p: QPainter, x, y, w, h, mode):
        """Active AI task in the notch."""
        eye_w = w * 0.35
        self.robo.draw(p, x + eye_w / 2.0, y + h / 2.0, eye_w=12, eye_h=8)

        # Divider
        p.setPen(QPen(QColor(80, 80, 120, 80), 1.0))
        lx = int(x + eye_w)
        p.drawLine(lx, int(y + 8), lx, int(y + h - 8))

        label = self._task_label
        if mode == MODE_TASK_RUNNING:
            label = (label[:20] + "…") if len(label) > 20 else label
            label += "." * self._task_dots
        elif mode == MODE_TASK_DONE:
            label = "✓ " + label[:22]
        elif mode == MODE_TASK_WAITING:
            label = "⚠ " + label[:20]

        icon_col = {
            MODE_TASK_RUNNING: ACCENT_CYAN,
            MODE_TASK_DONE:    QColor(29, 185, 84),
            MODE_TASK_WAITING: QColor(230, 170, 0),
        }.get(mode, QColor(200, 200, 220))

        p.setFont(QFont("Noto Sans", 8, QFont.Weight.Bold))
        p.setPen(icon_col)
        p.drawText(QRectF(x + eye_w + 10, y + (h - 18) / 2.0, w - eye_w - 16, 18),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

    def _paint_greeting(self, p: QPainter, x, y, w, h):
        """Startup greeting in notch."""
        self.robo.draw(p, x + w * 0.28, y + h / 2.0, eye_w=13, eye_h=9)
        p.setFont(QFont("Noto Sans", 10, QFont.Weight.Bold))
        p.setPen(ACCENT_LIGHT)
        p.drawText(QRectF(x + w * 0.46, y + (h - 20) / 2.0, w * 0.50, 20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Hi, I'm Robo!")
