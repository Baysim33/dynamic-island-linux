"""
Device & Battery Monitor for Robo Island.
Tracks:
  1. KDE Connect paired phones (Galaxy S25 FE) battery percentage & charging status.
  2. Bluetooth audio devices (Galaxy Buds2, HAVIT I62) connection state & battery level.
Emits Qt signals when accessories connect or battery updates.
"""
import subprocess
import re
from PySide6.QtCore import QObject, Signal, QTimer


class DeviceBatteryWatcher(QObject):
    # Emitted when a bluetooth headset/earbuds connect
    device_connected = Signal(str, int)  # name, battery_pct (-1 if unknown)
    # Emitted periodically with updated phone and accessory battery info
    battery_updated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._previous_bt_connected = set()

        self.phone_info = {
            "name": "Telefon",
            "charge": -1,
            "is_charging": False,
            "is_reachable": False
        }

        self.bt_audio_info = {
            "name": "",
            "connected": False,
            "battery": -1
        }

        # Poll every 3 seconds
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._poll_all)
        self._timer.start()
        # Initial poll
        QTimer.singleShot(200, self._poll_all)

    def _poll_all(self):
        self._poll_kde_connect()
        self._poll_bluetooth()
        self.battery_updated.emit({
            "phone": self.phone_info,
            "headset": self.bt_audio_info
        })

    def _poll_kde_connect(self):
        try:
            # Query device list from KDE Connect
            out = subprocess.run(
                ["qdbus6", "org.kde.kdeconnect", "/modules/kdeconnect", "org.kde.kdeconnect.daemon.devices"],
                capture_output=True, text=True, timeout=0.8
            ).stdout.strip().splitlines()

            for dev_id in out:
                if not dev_id:
                    continue
                path = f"/modules/kdeconnect/devices/{dev_id}"
                name = subprocess.run(
                    ["qdbus6", "org.kde.kdeconnect", path, "org.kde.kdeconnect.device.name"],
                    capture_output=True, text=True, timeout=0.5
                ).stdout.strip()

                charge = subprocess.run(
                    ["qdbus6", "org.kde.kdeconnect", f"{path}/battery", "org.kde.kdeconnect.device.battery.charge"],
                    capture_output=True, text=True, timeout=0.5
                ).stdout.strip()

                is_charging = subprocess.run(
                    ["qdbus6", "org.kde.kdeconnect", f"{path}/battery", "org.kde.kdeconnect.device.battery.isCharging"],
                    capture_output=True, text=True, timeout=0.5
                ).stdout.strip()

                is_reachable = subprocess.run(
                    ["qdbus6", "org.kde.kdeconnect", path, "org.kde.kdeconnect.device.isReachable"],
                    capture_output=True, text=True, timeout=0.5
                ).stdout.strip()

                self.phone_info = {
                    "name": name or "Galaxy S25 FE",
                    "charge": int(charge) if charge.isdigit() else -1,
                    "is_charging": (is_charging.lower() == "true"),
                    "is_reachable": (is_reachable.lower() == "true")
                }
                break
        except Exception:
            pass

    def _poll_bluetooth(self):
        try:
            out = subprocess.run(
                ["bluetoothctl", "devices"],
                capture_output=True, text=True, timeout=0.8
            ).stdout.strip().splitlines()

            active_connected = set()
            headset_found = False

            for line in out:
                parts = line.split(maxsplit=2)
                if len(parts) >= 3:
                    mac = parts[1]
                    dev_name = parts[2]

                    # Filter for audio headsets / earbuds
                    info = subprocess.run(
                        ["bluetoothctl", "info", mac],
                        capture_output=True, text=True, timeout=0.6
                    ).stdout

                    is_connected = ("Connected: yes" in info)
                    if is_connected:
                        active_connected.add(mac)
                        # Check battery
                        batt_m = re.search(r"Battery Percentage:\s*0x[0-9a-fA-F]+\s*\((\d+)\)", info)
                        if not batt_m:
                            batt_m = re.search(r"Battery Percentage:\s*(\d+)", info)
                        batt_val = int(batt_m.group(1)) if batt_m else -1

                        self.bt_audio_info = {
                            "name": dev_name,
                            "connected": True,
                            "battery": batt_val
                        }
                        headset_found = True

                        # If just newly connected, trigger popup alert!
                        if mac not in self._previous_bt_connected:
                            self.device_connected.emit(dev_name, batt_val)

            if not headset_found:
                self.bt_audio_info = {
                    "name": "",
                    "connected": False,
                    "battery": -1
                }

            self._previous_bt_connected = active_connected
        except Exception:
            pass
