"""
Robo Face Drawing Engine for Robo Island.
Draws animated, living robot eyes that communicate system state via color, motion,
and lively autonomous micro-expressions when idle!

Eye states:
  idle      - half-closed, slow pulse with living autonomous saccades, winks, curiosity
  active    - full open, spinning retina (cyan bright)
  happy     - arc/smile shape, green glow
  alert     - full open blinking fast (yellow/amber)
  sleeping  - thin horizontal line, very dim
  error     - X shape, red
"""
import math
import time
import random
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QRadialGradient
from PySide6.QtCore import QRectF, Qt


# ── Color palette per state ────────────────────────────────────────────────
CUSTOM_EYE_COLORS = {
    "violet": (QColor(146, 110, 228, 210), QColor(190, 160, 255, 240)),
    "cyan":   (QColor(0,   200, 255, 220), QColor(120, 240, 255, 255)),
    "green":  (QColor(29,  185,  84, 220), QColor(80,  230, 130, 255)),
    "amber":  (QColor(230, 170,   0, 220), QColor(255, 210,  60, 255)),
    "red":    (QColor(220,  50,  60, 220), QColor(255,  80,  80, 255)),
    "white":  (QColor(230, 230, 245, 220), QColor(255, 255, 255, 255)),
}

STATE_COLORS = {
    "idle":     (QColor(146, 110, 228, 190), QColor(190, 160, 255, 230)),  # violet
    "active":   (QColor(0,   200, 255, 220), QColor(120, 240, 255, 255)),  # cyan
    "happy":    (QColor(29,  185,  84, 220), QColor(80,  230, 130, 255)),  # green
    "alert":    (QColor(230, 170,   0, 220), QColor(255, 210,  60, 255)),  # amber
    "sleeping": (QColor( 60,  60, 100, 120), QColor( 80,  80, 130, 140)),  # dim
    "error":    (QColor(220,  50,  60, 220), QColor(255,  80,  80, 255)),  # red
}


class RoboFace:
    """
    Stateless & autonomous drawing helper — call draw() each frame.
    Simulates a living, curious AI assistant with spontaneous organic micro-mimics.
    """

    def __init__(self):
        self.state = "idle"
        self._state_entered = time.perf_counter()
        self._blink_interval = 3.6   # seconds between auto-blinks
        self._blink_duration = 0.16  # seconds a blink lasts
        self._spin_speed = 1.8       # radians/s for active retina spin
        self._alert_freq  = 5.0      # Hz for alert blink

        # ── Autonomous Idle Behavior State Machine ────────────────────────
        self._last_behavior_switch = time.perf_counter()
        self._behavior_duration = 2.0
        self._current_behavior = "center"  # center, look_left, look_right, look_up, curious, wink, smile, heart

        # Smooth interpolated gaze offset
        self._gaze_x = 0.0
        self._gaze_y = 0.0
        self._target_gaze_x = 0.0
        self._target_gaze_y = 0.0
        self._is_hovered = False
        self._action_mode = ""
        self._action_until = 0.0

    def set_hover(self, is_hover: bool, rel_x: float = 0.0):
        """React to mouse cursor hovering or moving over the island."""
        self._is_hovered = is_hover
        if is_hover:
            self._target_gaze_x = max(-2.5, min(2.5, rel_x * 2.5))
            self._target_gaze_y = -0.6
            self._current_behavior = "curious"
        else:
            self._target_gaze_x = 0.0
            self._target_gaze_y = 0.0

    def trigger_action(self, action: str):
        """User interaction triggers: 'panel_open', 'panel_close', 'typing', 'song_change'."""
        now = time.perf_counter()
        self._action_mode = action
        if action == "panel_open":
            self._action_until = now + 1.2
            self._current_behavior = "smile"
            self._target_gaze_x = 0.0
            self._target_gaze_y = -1.2
        elif action == "panel_close":
            self._action_until = now + 0.8
            self._current_behavior = "wink"
        elif action == "typing":
            self._action_until = now + 0.5
            self._current_behavior = "center"
            # Oscillate gaze back and forth reading what the user types
            self._target_gaze_x = math.sin(now * 10.0) * 1.8
            self._target_gaze_y = 0.5
        elif action == "song_change":
            self._action_until = now + 1.5
            self._current_behavior = "heart"

    def set_state(self, state: str):
        if state != self.state:
            self.state = state
            self._state_entered = time.perf_counter()

    def _update_idle_behavior(self, t: float):
        """Randomly cycles between cute lifelike robotic expressions while idle."""
        # Action override
        if self._action_until > t:
            if self._action_mode == "typing":
                self._target_gaze_x = math.sin(t * 12.0) * 1.6
                self._target_gaze_y = 0.4
            self._gaze_x += (self._target_gaze_x - self._gaze_x) * 0.25
            self._gaze_y += (self._target_gaze_y - self._gaze_y) * 0.25
            return

        if self._is_hovered:
            self._gaze_x += (self._target_gaze_x - self._gaze_x) * 0.2
            self._gaze_y += (self._target_gaze_y - self._gaze_y) * 0.2
            return

        if self.state != "idle":
            self._current_behavior = "center"
            self._target_gaze_x = 0.0
            self._target_gaze_y = 0.0
            return

        if t - self._last_behavior_switch > self._behavior_duration:
            self._last_behavior_switch = t
            # Weight towards center but sprinkle fun autonomous actions
            choices = [
                ("center", 2.2, 0.0, 0.0),
                ("look_right", 1.8, 1.8, 0.0),
                ("look_left", 1.8, -1.8, 0.0),
                ("look_up", 1.5, 0.0, -1.5),
                ("curious", 1.6, 1.2, -0.8),
                ("wink", 0.9, 0.0, 0.0),
                ("smile", 1.4, 0.0, 0.0),
                ("heart", 1.6, 0.0, 0.0),
                ("center", 2.8, 0.0, 0.0),
            ]
            beh, dur, gx, gy = random.choice(choices)
            self._current_behavior = beh
            self._behavior_duration = dur
            self._target_gaze_x = gx
            self._target_gaze_y = gy

        # Smooth exponential easing for pupils
        self._gaze_x += (self._target_gaze_x - self._gaze_x) * 0.15
        self._gaze_y += (self._target_gaze_y - self._gaze_y) * 0.15

    def draw(self, painter: QPainter, cx: float, cy: float, eye_w: float = 14.0, eye_h: float = 10.0, eye_color_mode: str = "auto"):
        if eye_color_mode in ("off", "hidden", "none"):
            return

        t = time.perf_counter()
        elapsed = t - self._state_entered

        self._update_idle_behavior(t)

        if eye_color_mode and eye_color_mode in CUSTOM_EYE_COLORS:
            base_color, glow_color = CUSTOM_EYE_COLORS[eye_color_mode]
        else:
            base_color, glow_color = STATE_COLORS.get(self.state, STATE_COLORS["idle"])

        # Eye gap & positions
        gap = eye_w * 0.9
        left_cx  = cx - gap / 2 - eye_w / 2
        right_cx = cx + gap / 2 + eye_w / 2
        eye_y    = cy

        # Draw left eye
        self._draw_single_eye(painter, left_cx, eye_y, eye_w, eye_h,
                               base_color, glow_color, t, elapsed, is_left=True)

        # Draw right eye
        self._draw_single_eye(painter, right_cx, eye_y, eye_w, eye_h,
                               base_color, glow_color, t, elapsed, is_left=False)

    # ── Single Eye Renderer ───────────────────────────────────────────────────

    def _draw_single_eye(self, painter: QPainter, ex: float, ey: float, ew: float, eh: float,
                          base_col: QColor, glow_col: QColor, t: float, elapsed: float, is_left: bool):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        state = self.state
        beh   = self._current_behavior

        # ── Blink calculation ─────────────────────────────────────────────
        blink_phase = 0.0
        if state not in ("sleeping", "error"):
            blink_t = t % self._blink_interval
            if blink_t < self._blink_duration:
                blink_phase = math.sin(math.pi * blink_t / self._blink_duration)

        if state == "alert":
            blink_phase = 0.5 + 0.5 * math.sin(2 * math.pi * self._alert_freq * elapsed)
            blink_phase = max(0.0, blink_phase)

        open_ratio = 1.0 - blink_phase

        # ── Autonomous Behaviors & Mimic Modifiers ────────────────────────
        is_smile = False
        is_heart = False

        if state == "idle":
            # Breathing pulse
            breath = 0.58 + 0.10 * math.sin(2 * math.pi * 0.40 * t)
            open_ratio *= breath

            if beh == "wink":
                # Left eye winks while right stays alert!
                if is_left:
                    open_ratio *= 0.12
                else:
                    open_ratio = 0.85
            elif beh == "curious":
                # One eye slightly wider with curiosity
                if is_left:
                    open_ratio *= 1.25
                else:
                    open_ratio *= 0.75
            elif beh == "smile":
                is_smile = True
                open_ratio = 1.0
            elif beh == "heart":
                is_heart = True
                open_ratio = 0.95

        elif state == "sleeping":
            open_ratio = 0.08
        elif state == "happy":
            is_smile = True
            open_ratio = 1.0
        elif state == "active":
            open_ratio *= 0.88 + 0.12 * math.sin(2 * math.pi * 2.5 * elapsed)

        draw_h = max(1.0, eh * open_ratio)

        # ── Color variations for special states ───────────────────────────
        draw_base = QColor(base_col)
        draw_glow = QColor(glow_col)
        if is_heart:
            draw_base = QColor(255, 105, 180, 220)  # Hot pink / heart glow
            draw_glow = QColor(255, 160, 210, 255)

        # ── Outer glow halo ───────────────────────────────────────────────
        glow_alpha = int(draw_glow.alpha() * 0.38)
        glow_r = QColor(draw_glow)
        glow_r.setAlpha(glow_alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow_r))
        painter.drawEllipse(QRectF(ex - ew/2 - 2, ey - draw_h/2 - 2, ew + 4, draw_h + 4))

        # ── Eye Body ──────────────────────────────────────────────────────
        if (state == "happy" or is_smile) and open_ratio > 0.4:
            # Cute smile arc eye (^ ^)
            pen = QPen(draw_glow, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRectF(ex - ew/2, ey - draw_h/2 - 1, ew, draw_h)
            painter.drawArc(rect, 15 * 16, 150 * 16)
        elif state == "error":
            # X shape
            pen = QPen(draw_base, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            half = ew * 0.4
            painter.drawLine(int(ex - half), int(ey - half), int(ex + half), int(ey + half))
            painter.drawLine(int(ex + half), int(ey - half), int(ex - half), int(ey + half))
        else:
            # Standard filled oval
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(draw_base))
            painter.drawEllipse(QRectF(ex - ew/2, ey - draw_h/2, ew, draw_h))

            # ── Retina / Pupil with Gaze Tracking ─────────────────────────
            if draw_h > 2.2 and state not in ("sleeping", "error"):
                retina_r = min(draw_h * 0.30, ew * 0.22)

                if state == "active":
                    orbit_r = ew * 0.18
                    angle = self._spin_speed * elapsed
                    rx = ex + orbit_r * math.cos(angle)
                    ry = ey + orbit_r * math.sin(angle) * 0.5
                elif state == "alert":
                    rx = ex + 1.5 * math.sin(20 * elapsed)
                    ry = ey
                else:
                    # Autonomous gaze saccades!
                    rx = ex + self._gaze_x
                    ry = ey + self._gaze_y

                grad = QRadialGradient(rx, ry, retina_r * 2)
                grad.setColorAt(0.0, draw_glow)
                grad.setColorAt(1.0, QColor(draw_glow.red(), draw_glow.green(), draw_glow.blue(), 0))
                painter.setBrush(QBrush(grad))
                painter.drawEllipse(QRectF(rx - retina_r, ry - retina_r, retina_r * 2, retina_r * 2))

        painter.restore()
