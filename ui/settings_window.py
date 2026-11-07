"""
Settings & Customization Window for Spotify / Robo Island.
Sleek Apple / Glassmorphism UI for adjusting colors, styles, eye mimics, badges, and sizes.
Compact, responsive, and beautifully scrollable on any screen size.
"""
import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QApplication
)
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QCursor, QPainterPath, QGuiApplication
from PySide6.QtCore import Qt, Signal, QRectF, QPoint

from backend.settings_manager import get_settings, PRESET_COLORS, EYE_COLOR_PRESETS


class ColorCircleButton(QPushButton):
    """Circular color picker pill with glowing selection ring."""
    def __init__(self, color_hex: str, name: str, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self.color_hex = color_hex
        self.color_name = name
        self.is_selected = is_selected
        self.setFixedSize(32, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(name)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        cx = rect.center().x()
        cy = rect.center().y()

        # Selection glow ring
        if self.is_selected:
            p.setPen(QPen(QColor(self.color_hex), 2.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(cx - 14, cy - 14, 28, 28))

        # Main solid color circle
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self.color_hex)))
        p.drawEllipse(QRectF(cx - 10, cy - 10, 20, 20))

        if self.is_selected:
            p.setBrush(QBrush(QColor("#ffffff") if self.color_hex.lower() != "#f0f2f5" else QColor("#14121e")))
            p.drawEllipse(QRectF(cx - 2.5, cy - 2.5, 5, 5))


class SettingsWindow(QWidget):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()

        self.setWindowTitle("Robo Island — Kişiselleştirme")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Responsive height based on available screen space
        screen = QGuiApplication.primaryScreen()
        avail_h = screen.geometry().height() if screen else 900
        win_h = min(460, max(360, avail_h - 180))
        self.setFixedSize(450, win_h)

        self._color_buttons = []
        self._eye_buttons = []
        self._drag_pos = None

        self._build_ui()
        self._apply_current_states()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 50:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Frosted glass dark background
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), 20, 20)
        p.fillPath(path, QColor(14, 13, 20, 248))

        # Accent border
        accent_color = self.settings.accent_qcolor
        p.setPen(QPen(accent_color, 1.2))
        p.drawPath(path)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 16)
        main_layout.setSpacing(10)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 2)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("🎨 Ada Kişiselleştirme")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
        subtitle = QLabel("Görünüm, renk, çentik ve akıllı tercihler")
        subtitle.setStyleSheet("font-size: 10px; color: #9a9ab8;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)

        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,18); color: #fff; border-radius: 13px; font-weight: bold; font-size: 11px; border: none; } "
            "QPushButton:hover { background: #ff4d6d; }"
        )
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        main_layout.addLayout(header)

        # ── Scroll Area with Elegant Purple Scrollbar ─────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                border: none;
                background: rgba(255, 255, 255, 10);
                width: 6px;
                margin: 2px 0 2px 0;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #926ee4;
                min-height: 25px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #b496fa;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        scroll.verticalScrollBar().setSingleStep(25)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(0, 2, 8, 4)
        c_layout.setSpacing(12)

        # 1. Ada Stili (Form)
        c_layout.addWidget(self._make_section_title("📱 Ada Formu (Stil)"))
        style_box = QHBoxLayout()
        style_box.setSpacing(8)
        self.btn_pill = self._make_pill_button("Dynamic Island (Hap)", "pill")
        self.btn_notch = self._make_pill_button("MacBook Çentiği (Notch)", "notch")
        self.btn_pill.clicked.connect(lambda: self._set_island_style("pill"))
        self.btn_notch.clicked.connect(lambda: self._set_island_style("notch"))
        style_box.addWidget(self.btn_pill)
        style_box.addWidget(self.btn_notch)
        c_layout.addLayout(style_box)

        # 2. Ada Boyutu (Ölçek)
        c_layout.addWidget(self._make_section_title("📐 Ada Boyutu"))
        scale_box = QHBoxLayout()
        scale_box.setSpacing(8)
        self.btn_scale_sm = self._make_pill_button("Kibar & Küçük (%85)", 0.85)
        self.btn_scale_md = self._make_pill_button("Standart (%100)", 1.0)
        self.btn_scale_lg = self._make_pill_button("Geniş (%115)", 1.15)
        self.btn_scale_sm.clicked.connect(lambda: self._set_scale(0.85))
        self.btn_scale_md.clicked.connect(lambda: self._set_scale(1.0))
        self.btn_scale_lg.clicked.connect(lambda: self._set_scale(1.15))
        scale_box.addWidget(self.btn_scale_sm)
        scale_box.addWidget(self.btn_scale_md)
        scale_box.addWidget(self.btn_scale_lg)
        c_layout.addLayout(scale_box)

        # 3. Tema Rengi (Accent)
        c_layout.addWidget(self._make_section_title("🎨 Tema Vurgu Rengi"))
        color_box = QHBoxLayout()
        color_box.setSpacing(8)
        for c in PRESET_COLORS:
            btn = ColorCircleButton(c["hex"], c["name"])
            btn.clicked.connect(lambda _, hex_val=c["hex"]: self._set_accent_color(hex_val))
            self._color_buttons.append(btn)
            color_box.addWidget(btn)
        color_box.addStretch()
        c_layout.addLayout(color_box)

        # 4. Göz Rengi (Robo Eyes)
        c_layout.addWidget(self._make_section_title("👀 Robo Göz Rengi"))
        eye_box_1 = QHBoxLayout()
        eye_box_2 = QHBoxLayout()
        eye_box_1.setSpacing(6)
        eye_box_2.setSpacing(6)
        for i, eye in enumerate(EYE_COLOR_PRESETS):
            btn = self._make_pill_button(eye["name"], eye["id"])
            btn.clicked.connect(lambda _, eid=eye["id"]: self._set_eye_mode(eid))
            self._eye_buttons.append((eye["id"], btn))
            if i < 4:
                eye_box_1.addWidget(btn)
            else:
                eye_box_2.addWidget(btn)
        c_layout.addLayout(eye_box_1)
        c_layout.addLayout(eye_box_2)

        # 5. Sağ Rozet Göstergesi (Badge)
        c_layout.addWidget(self._make_section_title("⏰ Sağ Rozet Göstergesi"))
        badge_box = QHBoxLayout()
        badge_box.setSpacing(6)
        self.btn_badge_clock = self._make_pill_button("Saat", "clock")
        self.btn_badge_weather = self._make_pill_button("Hava", "weather")
        self.btn_badge_both = self._make_pill_button("Dönüşümlü", "both")
        self.btn_badge_hw = self._make_pill_button("Donanım", "hardware")
        self.btn_badge_none = self._make_pill_button("Boş (Gizle)", "none")

        self.btn_badge_clock.clicked.connect(lambda: self._set_badge_mode("clock"))
        self.btn_badge_weather.clicked.connect(lambda: self._set_badge_mode("weather"))
        self.btn_badge_both.clicked.connect(lambda: self._set_badge_mode("both"))
        self.btn_badge_hw.clicked.connect(lambda: self._set_badge_mode("hardware"))
        self.btn_badge_none.clicked.connect(lambda: self._set_badge_mode("none"))

        badge_box.addWidget(self.btn_badge_clock)
        badge_box.addWidget(self.btn_badge_weather)
        badge_box.addWidget(self.btn_badge_both)
        badge_box.addWidget(self.btn_badge_hw)
        badge_box.addWidget(self.btn_badge_none)
        c_layout.addLayout(badge_box)

        # 6. Akıllı Hızlı Asistan (Spotlight / Raycast)
        c_layout.addWidget(self._make_section_title("⚡ Akıllı Hızlı Asistan (Spotlight)"))
        self.btn_autopilot = QPushButton("⚡ Yerel & Ultra Hızlı Mod (0ms Gecikme, Bulutsuz)")
        self.btn_autopilot.setCursor(Qt.PointingHandCursor)
        self.btn_autopilot.clicked.connect(self._toggle_autopilot)
        c_layout.addWidget(self.btn_autopilot)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QLabel("⚡ Değişiklikler anında canlı olarak uygulanır")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 10px; color: #767694;")
        main_layout.addWidget(footer)

    def _make_section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #e2e2ec; margin-top: 4px;")
        return lbl

    def _make_pill_button(self, text: str, data) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("val", data)
        btn.setStyleSheet(self._btn_style(False))
        return btn

    def _btn_style(self, selected: bool) -> str:
        accent = self.settings.get("accent_color", "#926ee4")
        if selected:
            return (
                f"QPushButton {{ background: {accent}; color: #ffffff; border-radius: 8px; "
                f"padding: 5px 10px; font-size: 11px; font-weight: bold; border: none; }}"
            )
        else:
            return (
                "QPushButton { background: rgba(255,255,255,14); color: #c0c0d8; border-radius: 8px; "
                "padding: 5px 10px; font-size: 11px; border: 1px solid rgba(255,255,255,16); } "
                "QPushButton:hover { background: rgba(255,255,255,26); color: #ffffff; }"
            )

    def _apply_current_states(self):
        # 1. Island Style
        cur_style = self.settings.island_style
        self.btn_pill.setStyleSheet(self._btn_style(cur_style == "pill"))
        self.btn_notch.setStyleSheet(self._btn_style(cur_style == "notch"))

        # 2. Scale
        cur_scale = self.settings.scale
        self.btn_scale_sm.setStyleSheet(self._btn_style(abs(cur_scale - 0.85) < 0.05))
        self.btn_scale_md.setStyleSheet(self._btn_style(abs(cur_scale - 1.0) < 0.05))
        self.btn_scale_lg.setStyleSheet(self._btn_style(abs(cur_scale - 1.15) < 0.05))

        # 3. Accent Color
        cur_color = self.settings.get("accent_color", "#926ee4").lower()
        for b in self._color_buttons:
            b.is_selected = (b.color_hex.lower() == cur_color)
            b.update()

        # 4. Eye Mode
        cur_eye = self.settings.eye_color_mode
        for eid, btn in self._eye_buttons:
            btn.setStyleSheet(self._btn_style(eid == cur_eye))

        # 5. Badge Mode
        cur_badge = self.settings.badge_mode
        self.btn_badge_clock.setStyleSheet(self._btn_style(cur_badge == "clock"))
        self.btn_badge_weather.setStyleSheet(self._btn_style(cur_badge == "weather"))
        self.btn_badge_both.setStyleSheet(self._btn_style(cur_badge == "both"))
        self.btn_badge_hw.setStyleSheet(self._btn_style(cur_badge == "hardware"))
        self.btn_badge_none.setStyleSheet(self._btn_style(cur_badge == "none"))

        # 6. Autopilot / Fast Mode
        ap = self.settings.ai_autopilot
        if ap:
            self.btn_autopilot.setText("⚡ Yerel & Ultra Hızlı Mod Aktif (0ms Gecikme, Bulutsuz)")
            self.btn_autopilot.setStyleSheet(
                "QPushButton { background: rgba(29, 185, 84, 40); color: #1db954; "
                "border: 1px solid #1db954; border-radius: 8px; padding: 7px; font-weight: bold; font-size: 11px; }"
            )
        else:
            self.btn_autopilot.setText("🔒 Hızlı Komut Asistanı Pasif")
            self.btn_autopilot.setStyleSheet(
                "QPushButton { background: rgba(255, 77, 109, 30); color: #ff4d6d; "
                "border: 1px solid #ff4d6d; border-radius: 8px; padding: 7px; font-weight: bold; font-size: 11px; }"
            )

        self.update()

    def _set_island_style(self, style: str):
        self.settings.set("island_style", style)
        self._apply_current_states()

    def _set_scale(self, scale: float):
        self.settings.set("island_scale", scale)
        self._apply_current_states()

    def _set_accent_color(self, hex_val: str):
        self.settings.set("accent_color", hex_val)
        self._apply_current_states()

    def _set_eye_mode(self, eye_mode: str):
        self.settings.set("eye_color_mode", eye_mode)
        self._apply_current_states()

    def _set_badge_mode(self, badge_mode: str):
        self.settings.set("badge_mode", badge_mode)
        self._apply_current_states()

    def _toggle_autopilot(self):
        new_val = not self.settings.ai_autopilot
        self.settings.set("ai_autopilot", new_val)
        self._apply_current_states()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
