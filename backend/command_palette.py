"""
Robo Command Palette & Local Smart Assistant Engine.
100% Native, 0ms Latency, Zero API / Cloud Dependency.
Provides instant Spotlight/Raycast style control for:
  - Spotify media controls (Next, Prev, Play/Pause, Title query)
  - Audio sink volume adjustment (wpctl / PipeWire)
  - Real-time hardware telemetry (RAM, CPU, Disk, Temperatures)
  - Connected devices & battery (Galaxy S25 FE phone via KDE Connect, Bluetooth headsets)
  - Instant safe math evaluation (auto-copied to clipboard)
  - App launcher (Steam, Discord, Firefox, Terminal, Code, Dolphin, etc.)
  - Desktop quick utilities (Screenshot, Screen lock, Trash cleanup, Night light)
"""
import os
import re
import ast
import operator
import math
import shutil
import subprocess
import time
from typing import Optional, Tuple

ALLOWED_MATH_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

ALLOWED_FUNCS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "round": round,
    "pi": math.pi,
    "e": math.e,
}

POPULAR_APPS = {
    "steam": "steam",
    "discord": "discord",
    "vesktop": "vesktop",
    "spotify": "spotify",
    "firefox": "firefox",
    "chrome": "google-chrome-stable",
    "chromium": "chromium",
    "code": "code",
    "vscode": "code",
    "dolphin": "dolphin",
    "dosyalar": "dolphin",
    "dosya": "dolphin",
    "konsole": "konsole",
    "terminal": "konsole",
    "konsol": "konsole",
    "kate": "kate",
    "not defteri": "kate",
    "kcalc": "kcalc",
    "hesap makinesi": "kcalc",
    "vlc": "vlc",
    "telegram": "telegram-desktop",
    "lutris": "lutris",
    "heroic": "heroic",
    "obs": "obs",
    "gimp": "gimp",
    "blender": "blender",
    "ayarlar": "systemsettings",
    "settings": "systemsettings",
}


def _safe_eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.Name):
        if node.id in ALLOWED_FUNCS:
            return ALLOWED_FUNCS[node.id]
        raise ValueError("Forbidden identifier")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type in ALLOWED_MATH_OPS:
            left = _safe_eval_node(node.left)
            right = _safe_eval_node(node.right)
            return ALLOWED_MATH_OPS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type in ALLOWED_MATH_OPS:
            operand = _safe_eval_node(node.operand)
            return ALLOWED_MATH_OPS[op_type](operand)
    elif isinstance(node, ast.Call):
        func = _safe_eval_node(node.func)
        if callable(func):
            args = [_safe_eval_node(arg) for arg in node.args]
            return func(*args)
    raise ValueError("Invalid expression")


def try_evaluate_math(expr: str) -> Optional[float | int]:
    """Evaluates simple arithmetic expressions safely."""
    clean = expr.strip()
    # Must contain at least one math operator or known math function
    if not re.search(r"[\+\-\*/\^%]|sqrt|sin|cos|tan", clean):
        return None
    # Quick filter against dangerous words
    if any(k in clean for k in ("__", "import", "open", "exec", "eval", "os", "sys")):
        return None

    norm = clean.replace("^", "**").replace("x", "*").replace(",", ".")
    try:
        tree = ast.parse(norm, mode="eval")
        res = _safe_eval_node(tree.body)
        if isinstance(res, float) and res.is_integer():
            return int(res)
        return res
    except Exception:
        return None


def copy_to_clipboard(text: str):
    """Copies text to Wayland / X11 clipboard."""
    try:
        p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
        p.communicate(input=text.encode("utf-8"), timeout=0.5)
        return
    except Exception:
        pass
    try:
        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
        p.communicate(input=text.encode("utf-8"), timeout=0.5)
    except Exception:
        pass


class CommandPaletteEngine:
    """Zero-latency command processor and preview generator."""

    def __init__(self):
        self._phone_device_id = "4bc4747eab4e42a7874f9c704ba4927f"  # Galaxy S25 FE

    def get_preview(self, query: str) -> str:
        """Returns a real-time hint or live calculation as user types."""
        q = query.strip()
        if not q:
            return ""

        # 1. Math check
        val = try_evaluate_math(q)
        if val is not None:
            formatted = f"{val:,.4f}".rstrip("0").rstrip(".") if isinstance(val, float) else f"{val:,}"
            return f"🧮 = {formatted} (Enter: panoya kopyalar)"

        lower = q.lower()

        # 2. Media
        if any(lower.startswith(k) for k in ("sonraki", "gec", "geç", "atla", "next", "sırada", "şarkı değiştir")):
            return "🎵 Sıradaki Spotify parçasına atla"
        if any(lower.startswith(k) for k in ("önceki", "geri", "başa sar", "onceki", "prev")):
            return "⏮️ Önceki Spotify parçasına dön"
        if any(lower.startswith(k) for k in ("dur", "durdur", "duraklat", "pause")):
            return "⏸️ Spotify'ı duraklat"
        if any(lower.startswith(k) for k in ("oynat", "başlat", "devam", "çal", "play")):
            return "▶️ Spotify'ı oynat"
        if any(k in lower for k in ("çalan", "ne çalıyor", "şarkı ne", "müzik ne")):
            return "🎶 Şu an çalan Spotify parçasını göster"

        # 3. Volume
        vol_match = re.search(r"(?:ses|vol|volume)\s*(?:seviyesi|ayar)?\s*(\d{1,3})", lower)
        if vol_match:
            pct = max(0, min(100, int(vol_match.group(1))))
            return f"🔊 Ses seviyesini %{pct} yap"
        if any(k in lower for k in ("ses artır", "ses yükselt", "ses aç", "ses +")):
            return "🔊 Sesi %10 artır"
        if any(k in lower for k in ("ses kıs", "ses azalt", "ses -")):
            return "🔉 Sesi %10 azalt"
        if any(k in lower for k in ("sustur", "mute", "sesi kapat")):
            return "🔇 Sesi tamamen kapat (Mute)"
        if any(k in lower for k in ("sesi aç", "unmute")):
            return "🔊 Sesi aç (Unmute)"

        # 4. Hardware Telemetry
        if any(k in lower for k in ("ram", "bellek", "hafıza")):
            try:
                import psutil
                vm = psutil.virtual_memory()
                return f"⚡ RAM: %{vm.percent:.1f} ({vm.used / (1024**3):.1f} / {vm.total / (1024**3):.1f} GB)"
            except Exception:
                return "⚡ RAM durumunu göster"

        if any(k in lower for k in ("cpu", "işlemci", "yük")):
            try:
                import psutil
                return f"🚀 CPU Yükü: %{psutil.cpu_percent(interval=None)} ({psutil.cpu_count(logical=True)} Çekirdek)"
            except Exception:
                return "🚀 İşlemci yükünü göster"

        if any(k in lower for k in ("disk", "depolama", "ssd", "hdd", "alan")):
            try:
                import psutil
                du = psutil.disk_usage("/")
                return f"💾 Disk: %{du.percent:.0f} Dolu ({du.free / (1024**3):.1f} GB Boş)"
            except Exception:
                return "💾 Disk doluluğunu göster"

        if any(k in lower for k in ("donanım", "sistem", "özet", "pc")):
            return "💻 Tüm sistem donanım özetini göster"

        # 5. Phone / Galaxy S25 FE
        if any(k in lower for k in ("telefon", "s25", "galaxy", "pil", "şarj")):
            return "📱 Galaxy S25 FE pil durumunu sorgula"
        if any(k in lower for k in ("çaldır", "telefon nerede", "telefon bul")):
            return "🔔 Galaxy S25 FE telefonunu çaldır"

        # 6. Quick Desktop Tools
        if any(k in lower for k in ("ss", "ekran görüntüsü", "screenshot")):
            return "📸 Ekran görüntüsü al (Masaüstüne kaydeder)"
        if any(k in lower for k in ("kilit", "kilitle", "lock")):
            return "🔒 Masaüstü oturumunu kilitle"
        if any(k in lower for k in ("çöp", "trash")):
            return "🗑️ Çöp kutusunu temizle"
        if any(k in lower for k in ("gece ışığı", "nightlight")):
            return "🌙 KDE Gece Işığını aç/kapat"
        if any(k in lower for k in ("hava", "hava durumu")):
            return "⛅ Canlı hava durumu bilgisini göster"

        # 7. App Launcher
        clean_app = lower.replace("aç", "").replace("başlat", "").replace("run", "").strip()
        if clean_app in POPULAR_APPS:
            app_name = POPULAR_APPS[clean_app]
            return f"🚀 {clean_app.title()} uygulamasını başlat ({app_name})"

        # 8. Web Search
        if lower.startswith("google ") or lower.startswith("ara "):
            query_term = q.split(" ", 1)[1]
            return f"🔍 Google'da ara: '{query_term}'"
        if lower.startswith("yt ") or lower.startswith("youtube "):
            query_term = q.split(" ", 1)[1]
            return f"▶️ YouTube'da ara: '{query_term}'"

        # 9. General Help
        if any(k in lower for k in ("yardım", "komut", "help", "?")):
            return "💡 Komutlar: sonraki, ses 80, ram, cpu, steam, ss, telefon, 45*12..."

        return f"⚡ Komut: '{q}' (Enter ile çalıştır)"

    def execute(self, query: str) -> Tuple[str, bool]:
        """Executes the command with 0ms latency and returns (response_message, success)."""
        raw = query.strip()
        if not raw:
            return ("Boş komut.", False)

        # 1. Instant Math Evaluation
        val = try_evaluate_math(raw)
        if val is not None:
            formatted = f"{val:,.4f}".rstrip("0").rstrip(".") if isinstance(val, float) else f"{val:,}"
            copy_to_clipboard(str(formatted))
            return (f"🧮 Sonuç: {formatted}  (Panoya kopyalandı! 📋)", True)

        p = raw.lower()

        # 2. Spotify Track Skip / Next
        if any(p.startswith(k) or k in p for k in ("şarkı değiştir", "şarkıyı değiştir", "sonraki şarkı", "sonraki parça", "parça atla", "şarkıyı geç", "müziği değiştir", "başka şarkı", "sonraki", "gec", "geç", "atla", "next")):
            subprocess.run(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Next"], timeout=1)
            time.sleep(0.18)
            title, artist = self._get_spotify_meta()
            if title:
                return (f"Sıradaki Parça: '{title}' — {artist} 🎵", True)
            return ("Sıradaki parçaya geçildi! 🎵", True)

        # 3. Spotify Previous Track
        if any(p.startswith(k) or k in p for k in ("önceki parça", "önceki şarkı", "başa sar", "önceki", "onceki", "prev", "previous", "geri")):
            subprocess.run(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Previous"], timeout=1)
            time.sleep(0.18)
            title, artist = self._get_spotify_meta()
            if title:
                return (f"Önceki Parça: '{title}' — {artist} ⏮️", True)
            return ("Önceki parçaya dönüldü! ⏮️", True)

        # 4. Spotify Pause
        if any(k in p for k in ("şarkıyı durdur", "müziği durdur", "şarkıyı duraklat", "müziği duraklat", "şarkıyı kapat", "müziği kes", "dur", "durdur", "pause")):
            subprocess.run(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Pause"], timeout=1)
            return ("Müzik duraklatıldı. ⏸️", True)

        # 5. Spotify Play
        if any(k in p for k in ("şarkıyı başlat", "müziği başlat", "şarkıyı çal", "müziği çal", "devam et", "müziği aç", "oynat", "çal", "devam", "play")):
            subprocess.run(["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Play"], timeout=1)
            return ("Müzik çalıyor! ▶️", True)

        # 6. Spotify Track Info
        if any(k in p for k in ("ne çalıyor", "çalan şarkı", "şarkı ne", "müzik ne", "parça ne", "spotify")):
            title, artist = self._get_spotify_meta()
            if title:
                return (f"Çalan Şarkı: '{title}' — {artist} 🎶", True)
            return ("Şu an çalan bir Spotify parçası bulunamadı.", False)

        # 7. Volume Numeric
        vol_match = re.search(r"(?:ses|vol|volume)\s*(?:seviyesi|ayar)?\s*(\d{1,3})", p)
        if vol_match:
            pct = max(0, min(100, int(vol_match.group(1))))
            val_frac = pct / 100.0
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val_frac:.2f}"], timeout=1)
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], timeout=1)
            return (f"Ses seviyesi %{pct} yapıldı! 🔊", True)

        # Volume Adjust (+ / -)
        if any(k in p for k in ("ses artır", "ses yükselt", "ses aç", "ses +")):
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "10%+"], timeout=1)
            return ("Ses seviyesi %10 artırıldı. 🔊", True)
        if any(k in p for k in ("ses kıs", "ses azalt", "ses -")):
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "10%-"], timeout=1)
            return ("Ses seviyesi %10 kısıldı. 🔉", True)
        if any(k in p for k in ("sustur", "mute", "sesi kapat", "sesi sustur")):
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"], timeout=1)
            return ("Ses tamamen susturuldu (Mute). 🔇", True)
        if any(k in p for k in ("sesi aç", "unmute")):
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], timeout=1)
            return ("Ses açıldı. 🔊", True)

        # 8. Hardware Telemetry: RAM
        if any(k in p for k in ("ram", "bellek", "hafıza")):
            try:
                import psutil
                vm = psutil.virtual_memory()
                used_gb = vm.used / (1024**3)
                total_gb = vm.total / (1024**3)
                free_gb = vm.available / (1024**3)
                return (f"⚡ RAM: %{vm.percent:.1f} dolu  ({used_gb:.1f} GB / {total_gb:.1f} GB | Boş: {free_gb:.1f} GB)", True)
            except Exception as e:
                return (f"RAM bilgisi alınamadı: {e}", False)

        # 9. Hardware Telemetry: CPU
        if any(k in p for k in ("cpu", "işlemci", "yük")):
            try:
                import psutil
                cpu_pct = psutil.cpu_percent(interval=0.1)
                cores = psutil.cpu_count(logical=True)
                freq = psutil.cpu_freq()
                freq_mhz = f" @ {freq.current:.0f}MHz" if freq else ""
                return (f"🚀 CPU Yükü: %{cpu_pct} ({cores} Çekirdek{freq_mhz})", True)
            except Exception as e:
                return (f"CPU bilgisi alınamadı: {e}", False)

        # 10. Hardware Telemetry: Disk
        if any(k in p for k in ("disk", "depolama", "ssd", "hdd", "alan")):
            try:
                import psutil
                du = psutil.disk_usage("/")
                used_gb = du.used / (1024**3)
                total_gb = du.total / (1024**3)
                free_gb = du.free / (1024**3)
                return (f"💾 Disk (/): %{du.percent:.0f} dolu ({used_gb:.1f} GB / {total_gb:.1f} GB | Boş: {free_gb:.1f} GB)", True)
            except Exception as e:
                return (f"Disk bilgisi alınamadı: {e}", False)

        # 11. Full System Overview
        if any(k in p for k in ("donanım", "sistem", "özet", "pc")):
            try:
                import psutil
                vm = psutil.virtual_memory()
                cpu_pct = psutil.cpu_percent(interval=None)
                du = psutil.disk_usage("/")
                return (f"💻 Sistem: RAM %{vm.percent:.0f} | CPU %{cpu_pct:.0f} | Disk %{du.percent:.0f} | Durum: Harika 🚀", True)
            except Exception:
                pass

        # 12. Phone Battery & Find Phone (KDE Connect)
        if any(k in p for k in ("çaldır", "telefon nerede", "telefon bul", "telefonu çaldır")):
            res = subprocess.run(
                ["qdbus6", "org.kde.kdeconnect", f"/modules/kdeconnect/devices/{self._phone_device_id}/findmyphone",
                 "org.kde.kdeconnect.device.findmyphone.ring"],
                capture_output=True, text=True, timeout=1.5
            )
            return ("🔔 Galaxy S25 FE çaldırılıyor!", True)

        if any(k in p for k in ("telefon", "s25", "galaxy", "pil", "şarj")):
            try:
                res_charge = subprocess.run(
                    ["qdbus6", "org.kde.kdeconnect", f"/modules/kdeconnect/devices/{self._phone_device_id}/battery",
                     "org.kde.kdeconnect.device.battery.charge"],
                    capture_output=True, text=True, timeout=1.0
                )
                res_charging = subprocess.run(
                    ["qdbus6", "org.kde.kdeconnect", f"/modules/kdeconnect/devices/{self._phone_device_id}/battery",
                     "org.kde.kdeconnect.device.battery.isCharging"],
                    capture_output=True, text=True, timeout=1.0
                )
                charge = res_charge.stdout.strip()
                charging = "Şarj Oluyor ⚡" if "true" in res_charging.stdout.lower() else "Pilde 🔋"
                if charge.isdigit():
                    return (f"📱 Galaxy S25 FE: %{charge} ({charging})", True)
            except Exception:
                pass
            return ("Galaxy S25 FE cihazına ulaşılamadı (KDE Connect kontrol edin).", False)

        # 13. Screenshot
        if any(k in p for k in ("ekran görüntüsü", "ss", "screenshot")):
            desktop_dir = os.path.expanduser("~/Masaüstü")
            os.makedirs(desktop_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(desktop_dir, f"Ekran_Goruntusu_{ts}.png")
            try:
                subprocess.run(["grim", save_path], timeout=3)
                return (f"📸 Ekran görüntüsü Masaüstüne kaydedildi: Ekran_Goruntusu_{ts}.png", True)
            except Exception:
                subprocess.Popen(["spectacle", "-b", "-n", "-o", save_path])
                return ("📸 Ekran görüntüsü kaydedildi!", True)

        # 14. Screen Lock
        if any(k in p for k in ("kilit", "kilitle", "lock")):
            subprocess.Popen(["loginctl", "lock-session"])
            return ("🔒 Oturum kilitlendi.", True)

        # 15. Empty Trash
        if any(k in p for k in ("çöp", "trash")):
            trash_path = os.path.expanduser("~/.local/share/Trash")
            files_path = os.path.join(trash_path, "files")
            info_path = os.path.join(trash_path, "info")
            if os.path.exists(files_path):
                shutil.rmtree(files_path, ignore_errors=True)
                os.makedirs(files_path, exist_ok=True)
            if os.path.exists(info_path):
                shutil.rmtree(info_path, ignore_errors=True)
                os.makedirs(info_path, exist_ok=True)
            return ("🗑️ Çöp kutusu başarıyla temizlendi!", True)

        # 16. Night Light Toggle
        if any(k in p for k in ("gece ışığı", "nightlight")):
            subprocess.run(["qdbus6", "org.kde.KWin", "/org/kde/KWin/NightLight", "preview", "4500"], timeout=1)
            return ("🌙 Gece ışığı değiştirildi.", True)

        # 17. Web Searches (Google & YouTube)
        if p.startswith("google ") or p.startswith("ara "):
            query_term = raw.split(" ", 1)[1]
            url = f"https://www.google.com/search?q={urllib_quote(query_term)}"
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return (f"🔍 Google'da aranıyor: '{query_term}'", True)

        if p.startswith("yt ") or p.startswith("youtube "):
            query_term = raw.split(" ", 1)[1]
            url = f"https://www.youtube.com/results?search_query={urllib_quote(query_term)}"
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return (f"▶️ YouTube'da aranıyor: '{query_term}'", True)

        # 18. App Launching
        clean_app = p.replace("aç", "").replace("başlat", "").replace("run", "").strip()
        if clean_app in POPULAR_APPS:
            exe = POPULAR_APPS[clean_app]
            try:
                subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return (f"🚀 {clean_app.title()} başlatılıyor...", True)
            except Exception as e:
                return (f"Uygulama açılamadı: {e}", False)

        # If it looks like a direct command/binary name
        if shutil.which(clean_app):
            try:
                subprocess.Popen([clean_app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return (f"🚀 {clean_app} başlatılıyor...", True)
            except Exception as e:
                return (f"Çalıştırılamadı: {e}", False)

        # 19. Help / Fallback
        if any(k in p for k in ("yardım", "komutlar", "help", "?")):
            return ("⚡ Hızlı Komutlar: sonraki, ses 80, ram, cpu, disk, steam, ss, telefon, çaldır, 45*12, kilit, çöp", True)

        return (f"Komut anlaşılamadı: '{raw}'. Yardım için 'yardım' yazabilirsiniz.", False)

    def _get_spotify_meta(self) -> Tuple[str, str]:
        """Reads current Spotify title and artist from DBus."""
        try:
            res = subprocess.run(
                ["qdbus6", "org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2",
                 "org.freedesktop.DBus.Properties.Get", "org.mpris.MediaPlayer2.Player", "Metadata"],
                capture_output=True, text=True, timeout=0.3
            )
            title, artist = "", ""
            for line in res.stdout.splitlines():
                if line.startswith("xesam:title:"):
                    title = line.split(":", 1)[1].strip()
                elif line.startswith("xesam:artist:"):
                    artist = line.split(":", 1)[1].strip()
            return title, artist
        except Exception:
            return "", ""


def urllib_quote(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote_plus(s)
