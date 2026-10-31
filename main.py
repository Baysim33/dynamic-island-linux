#!/usr/bin/env python3
"""
Robo Island — Apple iPhone 14/15 Dynamic Island & Multi-Tab Control Center.
Features:
  - Media Controls with Ash wind particle disintegration
  - Wi-Fi Manager (nmcli) & Bluetooth Manager
  - Live Notifications over DBus (replaces default OS popups)
  - KDE Connect Phone (Galaxy S25 FE) & Bluetooth Headset Battery
  - LayerShell input region click-through
"""
import sys
import os
import signal

# Ensure unbuffered stdout for journalctl
sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QGuiApplication, QCursor
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from backend.spotify_client import SpotifyClient
from backend.game_detector import GameMonitorDetector
from backend.task_watcher import TaskWatcher
from backend.hotkey import HotkeyListener
from ui.island_window import DynamicIsland

SOCKET_NAME = f"spotify_island_ipc_{os.getenv('USER', 'default')}"


def send_ipc_command(command: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(SOCKET_NAME)
    if socket.waitForConnected(200):
        socket.write(f"{command}\n".encode("utf-8"))
        socket.waitForBytesWritten(200)
        socket.waitForReadyRead(50)
        socket.disconnectFromServer()
        return True
    return False


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RoboIsland")
    app.setQuitOnLastWindowClosed(False)

    # ── CLI Commands sent to running instance ──────────────────────────────
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ("--toggle-panel", "--toggle", "-t"):
            if send_ipc_command("toggle_panel"):
                print("[RoboIsland] Hızlı Panel aç/kapat sinyali iletildi.")
            else:
                print("[RoboIsland] Ada çalışmıyor.")
            sys.exit(0)

        if arg in ("--quit", "-q"):
            send_ipc_command("quit")
            sys.exit(0)

        if arg == "--test-notif":
            msg = sys.argv[2] if len(sys.argv) > 2 else "Bu bir test bildirimidir!"
            send_ipc_command(f"test_notif:{msg}")
            sys.exit(0)

        if arg == "--test-buds":
            send_ipc_command("test_buds")
            sys.exit(0)

        if arg.startswith("--task-"):
            cmd_map = {
                "--task-start":  "task_start:",
                "--task-done":   "task_done:",
                "--task-wait":   "task_wait:",
                "--task-cancel": "task_cancel",
            }
            prefix = cmd_map.get(arg, "")
            if prefix:
                msg = sys.argv[2] if len(sys.argv) > 2 else ""
                full = prefix + msg if not prefix.endswith("task_cancel") else prefix
                if send_ipc_command(full):
                    print(f"[RoboIsland] Sent: {full}")
                    sys.exit(0)

    # ── Single-instance check ─────────────────────────────────────────────
    if send_ipc_command("ping"):
        print("Robo Island zaten arka planda çalışıyor.")
        sys.exit(0)

    # ── IPC Server ────────────────────────────────────────────────────────
    QLocalServer.removeServer(SOCKET_NAME)
    server = QLocalServer()
    server.listen(SOCKET_NAME)

    # ── Components (Dual-Monitor Dynamic Islands) ─────────────────────────
    detector = GameMonitorDetector()
    
    # Discover all connected Wayland screens (e.g. HDMI-A-1, HDMI-A-2)
    screens = QGuiApplication.screens()
    islands = []
    
    if screens:
        for s in screens:
            isl = DynamicIsland(target_screen_name=s.name())
            islands.append(isl)
    else:
        islands.append(DynamicIsland(target_screen_name=detector.current_target_screen))

    watcher = TaskWatcher()
    hotkey  = HotkeyListener()

    # Determine which island is currently active under the mouse
    def get_focused_island() -> DynamicIsland:
        cursor_pos = QCursor.pos()
        for isl in islands:
            target_scr = None
            for s in QGuiApplication.screens():
                if s.name() == isl.target_screen_name:
                    target_scr = s
                    break
            if target_scr and target_scr.geometry().contains(cursor_pos):
                return isl
        return islands[0] if islands else None

    def toggle_all_or_focused_panel():
        # Toggle on the monitor where the cursor currently resides
        focused = get_focused_island()
        if focused:
            focused.toggle_quick_panel()
        else:
            for isl in islands:
                isl.toggle_quick_panel()

    # Hotkey trigger (Ctrl+Alt+Space / Grave / P) toggles the Control Panel
    hotkey.toggle_panel.connect(toggle_all_or_focused_panel)
    hotkey.start()

    # Spotify Client broadcast to all islands
    spotify = SpotifyClient()
    for isl in islands:
        spotify.status_changed.connect(isl.on_playback_status)
        spotify.track_changed.connect(isl.on_track_changed)

    # Task Watcher broadcast to all islands
    for isl in islands:
        watcher.task_started.connect(isl.on_task_started)
        watcher.task_done.connect(isl.on_task_done)
        watcher.task_waiting.connect(isl.on_task_waiting)
        watcher.task_cancelled.connect(isl.on_task_cancelled)

    # ── IPC handler ───────────────────────────────────────────────────────
    def handle_ipc():
        client = server.nextPendingConnection()
        if not client:
            return

        def read():
            while client.bytesAvailable():
                cmd = str(client.readLine(), "utf-8").strip()
                if cmd == "quit":
                    app.quit()
                elif cmd in ("toggle_panel", "toggle"):
                    toggle_all_or_focused_panel()
                elif cmd in ("bloom_open", "bloom"):
                    for isl in islands:
                        isl.trigger_notch_bloom_open()
                elif cmd == "bloom_close":
                    for isl in islands:
                        isl.trigger_notch_bloom_close()
                elif cmd == "test_buds":
                    for isl in islands:
                        isl._on_accessory_connected("Galaxy Buds2 (A51C)", 85)
                elif cmd.startswith("test_notif:"):
                    msg = cmd[len("test_notif:"):]
                    for isl in islands:
                        isl._on_notification("Discord", "Yeni Mesaj", msg, "")
                elif cmd == "ping":
                    pass
                elif cmd.startswith("task_"):
                    watcher.handle_command(cmd)
            client.close()

        client.readyRead.connect(read)

    server.newConnection.connect(handle_ipc)

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    print("🤖 Robo Island (iPhone Dynamic Island, Bildirim Merkezi & Kontrol Paneli) başlatıldı.", flush=True)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
