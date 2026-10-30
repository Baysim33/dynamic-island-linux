"""
Robo Island — Dynamic Island with AI Robot Face + Spotify + Task Monitoring.
Extends the original Spotify-Island with:
  - Robot face (animated eyes) for idle/task states
  - Task modes: TASK_RUNNING, TASK_DONE, TASK_WAITING
  - Greeting animation on first launch
  - All original Spotify compact/expanded modes preserved
"""
import os
import subprocess
import ctypes
import time
import shiboken6
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont,
                             QPixmap, QGuiApplication, QLinearGradient)
from PySide6.QtCore import Qt, QTimer, QRectF, Signal

from graphics.ash_particles import AshCoverCanvas
from ui.visualizer import MiniVisualizer
from ui.robo_face import RoboFace

LIB_LAYERSHELL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "liblayershell_helper.so"
)

# ── Display mode constants ────────────────────────────────────────────────────
MODE_HIDDEN          = 0
MODE_IDLE            = 1   # Robo face — idle / sleeping
MODE_MUSIC_COMPACT   = 2   # Compact Spotify pill
MODE_MUSIC_EXPANDED  = 3   # Expanded Spotify + ash particles
MODE_TASK_RUNNING    = 4   # Robo active eyes + task label
MODE_TASK_DONE       = 5   # Robo happy eyes + done message
MODE_TASK_WAITING    = 6   # Robo alert eyes + waiting message
MODE_GREETING        = 7   # "Hi, I'm Robo" wink

# Target dimensions per mode
MODE_DIMS = {
    MODE_HIDDEN:         (0,    0),
    MODE_IDLE:           (140,  40),
    MODE_MUSIC_COMPACT:  (210,  36),
    MODE_MUSIC_EXPANDED: (440, 110),
    MODE_TASK_RUNNING:   (280,  48),
    MODE_TASK_DONE:      (300,  48),
    MODE_TASK_WAITING:   (300,  52),
    MODE_GREETING:       (200,  44),
}


class DynamicIsland(QWidget):
    """Robo Island main window — all rendering lives here."""

    # Expose old constants for backward compat with main.py
    MODE_HIDDEN   = MODE_HIDDEN
    MODE_COMPACT  = MODE_MUSIC_COMPACT
    MODE_EXPANDED = MODE_MUSIC_EXPANDED

    def __init__(self, target_screen_name: str = "HDMI-A-2", parent=None):
        super().__init__(parent)
        self.target_screen_name = target_screen_name

        # Qt window setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Canvas — large enough for biggest mode
        self.canvas_width  = 480
        self.canvas_height = 130
        self.setFixedSize(self.canvas_width, self.canvas_height)

        # ── Animated pill dimensions ──────────────────────────────────────
        self._pill_width  = 0.0
        self._pill_height = 0.0
        self.target_width  = 0.0
        self.target_height = 0.0
        self.current_mode  = MODE_HIDDEN

        # ── Spotify track state ───────────────────────────────────────────
        self.title_text  = ""
        self.artist_text = ""
        self.album_text  = ""
        self.is_playing  = False
        self.mini_cover_pixmap: QPixmap | None = None

        # ── Task state ────────────────────────────────────────────────────
        self._task_label   = ""
        self._task_entered = 0.0     # time.perf_counter() when task mode started
        self._task_dots    = 0       # animated ellipsis counter
        self._task_progress = 0.0   # 0.0-1.0 (future use)

        # ── Greeting state ────────────────────────────────────────────────
        self._greeting_done = False

        # ── Sub-widgets ───────────────────────────────────────────────────
        self.cover_canvas = AshCoverCanvas(size=84, parent=self)
        self.cover_canvas.setGeometry(16, 12, 144, 84)
        self.cover_canvas.hide()

        self.visualizer = MiniVisualizer(
            bars_count=4, bar_color=QColor(29, 185, 84), parent=self
        )
        self.visualizer.hide()

        self.robo = RoboFace()

        # ── Timers ────────────────────────────────────────────────────────
        # Physics spring (7ms ≈ 143fps, fine for 240Hz)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(7)
        self.anim_timer.timeout.connect(self._step_dimensions)
        self.anim_timer.start()

        # Repaint for robo eye animation when in robo modes
        self.robo_timer = QTimer(self)
        self.robo_timer.setInterval(16)   # ~60fps eye updates
        self.robo_timer.timeout.connect(self.update)
        self.robo_timer.start()

        # Auto-collapse after expanded music mode
        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.setInterval(4500)
        self.collapse_timer.timeout.connect(self._on_collapse_timeout)

        # Task-done auto-dismiss after 4s
        self.task_done_timer = QTimer(self)
        self.task_done_timer.setSingleShot(True)
        self.task_done_timer.setInterval(4000)
        self.task_done_timer.timeout.connect(self._on_task_done_timeout)

        # Animated dots for task label ("running…")
        self.dots_timer = QTimer(self)
        self.dots_timer.setInterval(550)
        self.dots_timer.timeout.connect(self._step_dots)

        # Anchor to screen top
        self.update_screen_position(target_screen_name)

        # Show greeting after 800ms warm-up
        QTimer.singleShot(800, self._show_greeting)

    # ── LayerShell / positioning ─────────────────────────────────────────────

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
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int
            ]
            lib.setup_layershell_window.restype = ctypes.c_bool
            ptr_wh     = shiboken6.getCppPointer(wh)[0]
            ptr_screen = shiboken6.getCppPointer(target_screen)[0] if target_screen else 0
            return lib.setup_layershell_window(
                ptr_wh, ptr_screen, self.canvas_width, self.canvas_height
            )
        except Exception as e:
            print(f"[RoboIsland] LayerShell setup error: {e}")
            return False

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

    # ── Spotify callbacks ────────────────────────────────────────────────────

    def on_playback_status(self, status: str):
        self.is_playing = (status == "Playing")
        self.visualizer.set_playing(self.is_playing)

        # Don't interrupt task modes with music state changes
        if self.current_mode in (MODE_TASK_RUNNING, MODE_TASK_WAITING):
            return

        if not self.is_playing and self.current_mode not in (
            MODE_MUSIC_EXPANDED, MODE_TASK_DONE
        ):
            self._enter_idle()
        elif self.is_playing and self.current_mode in (MODE_HIDDEN, MODE_IDLE):
            self.set_mode(MODE_MUSIC_COMPACT)

    def on_track_changed(self, track_info: dict):
        self.title_text  = track_info.get("title",  "")
        self.artist_text = track_info.get("artist", "")
        self.album_text  = track_info.get("album",  "")
        cover_path = track_info.get("cover_path", "")

        new_pixmap = QPixmap()
        if cover_path and os.path.exists(cover_path):
            new_pixmap.load(cover_path)
            self.mini_cover_pixmap = new_pixmap.scaled(
                20, 20,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            self.mini_cover_pixmap = None

        if not new_pixmap.isNull():
            self.cover_canvas.transition_to(new_pixmap)

        # Don't interrupt active task modes
        if self.current_mode in (MODE_TASK_RUNNING, MODE_TASK_WAITING):
            return

        self.set_mode(MODE_MUSIC_EXPANDED)
        self.collapse_timer.start()

    # ── Task callbacks ────────────────────────────────────────────────────────

    def on_task_started(self, message: str):
        self._task_label   = message
        self._task_entered = time.perf_counter()
        self._task_dots    = 0
        self.collapse_timer.stop()
        self.task_done_timer.stop()
        self.dots_timer.start()
        self.set_mode(MODE_TASK_RUNNING)

    def on_task_done(self, message: str):
        self._task_label = message
        self.dots_timer.stop()
        self.set_mode(MODE_TASK_DONE)
        self.task_done_timer.start()

    def on_task_waiting(self, message: str):
        self._task_label = message
        self.dots_timer.stop()
        self.set_mode(MODE_TASK_WAITING)

    def on_task_cancelled(self):
        self._task_label = ""
        self.dots_timer.stop()
        self.task_done_timer.stop()
        self._enter_idle()

    # ── Mode management ───────────────────────────────────────────────────────

    def set_mode(self, mode: int):
        self.current_mode = mode
        tw, th = MODE_DIMS.get(mode, (0, 0))
        self.target_width  = float(tw)
        self.target_height = float(th)

        # Robo face state
        if mode == MODE_IDLE:
            self.robo.set_state("idle")
        elif mode == MODE_TASK_RUNNING:
            self.robo.set_state("active")
        elif mode == MODE_TASK_DONE:
            self.robo.set_state("happy")
        elif mode == MODE_TASK_WAITING:
            self.robo.set_state("alert")
        elif mode == MODE_GREETING:
            self.robo.set_state("happy")

        # Sub-widget visibility
        show_cover = (mode == MODE_MUSIC_EXPANDED)
        show_viz   = (mode in (MODE_MUSIC_COMPACT, MODE_MUSIC_EXPANDED))
        self.cover_canvas.setVisible(show_cover)
        self.visualizer.setVisible(show_viz)

        if mode != MODE_HIDDEN and not self.isVisible():
            self.update_screen_position(self.target_screen_name)
            self.show()
            self.raise_()

    def _enter_idle(self):
        """Switch to idle robo face mode."""
        self.robo.set_state("sleeping")
        self.set_mode(MODE_IDLE)

    # ── Greeting ──────────────────────────────────────────────────────────────

    def _show_greeting(self):
        if self._greeting_done:
            return
        self._greeting_done = True
        self._task_label = "Hi, I'm Robo!"
        self.set_mode(MODE_GREETING)
        QTimer.singleShot(2800, self._after_greeting)

    def _after_greeting(self):
        self._task_label = ""
        if self.is_playing:
            self.set_mode(MODE_MUSIC_COMPACT)
        else:
            self._enter_idle()

    # ── Timers / helpers ──────────────────────────────────────────────────────

    def _on_collapse_timeout(self):
        if self.current_mode in (MODE_TASK_RUNNING, MODE_TASK_WAITING):
            return
        if self.is_playing:
            self.set_mode(MODE_MUSIC_COMPACT)
        else:
            self._enter_idle()

    def _on_task_done_timeout(self):
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
            self._pill_width  += diff_w * 0.16
            self._pill_height += diff_h * 0.16
            self.update()
        else:
            self._pill_width  = self.target_width
            self._pill_height = self.target_height
            if self.current_mode == MODE_HIDDEN and self._pill_height <= 1.0:
                self.hide()
            self.update()

    # ── Mouse interaction ─────────────────────────────────────────────────────

    def enterEvent(self, event):
        if self.collapse_timer.isActive():
            self.collapse_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.current_mode == MODE_MUSIC_EXPANDED:
            self.collapse_timer.start(2500)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.current_mode in (MODE_MUSIC_COMPACT, MODE_MUSIC_EXPANDED):
                # Spotify play/pause
                try:
                    subprocess.run([
                        "qdbus6", "org.mpris.MediaPlayer2.spotify",
                        "/org/mpris/MediaPlayer2",
                        "org.mpris.MediaPlayer2.Player.PlayPause"
                    ], timeout=1)
                except Exception:
                    pass
            elif self.current_mode == MODE_TASK_WAITING:
                # Click to dismiss wait state → done
                self.on_task_done("Onaylandı ✓")
            event.accept()
            return
        super().mousePressEvent(event)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        if self._pill_width <= 2.0 or self._pill_height <= 2.0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2.0
        x  = cx - self._pill_width / 2.0
        y  = 0.0
        w  = self._pill_width
        h  = self._pill_height
        r  = min(h / 2.0, 22.0)
        pill_rect = QRectF(x, y, w, h)

        mode = self.current_mode

        # ── Pill background ───────────────────────────────────────────────
        if mode in (MODE_TASK_RUNNING, MODE_TASK_WAITING, MODE_TASK_DONE, MODE_GREETING):
            # Subtle gradient for robo modes
            grad = QLinearGradient(x, y, x, y + h)
            grad.setColorAt(0.0, QColor(18, 14, 32, 252))
            grad.setColorAt(1.0, QColor(10, 10, 18, 252))
            border_col = {
                MODE_TASK_RUNNING: QColor(0,   200, 255, 110),
                MODE_TASK_DONE:    QColor(29,  185,  84, 110),
                MODE_TASK_WAITING: QColor(230, 170,   0, 150),
                MODE_GREETING:     QColor(146, 110, 228, 130),
            }.get(mode, QColor(146, 110, 228, 90))
            painter.setPen(QPen(border_col, 1.4))
            painter.setBrush(QBrush(grad))
        elif mode == MODE_IDLE:
            painter.setPen(QPen(QColor(80, 60, 120, 60), 1.0))
            painter.setBrush(QBrush(QColor(10, 10, 16, 200)))
        else:
            # Spotify / hidden modes — classic matte black
            painter.setPen(QPen(QColor(146, 110, 228, 90), 1.2))
            painter.setBrush(QBrush(QColor(11, 11, 16, 250)))

        painter.drawRoundedRect(pill_rect, r, r)

        # ── Mode content ──────────────────────────────────────────────────

        if mode == MODE_IDLE and self._pill_width > 60:
            self._paint_idle(painter, x, y, w, h)

        elif mode == MODE_MUSIC_COMPACT and self._pill_width > 120:
            self._paint_music_compact(painter, x, y, w, h)

        elif mode == MODE_MUSIC_EXPANDED and self._pill_width > 300:
            self._paint_music_expanded(painter, x, y, w, h)

        elif mode in (MODE_TASK_RUNNING, MODE_TASK_DONE, MODE_TASK_WAITING) \
                and self._pill_width > 160:
            self._paint_task(painter, x, y, w, h, mode)

        elif mode == MODE_GREETING and self._pill_width > 120:
            self._paint_greeting(painter, x, y, w, h)

        painter.end()

    # ── Sub-paint routines ────────────────────────────────────────────────────

    def _paint_idle(self, p: QPainter, x, y, w, h):
        """Just robo eyes, dim, sleepy."""
        eye_cx = x + w / 2
        eye_cy = y + h / 2
        self.robo.draw(p, eye_cx, eye_cy, eye_w=11, eye_h=7)

    def _paint_music_compact(self, p: QPainter, x, y, w, h):
        # Mini cover / green dot
        if self.mini_cover_pixmap:
            icon_rect = QRectF(x + 8, y + (h - 20) / 2.0, 20, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self.mini_cover_pixmap))
            p.drawRoundedRect(icon_rect, 10, 10)
        else:
            p.setFont(QFont("Noto Sans", 11, QFont.Weight.Bold))
            p.setPen(QColor(29, 185, 84))
            p.drawText(QRectF(x + 8, y + 4, 20, 20), Qt.AlignmentFlag.AlignCenter, "●")

        # Title
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.DemiBold))
        p.setPen(QColor(240, 240, 248))
        p.drawText(
            QRectF(x + 34, y + (h - 18) / 2.0, w - 66, 18),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.title_text[:20]
        )
        self.visualizer.move(int(x + w - 28), int(y + (h - 18) / 2.0))

    def _paint_music_expanded(self, p: QPainter, x, y, w, h):
        text_x = x + 116
        text_w = w - 150

        p.setFont(QFont("Noto Sans", 11, QFont.Weight.Bold))
        p.setPen(QColor(255, 255, 255))
        p.drawText(
            QRectF(text_x, y + 16, text_w, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.title_text[:28]
        )
        p.setFont(QFont("Noto Sans", 9, QFont.Weight.Medium))
        p.setPen(QColor(180, 150, 250))
        p.drawText(
            QRectF(text_x, y + 40, text_w, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.artist_text[:32]
        )
        if self.album_text:
            p.setFont(QFont("Noto Sans", 8))
            p.setPen(QColor(140, 140, 165))
            p.drawText(
                QRectF(text_x, y + 60, text_w, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.album_text[:34]
            )
        self.visualizer.move(int(x + w - 34), int(y + 16))
        self.cover_canvas.move(int(x + 14), int(y + 13))

    def _paint_task(self, p: QPainter, x, y, w, h, mode):
        """Robo eyes left + status label right."""
        # Eyes take left ~40% of pill
        eye_zone_w = w * 0.38
        eye_cx = x + eye_zone_w / 2
        eye_cy = y + h / 2

        eye_size = min(h * 0.38, 14.0)
        self.robo.draw(p, eye_cx, eye_cy, eye_w=eye_size, eye_h=eye_size * 0.72)

        # Divider line
        p.setPen(QPen(QColor(80, 80, 120, 80), 1.0))
        lx = int(x + eye_zone_w)
        p.drawLine(lx, int(y + 8), lx, int(y + h - 8))

        # Status label
        label = self._task_label
        if mode == MODE_TASK_RUNNING:
            dots = "." * self._task_dots
            label_short = (label[:22] + "…") if len(label) > 22 else label
            label = label_short + dots
        elif mode == MODE_TASK_DONE:
            label = "✓ " + (label[:24])
        elif mode == MODE_TASK_WAITING:
            label = "⚠ " + (label[:22])

        # Icon / color per mode
        icon_col = {
            MODE_TASK_RUNNING: QColor(0,   200, 255),
            MODE_TASK_DONE:    QColor(29,  185,  84),
            MODE_TASK_WAITING: QColor(230, 170,   0),
        }.get(mode, QColor(200, 200, 220))

        p.setFont(QFont("Noto Sans", 8, QFont.Weight.Bold))
        p.setPen(icon_col)
        label_x = x + eye_zone_w + 10
        label_w = w - eye_zone_w - 16
        p.drawText(
            QRectF(label_x, y + (h - 18) / 2, label_w, 18),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            label
        )

    def _paint_greeting(self, p: QPainter, x, y, w, h):
        """Winking robo + 'Hi, I'm Robo!' text."""
        eye_cx = x + w * 0.28
        eye_cy = y + h / 2
        self.robo.draw(p, eye_cx, eye_cy, eye_w=13, eye_h=9)

        p.setFont(QFont("Noto Sans", 10, QFont.Weight.Bold))
        p.setPen(QColor(180, 150, 255))
        text_x  = x + w * 0.48
        text_w  = w * 0.50
        p.drawText(
            QRectF(text_x, y + (h - 20) / 2, text_w, 20),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "Hi, I'm Robo!"
        )
