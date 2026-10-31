"""
Spotify MPRIS2 DBus Client & Album Art Downloader for Spotify-Island.
"""
import os
import hashlib
import urllib.request
import dbus
from dbus.mainloop.glib import DBusGMainLoop
from PySide6.QtCore import QObject, Signal, QTimer

CACHE_DIR = "/tmp/spotify_island_cache"
os.makedirs(CACHE_DIR, exist_ok=True)


class SpotifyClient(QObject):
    status_changed = Signal(str)  # 'Playing', 'Paused', 'Stopped'
    track_changed = Signal(dict)   # {'title', 'artist', 'album', 'cover_path', 'track_id'}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_track_id = ""
        self.current_status = "Stopped"
        self.current_cover_path = ""

        # Poll timer as robust fallback for Wayland/MPRIS
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(250)
        self.poll_timer.timeout.connect(self.check_spotify)
        self.poll_timer.start()

        # Initial check
        self.check_spotify()

    def _get_spotify_props(self):
        try:
            bus = dbus.SessionBus()
            spotify = bus.get_object("org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2")
            props = dbus.Interface(spotify, "org.freedesktop.DBus.Properties")
            meta = props.Get("org.mpris.MediaPlayer2.Player", "Metadata")
            status = str(props.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus"))
            return status, meta
        except Exception:
            return "Stopped", None

    def get_progress(self):
        """Returns (position_sec, length_sec, ratio 0.0-1.0)"""
        try:
            bus = dbus.SessionBus()
            spotify = bus.get_object("org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2")
            props = dbus.Interface(spotify, "org.freedesktop.DBus.Properties")
            pos_us = int(props.Get("org.mpris.MediaPlayer2.Player", "Position"))
            meta = props.Get("org.mpris.MediaPlayer2.Player", "Metadata")
            len_us = int(meta.get("mpris:length", 0))
            pos_s = pos_us // 1000000
            len_s = len_us // 1000000
            ratio = min(1.0, max(0.0, pos_s / float(len_s))) if len_s > 0 else 0.0
            return pos_s, len_s, ratio
        except Exception:
            return 0, 0, 0.0

    def _download_cover(self, url: str) -> str:
        if not url:
            return ""
        if url.startswith("file://"):
            return url.replace("file://", "")

        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        local_path = os.path.join(CACHE_DIR, f"{url_hash}.jpg")
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            return local_path

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = resp.read()
                with open(local_path, "wb") as f:
                    f.write(data)
            return local_path
        except Exception as e:
            print(f"Album kapağı indirilemedi ({url}): {e}")
            return ""

    def check_spotify(self):
        status, meta = self._get_spotify_props()

        if status != self.current_status:
            self.current_status = status
            self.status_changed.emit(status)

        if not meta or status == "Stopped":
            return

        track_id = str(meta.get("mpris:trackid", ""))
        title = str(meta.get("xesam:title", "Bilinmeyen Parça"))
        
        # Artist parsing (can be dbus.Array)
        artists = meta.get("xesam:artist", ["Bilinmeyen Sanatçı"])
        artist = ", ".join([str(a) for a in artists]) if isinstance(artists, (list, tuple, dbus.Array)) else str(artists)
        
        album = str(meta.get("xesam:album", ""))
        art_url = str(meta.get("mpris:artUrl", ""))

        # Check if track actually changed (manual skip OR natural song completion)
        track_key = f"{track_id}|{title}|{artist}"
        if not hasattr(self, "current_track_key"):
            self.current_track_key = ""

        if track_key != self.current_track_key or not self.current_cover_path:
            self.current_track_key = track_key
            self.current_track_id = track_id
            cover_path = self._download_cover(art_url)
            self.current_cover_path = cover_path

            track_data = {
                "track_id": track_id,
                "title": title,
                "artist": artist,
                "album": album,
                "cover_path": cover_path,
                "status": status
            }
            self.track_changed.emit(track_data)
