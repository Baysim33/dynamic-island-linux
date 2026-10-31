"""
Network & Hardware Telemetry Manager for Robo Island.
Handles Wi-Fi scanning/toggling, Bluetooth state, CPU/RAM telemetry, and Weather.
"""
import subprocess
import os
import time
from PySide6.QtCore import QObject, Signal, QTimer


class NetworkManager(QObject):
    wifi_status_changed = Signal(dict)
    telemetry_updated   = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wifi_enabled = True
        self.bt_enabled = True
        self.airplane_mode = False
        self.connected_ssid = ""
        self.networks = []

        self.cpu_usage = 0
        self.ram_usage = 0
        self.weather_temp = "19°C"
        self.weather_condition = "Açık"

        self._last_cpu_stat = None

        # Telemetry poll timer (every 2.5s)
        self._timer = QTimer(self)
        self._timer.setInterval(2500)
        self._timer.timeout.connect(self._poll_telemetry)
        self._timer.start()

        # Weather timer (every 10 minutes)
        self._weather_timer = QTimer(self)
        self._weather_timer.setInterval(600000)
        self._weather_timer.timeout.connect(self._poll_weather)
        self._weather_timer.start()

        QTimer.singleShot(100, self._poll_telemetry)
        QTimer.singleShot(500, self._poll_weather)

    def toggle_wifi(self):
        new_state = "off" if self.wifi_enabled else "on"
        try:
            subprocess.run(["nmcli", "radio", "wifi", new_state], timeout=1)
            self.wifi_enabled = not self.wifi_enabled
        except Exception:
            pass
        self._poll_wifi()

    def toggle_bluetooth(self):
        new_state = "off" if self.bt_enabled else "on"
        try:
            subprocess.run(["bluetoothctl", "power", new_state], timeout=1)
            self.bt_enabled = not self.bt_enabled
        except Exception:
            pass

    def toggle_airplane(self):
        self.airplane_mode = not self.airplane_mode
        try:
            val = "on" if not self.airplane_mode else "off"
            subprocess.run(["nmcli", "radio", "all", val], timeout=1)
        except Exception:
            pass

    def _poll_telemetry(self):
        self._poll_wifi()
        self._poll_cpu_ram()
        self.telemetry_updated.emit({
            "cpu": self.cpu_usage,
            "ram": self.ram_usage,
            "weather_temp": self.weather_temp,
            "weather_cond": self.weather_condition,
            "wifi_enabled": self.wifi_enabled,
            "connected_ssid": self.connected_ssid,
            "networks": self.networks
        })

    def _poll_wifi(self):
        try:
            radio = subprocess.run(
                ["nmcli", "radio", "wifi"],
                capture_output=True, text=True, timeout=0.6
            ).stdout.strip().lower()
            self.wifi_enabled = (radio == "enabled")

            if self.wifi_enabled:
                out = subprocess.run(
                    ["nmcli", "dev", "wifi", "list", "--rescan", "no"],
                    capture_output=True, text=True, timeout=1.0
                ).stdout.strip().splitlines()

                nets = []
                connected_name = ""
                # Skip header line
                for line in out[1:]:
                    parts = line.split()
                    if not parts:
                        continue
                    is_active = (parts[0] == "*")
                    # SSID usually starts at index 1 or 2
                    ssid_start = 2 if is_active else 1
                    if len(parts) > ssid_start:
                        ssid = parts[ssid_start]
                        if ssid not in ("--", ""):
                            if is_active:
                                connected_name = ssid
                            nets.append({
                                "ssid": ssid,
                                "active": is_active,
                                "signal": 70 if is_active else 50
                            })
                self.connected_ssid = connected_name
                self.networks = nets[:5]
        except Exception:
            pass

    def _poll_cpu_ram(self):
        # 1. CPU from /proc/stat
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
                parts = [int(x) for x in line.split()[1:]]
                busy = sum(parts[:3]) + sum(parts[5:8])
                total = sum(parts)
                if self._last_cpu_stat:
                    d_busy = busy - self._last_cpu_stat[0]
                    d_total = total - self._last_cpu_stat[1]
                    if d_total > 0:
                        self.cpu_usage = int((d_busy / d_total) * 100)
                self._last_cpu_stat = (busy, total)
        except Exception:
            pass

        # 2. RAM from /proc/meminfo
        try:
            with open("/proc/meminfo", "r") as f:
                m = {}
                for line in f:
                    p = line.split(":")
                    if len(p) == 2:
                        m[p[0].strip()] = int(p[1].split()[0])
                total = m.get("MemTotal", 1)
                avail = m.get("MemAvailable", 0)
                self.ram_usage = int(((total - avail) / total) * 100)
        except Exception:
            pass

    def _poll_weather(self):
        try:
            res = subprocess.run(
                ["curl", "-s", "--max-time", "1.5", "https://wttr.in/?format=%t+%C"],
                capture_output=True, text=True, timeout=2.0
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split(maxsplit=1)
                if parts:
                    self.weather_temp = parts[0]
                    self.weather_condition = parts[1] if len(parts) > 1 else "Açık"
        except Exception:
            pass
