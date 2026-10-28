"""
Apple Dynamic Island-style Animated Audio Visualizer Bars for Spotify-Island.
"""
import math
import time
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush


class MiniVisualizer(QWidget):
    def __init__(self, bars_count: int = 4, bar_color: QColor = None, parent=None):
        super().__init__(parent)
        self.bars_count = bars_count
        self.setFixedSize(22, 18)
        self.bar_color = bar_color or QColor(29, 185, 84)  # Spotify Green #1DB954
        self.is_playing = True

        self.phase_offsets = [0.0, 1.8, 3.4, 4.9]
        self.speeds = [4.2, 5.1, 4.7, 5.8]

        self.timer = QTimer(self)
        self.timer.setInterval(16)  # ~60-120fps smooth
        self.timer.timeout.connect(self.update)
        self.timer.start()

    def set_playing(self, playing: bool):
        self.is_playing = playing
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.bar_color))

        w = self.width()
        h = self.height()
        bar_w = 3.0
        gap = 2.0
        t = time.perf_counter()

        total_w = (self.bars_count * bar_w) + ((self.bars_count - 1) * gap)
        start_x = (w - total_w) / 2.0

        for i in range(self.bars_count):
            if self.is_playing:
                # Dynamic sinusoidal heights
                norm = 0.5 + 0.5 * math.sin(t * self.speeds[i] + self.phase_offsets[i])
                bar_h = max(3.0, norm * (h - 2.0))
            else:
                bar_h = 3.0  # Flattened when paused

            x = start_x + i * (bar_w + gap)
            y = (h - bar_h) / 2.0
            painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 1.5, 1.5)

        painter.end()
