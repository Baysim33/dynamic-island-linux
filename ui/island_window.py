"""
Apple Dynamic Island Floating Window for Spotify-Island.
Supports Compact (playing), Expanded (track change with ash animation), and Hidden states.
Animates smoothly on 240Hz screens and respects multi-monitor gaming protection.
"""
import os
import subprocess
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QApplication
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPixmap, QGuiApplication, QCursor
from PySide6.QtCore import Qt, QTimer, QRectF, QPropertyAnimation, QEasingCurve, Signal, Property

from graphics.ash_particles import AshCoverCanvas
from ui.visualizer import MiniVisualizer


class DynamicIsland(QWidget):
    MODE_HIDDEN = 0
    MODE_COMPACT = 1
    MODE_EXPANDED = 2

    def __init__(self, target_screen_name: str = "HDMI-A-2", parent=None):
        super().__init__(parent)
        self.target_screen_name = target_screen_name

        # Window configuration
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Island dimensions & animation state
        self._pill_width = 0.0
        self._pill_height = 0.0
        self.current_mode = self.MODE_HIDDEN

        self.target_width = 0.0
        self.target_height = 0.0

        # Current track data
        self.title_text = ""
        self.artist_text = ""
        self.album_text = ""
        self.is_playing = False

        # Fixed overall window canvas size
        self.canvas_width = 480
        self.canvas_height = 130
        self.setFixedSize(self.canvas_width, self.canvas_height)

        # 1. Ash Particle Cover Canvas
        self.cover_canvas = AshCoverCanvas(size=84, parent=self)
        self.cover_canvas.setGeometry(16, 14, 144, 84)
        self.cover_canvas.hide()

        # 2. Mini Compact Cover
        self.mini_cover_pixmap: QPixmap = None

        # 3. Audio Visualizer
        self.visualizer = MiniVisualizer(bars_count=4, bar_color=QColor(29, 185, 84), parent=self)
        self.visualizer.hide()

        # Spring Animation Timer (smooth 120-240Hz physics ~7ms)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(7)
        self.anim_timer.timeout.connect(self._step_dimensions)
        self.anim_timer.start()

        # Auto-collapse timer (after track change expands, wait 4.5s then shrink to compact)
        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.setInterval(4500)
        self.collapse_timer.timeout.connect(self._on_collapse_timeout)

        # Re-position window on chosen screen
        self.update_screen_position(target_screen_name)

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

        if target_screen:
            geo = target_screen.geometry()
            # Center horizontally at the very top of that monitor
            x = geo.x() + (geo.width() - self.canvas_width) // 2
            y = geo.y() + 6  # 6px gap from the top bezel
            self.move(x, y)

    def on_playback_status(self, status: str):
        self.is_playing = (status == "Playing")
        self.visualizer.set_playing(self.is_playing)

        if not self.is_playing and self.current_mode != self.MODE_EXPANDED:
            # Hide island when paused/stopped
            self.set_mode(self.MODE_HIDDEN)
        elif self.is_playing and self.current_mode == self.MODE_HIDDEN:
            # Reveal compact island when music starts playing
            self.set_mode(self.MODE_COMPACT)

    def on_track_changed(self, track_info: dict):
        self.title_text = track_info.get("title", "")
        self.artist_text = track_info.get("artist", "")
        self.album_text = track_info.get("album", "")
        cover_path = track_info.get("cover_path", "")

        # Load pixmap
        new_pixmap = QPixmap()
        if cover_path and os.path.exists(cover_path):
            new_pixmap.load(cover_path)
            self.mini_cover_pixmap = new_pixmap.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        else:
            self.mini_cover_pixmap = None

        # Trigger wind ash particle transition
        if not new_pixmap.isNull():
            self.cover_canvas.transition_to(new_pixmap)

        # Expand island!
        self.set_mode(self.MODE_EXPANDED)
        self.collapse_timer.start()

    def set_mode(self, mode: int):
        self.current_mode = mode
        if mode == self.MODE_HIDDEN:
            self.target_width = 0.0
            self.target_height = 0.0
        elif mode == self.MODE_COMPACT:
            self.target_width = 190.0
            self.target_height = 36.0
            self.cover_canvas.hide()
            self.visualizer.show()
        elif mode == self.MODE_EXPANDED:
            self.target_width = 440.0
            self.target_height = 110.0
            self.cover_canvas.show()
            self.visualizer.show()

        if mode != self.MODE_HIDDEN and not self.isVisible():
            self.show()
            self.raise_()

    def _on_collapse_timeout(self):
        # Only collapse back to compact if song is still playing
        if self.is_playing:
            self.set_mode(self.MODE_COMPACT)
        else:
            self.set_mode(self.MODE_HIDDEN)

    def _step_dimensions(self):
        # Exponential spring ease towards target dimensions
        diff_w = self.target_width - self._pill_width
        diff_h = self.target_height - self._pill_height

        if abs(diff_w) > 0.5 or abs(diff_h) > 0.5:
            self._pill_width += diff_w * 0.16
            self._pill_height += diff_h * 0.16
            self.update()
        else:
            self._pill_width = self.target_width
            self._pill_height = self.target_height
            if self.current_mode == self.MODE_HIDDEN and self._pill_height <= 1.0:
                self.hide()
            self.update()

    def enterEvent(self, event):
        # Hovering stops collapse timer so user can enjoy album & particle effect
        if self.collapse_timer.isActive():
            self.collapse_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.current_mode == self.MODE_EXPANDED:
            self.collapse_timer.start(2500)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        # Left click toggles play/pause on Spotify
        if event.button() == Qt.MouseButton.LeftButton:
            try:
                subprocess.run([
                    "qdbus6", "org.mpris.MediaPlayer2.spotify",
                    "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.PlayPause"
                ], timeout=1)
            except Exception:
                pass
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        if self._pill_width <= 2.0 or self._pill_height <= 2.0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Center the pill horizontally within the canvas
        cx = self.width() / 2.0
        x = cx - (self._pill_width / 2.0)
        y = 4.0
        w = self._pill_width
        h = self._pill_height
        radius = h / 2.0

        pill_rect = QRectF(x, y, w, h)

        # 1. Matte Black Apple Island Background with subtle violet glass rim
        painter.setPen(QPen(QColor(146, 110, 228, 90), 1.2))
        painter.setBrush(QBrush(QColor(11, 11, 16, 250)))
        painter.drawRoundedRect(pill_rect, radius, radius)

        # 2. Mode Content Rendering
        if self.current_mode == self.MODE_COMPACT and self._pill_width > 120:
            # --- COMPACT MODE ---
            # Mini Cover / Spotify Icon on left
            if self.mini_cover_pixmap:
                icon_rect = QRectF(x + 8, y + (h - 20) / 2.0, 20, 20)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(self.mini_cover_pixmap))
                painter.drawRoundedRect(icon_rect, 10, 10)
            else:
                painter.setFont(QFont("Noto Sans", 11, QFont.Weight.Bold))
                painter.setPen(QColor(29, 185, 84))
                painter.drawText(QRectF(x + 8, y + 4, 20, 20), Qt.AlignmentFlag.AlignCenter, "●")

            # Title
            painter.setFont(QFont("Noto Sans", 9, QFont.Weight.DemiBold))
            painter.setPen(QColor(240, 240, 248))
            text_rect = QRectF(x + 34, y + (h - 18) / 2.0, w - 66, 18)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title_text[:18])

            # Position Visualizer at far right of pill
            self.visualizer.move(int(x + w - 28), int(y + (h - 18) / 2.0))

        elif self.current_mode == self.MODE_EXPANDED and self._pill_width > 300:
            # --- EXPANDED MODE ---
            # Text layout to the right of the Ash Cover Canvas
            text_x = x + 116
            text_w = w - 150

            # Title (Bold, white)
            painter.setFont(QFont("Noto Sans", 11, QFont.Weight.Bold))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QRectF(text_x, y + 16, text_w, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title_text[:28])

            # Artist (Accent Violet)
            painter.setFont(QFont("Noto Sans", 9, QFont.Weight.Medium))
            painter.setPen(QColor(180, 150, 250))
            painter.drawText(QRectF(text_x, y + 40, text_w, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.artist_text[:32])

            # Album (Subtle gray)
            if self.album_text:
                painter.setFont(QFont("Noto Sans", 8))
                painter.setPen(QColor(140, 140, 165))
                painter.drawText(QRectF(text_x, y + 60, text_w, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.album_text[:34])

            # Position Visualizer top right
            self.visualizer.move(int(x + w - 34), int(y + 16))

            # Reposition cover canvas relative to pill
            self.cover_canvas.move(int(x + 14), int(y + 13))

        painter.end()
