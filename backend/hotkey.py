"""
Hotkey Listener for Spotify / Robo Island.
Listens for Ctrl+Alt+Space (and Ctrl+Alt+` or Ctrl+Alt+P) on Wayland without KDE shortcuts.
Ctrl+Alt+A -> toggle_ai (Robo AI Asistanı)
Meta+Space is left untouched (handled by KDE Plasma).

Runs in a daemon thread; emits toggle_panel / toggle_ai Signal to Qt main thread.
"""
import threading
import time
from PySide6.QtCore import QObject, Signal

try:
    import evdev
    from evdev import categorize, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False

TRIGGER_KEYS = set()
if EVDEV_AVAILABLE:
    TRIGGER_KEYS = {
        ecodes.KEY_SPACE,  # Ctrl+Alt+Space -> Hızlı Panel
        ecodes.KEY_GRAVE,  # Ctrl+Alt+` -> Hızlı Panel
        ecodes.KEY_P,      # Ctrl+Alt+P  -> Hızlı Panel
        ecodes.KEY_A,      # Ctrl+Alt+A  -> Robo AI Asistanı!
        ecodes.KEY_S,      # Ctrl+Alt+S  -> Kişiselleştirme & Ayarlar!
    }

REQUIRE_CTRL = True
REQUIRE_ALT  = True
DEBOUNCE_MS  = 350


def _find_keyboards():
    if not EVDEV_AVAILABLE:
        return []
    keyboards = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps and ecodes.KEY_A in caps[ecodes.EV_KEY]:
                keyboards.append(dev)
        except Exception:
            pass
    return keyboards


class HotkeyListener(QObject):
    toggle_panel    = Signal()
    toggle_ai       = Signal()
    toggle_settings = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_trigger = 0.0

    def start(self):
        if not EVDEV_AVAILABLE:
            print("[HotkeyListener] evdev not available — hotkey disabled")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[HotkeyListener] Started — listening for Ctrl+Alt+[Space/`/P/A]")

    def stop(self):
        self._running = False

    def _loop(self):
        keyboards = _find_keyboards()
        if not keyboards:
            print("[HotkeyListener] No keyboards found")
            return

        import select
        pressed = set()

        while self._running:
            fds = {dev.fd: dev for dev in keyboards}
            try:
                ready, _, _ = select.select(fds.keys(), [], [], 1.0)
            except Exception:
                time.sleep(0.1)
                continue

            for fd in ready:
                dev = fds[fd]
                try:
                    for event in dev.read():
                        if event.type != ecodes.EV_KEY:
                            continue
                        kev = categorize(event)

                        if kev.keystate == kev.key_down:
                            pressed.add(kev.scancode)
                        elif kev.keystate == kev.key_up:
                            pressed.discard(kev.scancode)

                        # Check combo on key down
                        if (kev.keystate == kev.key_down
                                and kev.scancode in TRIGGER_KEYS):
                            ctrl_ok = (ecodes.KEY_LEFTCTRL in pressed or
                                       ecodes.KEY_RIGHTCTRL in pressed)
                            alt_ok  = (ecodes.KEY_LEFTALT in pressed or
                                       ecodes.KEY_RIGHTALT in pressed)

                            if ctrl_ok and alt_ok:
                                now = time.time()
                                if now - self._last_trigger > (DEBOUNCE_MS / 1000.0):
                                    self._last_trigger = now
                                    if kev.scancode == ecodes.KEY_A:
                                        self.toggle_ai.emit()
                                    elif kev.scancode == ecodes.KEY_S:
                                        self.toggle_settings.emit()
                                    else:
                                        self.toggle_panel.emit()
                except OSError:
                    keyboards = _find_keyboards()
                    break
