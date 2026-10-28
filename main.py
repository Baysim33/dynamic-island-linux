#!/usr/bin/env python3
"""
Spotify-Island (Apple Dynamic Island with Ash Wind Particle Transitions for Linux/Wayland)
Main Daemon entrypoint.
"""
import sys
import os
import signal

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Force high-performance Wayland rendering
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from backend.spotify_client import SpotifyClient
from backend.game_detector import GameMonitorDetector
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
    if len(sys.argv) > 1 and sys.argv[1] in ("--quit", "-q"):
        send_ipc_command("quit")
        sys.exit(0)

    # Initialize Qt App
    app = QApplication(sys.argv)
    app.setApplicationName("SpotifyIsland")
    app.setQuitOnLastWindowClosed(False)

    if send_ipc_command("ping"):
        print("Spotify-Island zaten arka planda çalışıyor.")
        sys.exit(0)

    # Single instance IPC server
    QLocalServer.removeServer(SOCKET_NAME)
    server = QLocalServer()
    server.listen(SOCKET_NAME)

    # 1. Game & Multi-monitor detector
    detector = GameMonitorDetector()

    # 2. Dynamic Island UI
    island = DynamicIsland(target_screen_name=detector.current_target_screen)
    detector.target_screen_changed.connect(island.set_target_screen)

    # 3. Spotify Client
    spotify = SpotifyClient()
    spotify.status_changed.connect(island.on_playback_status)
    spotify.track_changed.connect(island.on_track_changed)

    # IPC connection
    def handle_ipc():
        client = server.nextPendingConnection()
        if not client:
            return
        def read():
            while client.bytesAvailable():
                cmd = str(client.readLine(), "utf-8").strip()
                if cmd == "quit":
                    app.quit()
            client.close()
        client.readyRead.connect(read)

    server.newConnection.connect(handle_ipc)

    # Graceful exit on SIGINT
    signal.signal(signal.SIGINT, lambda *args: app.quit())

    print("Spotify-Island başarıyla başlatıldı.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
