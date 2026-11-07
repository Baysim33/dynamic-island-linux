"""
Settings Manager for Spotify / Robo Island.
Persists user preferences in ~/.config/spotify-island/settings.json
Provides live reactive updates via Qt signals.
"""
import os
import json
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

CONFIG_DIR = os.path.expanduser("~/.config/spotify-island")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "accent_color": "#926ee4",       # Neon Violet (Default)
    "eye_color_mode": "auto",        # auto, violet, cyan, green, amber, red, white
    "island_style": "pill",          # pill (iPhone Island floating) or notch (MacBook attached to top)
    "badge_mode": "both",            # clock, weather, both, hardware
    "island_scale": 1.0,             # 0.85 (compact), 1.0 (standard), 1.15 (large)
    "ai_autopilot": True,            # allow AI to run system actions (volume, launch apps, etc.)
}

PRESET_COLORS = [
    {"name": "Neon Mor",     "hex": "#926ee4"},
    {"name": "Siber Cyan",   "hex": "#00c8ff"},
    {"name": "Zümrüt Yeşil", "hex": "#1db954"},
    {"name": "Ateş Kırmızı", "hex": "#ff4d6d"},
    {"name": "Altın Sarı",   "hex": "#ffb703"},
    {"name": "Buz Mavisi",   "hex": "#70d6ff"},
    {"name": "Kutup Beyazı", "hex": "#f0f2f5"},
]

EYE_COLOR_PRESETS = [
    {"id": "auto",   "name": "Otomatik (Canlı)",     "hex": "#00c8ff"},
    {"id": "violet", "name": "Mor",                 "hex": "#926ee4"},
    {"id": "cyan",   "name": "Cyan",                "hex": "#00c8ff"},
    {"id": "green",  "name": "Yeşil",               "hex": "#1db954"},
    {"id": "amber",  "name": "Amber",               "hex": "#ffb703"},
    {"id": "red",    "name": "Kırmızı",             "hex": "#ff4d6d"},
    {"id": "white",  "name": "Beyaz",               "hex": "#ffffff"},
    {"id": "off",    "name": "Gözleri Kapat / Gizle", "hex": "#4a4a5a"},
]


class SettingsManager(QObject):
    settings_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._settings.update(data)
            else:
                self.save()
        except Exception as e:
            print(f"[SettingsManager] Error loading settings: {e}")

    def save(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SettingsManager] Error saving settings: {e}")

    def get(self, key, default=None):
        return self._settings.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))

    def set(self, key, value):
        if self._settings.get(key) != value:
            self._settings[key] = value
            self.save()
            self.settings_changed.emit(self._settings)

    def update_all(self, new_data: dict):
        self._settings.update(new_data)
        self.save()
        self.settings_changed.emit(self._settings)

    @property
    def accent_qcolor(self) -> QColor:
        return QColor(self.get("accent_color", "#926ee4"))

    @property
    def scale(self) -> float:
        return float(self.get("island_scale", 1.0))

    @property
    def island_style(self) -> str:
        return self.get("island_style", "pill")

    @property
    def badge_mode(self) -> str:
        return self.get("badge_mode", "both")

    @property
    def eye_color_mode(self) -> str:
        return self.get("eye_color_mode", "auto")

    @property
    def ai_autopilot(self) -> bool:
        return bool(self.get("ai_autopilot", True))


# Global singleton instance
_instance = None

def get_settings() -> SettingsManager:
    global _instance
    if _instance is None:
        _instance = SettingsManager()
    return _instance
