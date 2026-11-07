# Dynamic Island Linux 🏝️🤖
> **Apple iPhone 14/15 Dynamic Island + macOS NotchNook Control Center** for Linux (KDE Plasma 6, Wayland).  
> Built with **Python 3, PySide6, and Wayland LayerShell**.

---

## ✨ Features

* **🏝️ Dynamic Island & MacBook Notch Modes:**
  * **Adaptive Pill / Notch:** Floating pill or sleek MacBook Pro screen-attached notch style.
  * **Live Digital Clock & Custom Badges:** Date, time, weather, or hardware telemetry at a glance.
  * **Zero Latency & Hardware Accelerated:** Native Qt rendering with spring physics.

* **🤖 Autonomous Living Robo Eyes:**
  * **Gaze Tracking:** Robot eyes autonomously follow your mouse cursor on hover.
  * **Dynamic Reactions:**
    * 🎵 **Heart Eyes:** Reacts when a new track starts.
    * 😊 **Smile & Look Up:** Welcomes you when the control center opens.
    * 😉 **Wink:** Greets you when closing the panel.
    * ⚡ **Reading/Typing Gaze:** Scans left and right as you type in the command bar.
  * Fully customizable or can be hidden completely in the Settings window.

* **🎛️ NotchNook Expanded Control Center (Dual-Card Hub):**
  * **Tile 1 (Media Player):** Live Spotify album artwork, track seek bar, play/pause, prev, next controls with dynamic particle animations.
  * **Tile 2 (System Telemetry & Controls):** Live CPU usage, RAM usage, interactive Volume slider.
  * **Quick Toggles (3x2 Grid):** Wi-Fi, Bluetooth, Night Light, GameMode/Performance, Audio Mute, and Screenshot.
  * **Connected Devices:** Live battery ring for Bluetooth Earbuds & KDE Connect Phone (e.g. Galaxy S25 FE).

* **⚡ Local Command Palette (Spotlight / Raycast style):**
  * Press `Ctrl+Alt+A` anywhere to launch the ultra-fast local command assistant.
  * Real-time preview and 0ms execution:
    * `ram`, `cpu`, `disk` — instant hardware telemetry
    * `ses 80`, `mute` — audio control
    * `sonraki`, `duraklat`, `oynat` — Spotify control
    * `45 * 12`, `sqrt(144)` — safe math evaluator & auto-clipboard
    * `telefon` — KDE Connect phone battery & status
    * `steam`, `discord`, `kod` — app launcher

* **🎨 Customization Window (`Ctrl+Alt+S`):**
  * Island style (Floating Pill vs. Top Notch)
  * Island scale (85% compact, 100% standard, 115% wide)
  * Theme accent colors (Neon Purple, Cyber Cyan, Emerald Green, etc.)
  * Eye modes (Auto, Custom colors, or Hide Eyes)
  * Badge modes (Clock, Weather, Alternate, Hardware, or Hidden)

---

## 🚀 Installation & Requirements

### Prerequisites
* **Arch Linux / CachyOS / Fedora / Ubuntu** (Wayland session, KDE Plasma 6 recommended)
* `python3`, `python-pyside6`, `python-psutil`
* Spotify (official client or Spotify Web)
* PipeWire / WirePlumber (`wpctl` or `pactl`)

```bash
# Clone the repository
git clone https://github.com/Baysim33/dynamic-island-linux.git
cd dynamic-island-linux

# Install python dependencies
pip install -r requirements.txt
```

### Running
```bash
python3 main.py
```

### Systemd User Service (Auto-start on login)
Create `~/.config/systemd/user/spotify-island.service`:
```ini
[Unit]
Description=Dynamic Island Linux
After=graphical-session.target

[Service]
ExecStart=/usr/bin/python3 /home/YOUR_USER/dynamic-island-linux/main.py
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```
Enable and start:
```bash
systemctl --user enable --now spotify-island.service
```

---

## ⌨️ Shortcuts
* `Click on Notch`: Toggle NotchNook Quick Control Center
* `Ctrl + Alt + A`: Open Fast Command Palette
* `Ctrl + Alt + P`: Toggle Control Panel
* `Ctrl + Alt + S`: Open Settings & Customization
* `Esc`: Close open overlays

---

## 📜 License
MIT License. Created with ❤️ for the Linux community.
