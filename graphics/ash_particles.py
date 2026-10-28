"""
Ash & Wind Particle Disintegration Engine for Spotify-Island.
Simulates an album cover dissolving like burnt ash blown away by a wind from the left,
and the new album cover assembling from floating embers and dust particles.
"""
import math
import random
import time
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPixmap, QImage, QColor, QPen, QBrush
from PySide6.QtCore import Qt, QTimer, QRectF, Signal


class AshParticle:
    __slots__ = (
        'x', 'y', 'orig_x', 'orig_y', 'target_x', 'target_y',
        'vx', 'vy', 'size', 'color', 'alpha', 'delay', 'is_ember',
        'phase', 'active'
    )

    def __init__(self, x, y, color: QColor, is_disintegrating: bool, delay: float = 0.0, target_x: float = 0.0, target_y: float = 0.0):
        self.orig_x = x
        self.orig_y = y
        self.delay = delay
        self.active = False

        if is_disintegrating:
            # Phase 1: Disintegrating (Old cover ash)
            self.x = x
            self.y = y
            self.phase = "dissolve"
            # Gentle wind from the left (positive X direction) + rising updraft
            self.vx = random.uniform(2.0, 5.2)
            self.vy = random.uniform(-1.8, 0.5)
            self.size = random.uniform(1.8, 3.2)
            self.alpha = 255.0
            # ~12% chance of being an incandescent ember spark
            self.is_ember = (random.random() < 0.12)
            if self.is_ember:
                self.color = QColor(255, random.randint(120, 200), random.randint(30, 80), 255)
            else:
                # Muted ash tint mixed with original pixel color
                gray = int(color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114)
                blend = 0.65  # 65% ash color, 35% original
                r = int(gray * blend + color.red() * (1 - blend))
                g = int(gray * blend + color.green() * (1 - blend))
                b = int(gray * blend + color.blue() * (1 - blend))
                self.color = QColor(r, g, b, 255)
        else:
            # Phase 2: Assembling (New cover forming from ash)
            self.target_x = target_x
            self.target_y = target_y
            self.phase = "assemble"
            # Spawn scattered to the left and slightly swirling
            self.x = target_x - random.uniform(120, 240)
            self.y = target_y + random.uniform(-50, 50)
            self.vx = 0.0
            self.vy = 0.0
            self.size = random.uniform(2.0, 3.0)
            self.alpha = 0.0
            self.color = color
            self.is_ember = (random.random() < 0.08)


class AshCoverCanvas(QWidget):
    animation_finished = Signal()

    def __init__(self, size: int = 84, parent=None):
        super().__init__(parent)
        self.canvas_size = size
        self.setFixedSize(size + 60, size)  # Extra width for particles flying off to the right

        self.current_pixmap: QPixmap = None
        self.new_pixmap: QPixmap = None

        self.particles: list[AshParticle] = []
        self.anim_start_time = 0.0
        self.anim_duration = 2.0  # Total transition duration in seconds
        self.is_animating = False

        # 120-240Hz High-refresh simulation timer (~6ms)
        self.timer = QTimer(self)
        self.timer.setInterval(6)
        self.timer.timeout.connect(self._step_simulation)

    def set_cover(self, pixmap: QPixmap):
        """Instantly display cover with no transition (initial load)"""
        self.is_animating = False
        self.timer.stop()
        self.particles.clear()
        self.current_pixmap = pixmap.scaled(
            self.canvas_size, self.canvas_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        self.update()

    def transition_to(self, new_pixmap: QPixmap):
        """Start the left-to-right wind ash disintegration & assembly animation"""
        scaled_new = new_pixmap.scaled(
            self.canvas_size, self.canvas_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )

        if self.current_pixmap is None:
            self.set_cover(scaled_new)
            return

        self.new_pixmap = scaled_new
        self.particles.clear()

        # 1. Sample old cover into disintegration particles
        old_img = self.current_pixmap.toImage()
        w = old_img.width()
        h = old_img.height()
        step = 3  # Sampling resolution (every 3 pixels)

        for y in range(0, h, step):
            for x in range(0, w, step):
                c = old_img.pixelColor(x, y)
                if c.alpha() > 20:
                    # Wave delay: particles on the left (x=0) blow away first!
                    delay = (x / float(w)) * 0.40 + random.uniform(0.0, 0.08)
                    self.particles.append(AshParticle(x, y, c, is_disintegrating=True, delay=delay))

        # 2. Sample new cover into assembly particles
        new_img = self.new_pixmap.toImage()
        for y in range(0, h, step):
            for x in range(0, w, step):
                c = new_img.pixelColor(x, y)
                if c.alpha() > 20:
                    # Assembly delay starts around 0.55s into the transition
                    delay = 0.55 + (x / float(w)) * 0.35 + random.uniform(0.0, 0.08)
                    self.particles.append(AshParticle(x, y, c, is_disintegrating=False, delay=delay, target_x=x, target_y=y))

        self.anim_start_time = time.perf_counter()
        self.is_animating = True
        self.timer.start()

    def _step_simulation(self):
        if not self.is_animating:
            return

        elapsed = time.perf_counter() - self.anim_start_time

        if elapsed >= self.anim_duration:
            # Complete animation
            self.is_animating = False
            self.timer.stop()
            self.current_pixmap = self.new_pixmap
            self.new_pixmap = None
            self.particles.clear()
            self.update()
            self.animation_finished.emit()
            return

        # Physics update per particle
        for p in self.particles:
            if elapsed < p.delay:
                continue

            t_active = elapsed - p.delay

            if p.phase == "dissolve":
                # Wind gust acceleration to the right
                p.vx += random.uniform(0.06, 0.20)
                p.vy += random.uniform(-0.08, 0.06)  # Thermal updraft turbulence
                p.x += p.vx
                p.y += p.vy
                # Fade out ash
                p.alpha = max(0.0, 255.0 * (1.0 - (t_active / 0.95)))
                p.size = max(0.8, p.size * 0.988)
            elif p.phase == "assemble":
                # Magnetic spring attraction towards target (tx, ty)
                progress = min(1.0, t_active / 0.75)
                # Cubic ease-out
                ease = 1.0 - math.pow(1.0 - progress, 3)
                p.x = p.orig_x + (p.target_x - p.orig_x) * ease
                p.y = p.orig_y + (p.target_y - p.orig_y) * ease
                p.alpha = min(255.0, progress * 280.0)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.is_animating:
            if self.current_pixmap:
                # Rounded clipping for cover art
                rect = QRectF(0, 0, self.canvas_size, self.canvas_size)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(self.current_pixmap))
                painter.drawRoundedRect(rect, 10, 10)
        else:
            # Render Ash & Wind Particles
            elapsed = time.perf_counter() - self.anim_start_time

            # Draw static residual of old cover that hasn't peeled off yet
            if self.current_pixmap and elapsed < 0.50:
                # Clip revealing only remaining right side
                pct = min(1.0, elapsed / 0.50)
                left_cutoff = self.canvas_size * pct
                painter.save()
                painter.setClipRect(QRectF(left_cutoff, 0, self.canvas_size - left_cutoff, self.canvas_size))
                painter.drawRoundedRect(QRectF(0, 0, self.canvas_size, self.canvas_size), 10, 10)
                painter.restore()

            for p in self.particles:
                if elapsed < p.delay or p.alpha <= 1.0:
                    continue

                c = QColor(p.color)
                c.setAlpha(int(p.alpha))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(c))

                if p.is_ember:
                    # Glowing ember dot
                    painter.drawEllipse(QRectF(p.x, p.y, p.size * 1.3, p.size * 1.3))
                else:
                    painter.drawRect(QRectF(p.x, p.y, p.size, p.size))

        painter.end()
