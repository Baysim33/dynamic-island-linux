"""
Notification Watcher for Robo Island.
Monitors system notifications over DBus without blocking.
Emits Qt signals when a notification arrives so Dynamic Island displays it.
"""
import subprocess
import threading
import time
from PySide6.QtCore import QObject, Signal


class NotificationWatcher(QObject):
    notification_received = Signal(str, str, str, str)  # app_name, summary, body, icon

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print("[NotificationWatcher] Started — listening for system notifications")

    def stop(self):
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _monitor_loop(self):
        cmd = [
            "dbus-monitor",
            "type='method_call',path='/org/freedesktop/Notifications',member='Notify'"
        ]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
        except Exception as e:
            print(f"[NotificationWatcher] Failed to start dbus-monitor: {e}")
            return

        while self._running and self._proc.poll() is None:
            line = self._proc.stdout.readline()
            if not line:
                break

            if "member=Notify" in line:
                # Next strings in order: app_name, replaces_id (uint), app_icon, summary, body
                try:
                    app_name = self._read_next_string(self._proc.stdout)
                    # Next line might be uint32 (replaces_id)
                    _ = self._proc.stdout.readline()
                    app_icon = self._read_next_string(self._proc.stdout)
                    summary  = self._read_next_string(self._proc.stdout)
                    body     = self._read_next_string(self._proc.stdout)

                    # Filter out notifications sent by ourselves or empty
                    if app_name and app_name.lower() not in ("spotifyisland", "roboisland"):
                        if summary or body:
                            self.notification_received.emit(
                                app_name.strip(),
                                summary.strip(),
                                body.strip(),
                                app_icon.strip()
                            )
                except Exception:
                    pass

    def _read_next_string(self, stream) -> str:
        """Reads stream until a 'string \"...\"' line is encountered."""
        for _ in range(8):
            line = stream.readline()
            if not line:
                return ""
            line_str = line.strip()
            if line_str.startswith('string "') and line_str.endswith('"'):
                return line_str[8:-1]
        return ""
