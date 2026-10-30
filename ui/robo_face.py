"""
Robo Face Drawing Engine for Robo Island.
Draws animated robot eyes that communicate system state via color and motion.

Eye states:
  idle      - half-closed, slow pulse (violet dim)
  active    - full open, spinning retina (cyan bright)
  happy     - arc/smile shape, green glow
  alert     - full open blinking fast (yellow/amber)
  sleeping  - thin horizontal line, very dim
  error     - X shape, red
"""
import math
import time
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QRadialGradient
from PySide6.QtCore import QRectF, Qt


# ── Color palette per state ────────────────────────────────────────────────
STATE_COLORS = {
    "idle":     (QColor(146, 110, 228, 180), QColor(180, 150, 255, 220)),  # violet
    "active":   (QColor(0,   200, 255, 220), QColor(120, 240, 255, 255)),  # cyan
    "happy":    (QColor(29,  185,  84, 220), QColor(80,  230, 130, 255)),  # green
    "alert":    (QColor(230, 170,   0, 220), QColor(255, 210,  60, 255)),  # amber
    "sleeping": (QColor( 60,  60, 100, 120), QColor( 80,  80, 130, 140)),  # dim
    "error":    (QColor(220,  50,  60, 220), QColor(255,  80,  80, 255)),  # red
}


class RoboFace:
    """
    Stateless drawing helper — call draw() each frame.
    All animation is driven by time.perf_counter() so no QTimer needed.
    """

    def __init__(self):
        self.state = "idle"
        self._state_entered = time.perf_counter()
        self._blink_interval = 4.2   # seconds between auto-blinks
        self._blink_duration = 0.18  # seconds a blink lasts
        self._spin_speed = 1.8       # radians/s for active retina spin
        self._alert_freq  = 5.0      # Hz for alert blink

    def set_state(self, state: str):
        if state != self.state:
            self.state = state
            self._state_entered = time.perf_counter()

    def draw(self, painter: QPainter, cx: float, cy: float, eye_w: float = 14.0, eye_h: float = 10.0):
        """
        Draw two robot eyes centered around (cx, cy).
        eye_w / eye_h = outer eye oval dimensions.
        """
        t = time.perf_counter()
        elapsed = t - self._state_entered

        base_color, glow_color = STATE_COLORS.get(self.state, STATE_COLORS["idle"])

        # ── Eye gap & positions ───────────────────────────────────────────
        gap = eye_w * 0.9
        left_cx  = cx - gap / 2 - eye_w / 2
        right_cx = cx + gap / 2 + eye_w / 2
        eye_y    = cy

        for ex in (left_cx, right_cx):
            self._draw_single_eye(painter, ex, eye_y, eye_w, eye_h,
                                   base_color, glow_color, t, elapsed, cx)

    # ── Private helpers ───────────────────────────────────────────────────

    def _draw_single_eye(self, painter, ex, ey, ew, eh,
                          base_col, glow_col, t, elapsed, center_cx):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        state = self.state

        # ── Blink calculation ─────────────────────────────────────────────
        blink_phase = 0.0   # 0 = fully open, 1 = fully closed
        if state not in ("sleeping", "error"):
            blink_t = t % self._blink_interval
            if blink_t < self._blink_duration:
                blink_phase = math.sin(math.pi * blink_t / self._blink_duration)

        if state == "alert":
            # Override blink with fast strobe
            blink_phase = 0.5 + 0.5 * math.sin(2 * math.pi * self._alert_freq * elapsed)
            blink_phase = max(0.0, blink_phase)

        open_ratio = 1.0 - blink_phase  # 1 = open, 0 = blink-closed

        # ── Height modifiers per state ────────────────────────────────────
        if state == "idle":
            # Slightly droopy — half open with slow breathe
            open_ratio *= 0.60 + 0.12 * math.sin(2 * math.pi * 0.35 * t)
        elif state == "sleeping":
            open_ratio = 0.08  # Near-closed line
        elif state == "happy":
            open_ratio = 1.0  # Full open (arc drawn differently below)
        elif state == "active":
            # Subtle quick pulse
            open_ratio *= 0.88 + 0.12 * math.sin(2 * math.pi * 2.5 * elapsed)

        draw_h = max(1.0, eh * open_ratio)

        # ── Outer glow halo ───────────────────────────────────────────────
        glow_alpha = int(glow_col.alpha() * 0.35)
        glow_r = QColor(glow_col)
        glow_r.setAlpha(glow_alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow_r))
        painter.drawEllipse(QRectF(ex - ew/2 - 2, ey - draw_h/2 - 2, ew + 4, draw_h + 4))

        # ── Eye body ──────────────────────────────────────────────────────
        if state == "happy" and open_ratio > 0.5:
            # Draw upward arc (smile eye)
            pen = QPen(glow_col, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRectF(ex - ew/2, ey - draw_h/2, ew, draw_h)
            painter.drawArc(rect, 0 * 16, 180 * 16)    # top half arc
        elif state == "error":
            # X shape
            pen = QPen(base_col, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            half = ew * 0.4
            painter.drawLine(
                int(ex - half), int(ey - half),
                int(ex + half), int(ey + half)
            )
            painter.drawLine(
                int(ex + half), int(ey - half),
                int(ex - half), int(ey + half)
            )
        else:
            # Standard filled oval
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(base_col))
            painter.drawEllipse(QRectF(ex - ew/2, ey - draw_h/2, ew, draw_h))

            # ── Retina (inner bright dot) ─────────────────────────────────
            if draw_h > 2.0 and state not in ("sleeping", "error"):
                retina_r = min(draw_h * 0.28, ew * 0.22)

                if state == "active":
                    # Spin retina in a small orbit
                    orbit_r = ew * 0.18
                    angle = self._spin_speed * elapsed
                    rx = ex + orbit_r * math.cos(angle)
                    ry = ey + orbit_r * math.sin(angle) * 0.5
                elif state == "alert":
                    # Slight jitter
                    rx = ex + 1.5 * math.sin(20 * elapsed)
                    ry = ey
                else:
                    rx, ry = ex, ey

                # Radial gradient for retina glow
                grad = QRadialGradient(rx, ry, retina_r * 2)
                grad.setColorAt(0.0, glow_col)
                grad.setColorAt(1.0, QColor(glow_col.red(), glow_col.green(), glow_col.blue(), 0))
                painter.setBrush(QBrush(grad))
                painter.drawEllipse(QRectF(rx - retina_r, ry - retina_r,
                                           retina_r * 2, retina_r * 2))

        painter.restore()
