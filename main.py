#!/usr/bin/env python3
"""
Robo Island — Main Daemon Entrypoint.
AI Robot Face + Spotify Dynamic Island + Background Task Monitor.
"""
import sys
import os
import signal

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from backend.spotify_client import SpotifyClient
from backend.game_detector import GameMonitorDetector
from backend.task_watcher import TaskWatcher
from ui.island_window import DynamicIsland

SOCKET_NAME = f"spotify_island_ipc_{os.getenv('USER', 'default')}"


def send_ipc_command(command: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(SOCKET_NAME)
    if socket.waitForConnected(150):
        socket.write(f"{command}\n".encode("utf-8"))
        socket.waitForBytesWritten(150)
        socket.disconnectFromServer()
        return True
    return False


def main():
    # ── CLI commands (sent to running instance via IPC) ───────────────────
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ("--quit", "-q"):
            send_ipc_command("quit")
            sys.exit(0)
        # Pass task commands directly to running daemon
        if arg.startswith("--task-"):
            # e.g. --task-start "Claude Code refactoring"
            #      --task-done  "Bitti!"
            #      --task-wait  "Devam edeyim mi?"
            #      --task-cancel
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
                else:
                    print("[RoboIsland] Daemon çalışmıyor, başlatılıyor…")

    # ── Single-instance check ─────────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setApplicationName("RoboIsland")
    app.setQuitOnLastWindowClosed(False)

    if send_ipc_command("ping"):
        print("Robo Island zaten arka planda çalışıyor.")
        sys.exit(0)

    # ── IPC Server ────────────────────────────────────────────────────────
    QLocalServer.removeServer(SOCKET_NAME)
    server = QLocalServer()
    server.listen(SOCKET_NAME)

    # ── Components ────────────────────────────────────────────────────────
    detector = GameMonitorDetector()
    island   = DynamicIsland(target_screen_name=detector.current_target_screen)
    watcher  = TaskWatcher()

    # Screen changes
    detector.target_screen_changed.connect(island.set_target_screen)

    # Spotify
    spotify = SpotifyClient()
    spotify.status_changed.connect(island.on_playback_status)
    spotify.track_changed.connect(island.on_track_changed)

    # Task monitoring
    watcher.task_started.connect(island.on_task_started)
    watcher.task_done.connect(island.on_task_done)
    watcher.task_waiting.connect(island.on_task_waiting)
    watcher.task_cancelled.connect(island.on_task_cancelled)

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
                elif cmd == "ping":
                    pass  # Just used to check if daemon is alive
                elif cmd.startswith("task_"):
                    # Forward to TaskWatcher
                    watcher.handle_command(cmd)
            client.close()

        client.readyRead.connect(read)

    server.newConnection.connect(handle_ipc)

    signal.signal(signal.SIGINT, lambda *args: app.quit())

    print("🤖 Robo Island başarıyla başlatıldı.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
