"""
Game and Monitor Detector for Spotify-Island.
Directs the Dynamic Island to the non-gaming monitor when a game is active,
or defaults to the primary 240Hz monitor (HDMI-A-1).
"""
import os
import subprocess
from PySide6.QtCore import QObject, Signal, QTimer

PRIMARY_SCREEN_NAME = "HDMI-A-1"    # 240Hz Main monitor (priority 1)
SECONDARY_SCREEN_NAME = "HDMI-A-2"  # 75Hz Side monitor (priority 2)

# Keywords in executable paths or process command lines
GAME_BIN_PATTERNS = [
    "/steamapps/common/",
    "wineserver",
    "/proton",
    "gamescope",
    "lutris",
    "heroic",
    "gamemoderun",
    "mangohud"
]


class GameMonitorDetector(QObject):
    target_screen_changed = Signal(str)  # Emits screen name e.g. 'HDMI-A-1' or 'HDMI-A-2'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_target_screen = PRIMARY_SCREEN_NAME
        self.is_game_active = False

        self.timer = QTimer(self)
        self.timer.setInterval(1500)  # Check every 1.5 seconds
        self.timer.timeout.connect(self.check_state)
        self.timer.start()

    def get_active_kwin_output(self) -> str:
        """Query active focused screen from KWin Wayland"""
        try:
            res = subprocess.run(
                ["qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.activeOutputName"],
                capture_output=True, text=True, timeout=1
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
        return PRIMARY_SCREEN_NAME

    def is_game_running(self) -> bool:
        """Scan running processes for active games (Steam, Proton, Wine, etc.)"""
        try:
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                try:
                    with open(f"/proc/{pid}/cmdline", "rb") as f:
                        cmd = f.read().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
                        if any(pattern in cmd for pattern in GAME_BIN_PATTERNS):
                            if "spotify-island" not in cmd and "python" not in cmd.split()[0]:
                                return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def determine_target_screen(self) -> str:
        game_running = self.is_game_running()
        active_output = self.get_active_kwin_output()

        if game_running:
            # If game is running on the 240Hz monitor, move Island to side monitor
            if active_output == PRIMARY_SCREEN_NAME:
                return SECONDARY_SCREEN_NAME
            elif active_output == SECONDARY_SCREEN_NAME:
                return PRIMARY_SCREEN_NAME
            else:
                return SECONDARY_SCREEN_NAME
        else:
            return PRIMARY_SCREEN_NAME

    def check_state(self):
        new_target = self.determine_target_screen()
        if new_target != self.current_target_screen:
            self.current_target_screen = new_target
            self.target_screen_changed.emit(new_target)
