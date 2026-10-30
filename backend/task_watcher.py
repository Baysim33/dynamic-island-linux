"""
Task Watcher for Robo Island.
Monitors background AI/coding tasks and emits signals when status changes.

Supports two input methods:
  1. IPC socket commands (via main.py)
  2. Process name detection (agy, claude, gemini CLI running → auto task mode)

Signal contract (emitted to DynamicIsland):
  task_started(message: str)
  task_done(message: str)
  task_waiting(message: str)
  task_cancelled()
"""
import os
import subprocess
from PySide6.QtCore import QObject, Signal, QTimer


WATCHED_PROCESSES = [
    "agy", "claude", "gemini", "codex", "aider",
]


class TaskWatcher(QObject):
    task_started  = Signal(str)
    task_done     = Signal(str)
    task_waiting  = Signal(str)
    task_cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_mode = False   # True when a watched process is detected
        self._manual_task = False # True when set via IPC

        # Poll process list every 5 seconds for auto-detection
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(5000)
        self._auto_timer.timeout.connect(self._check_processes)
        self._auto_timer.start()
        self._check_processes()

    # ── IPC commands (called from main.py) ────────────────────────────────

    def handle_command(self, command: str):
        """Parse a raw IPC command string and emit the right signal."""
        command = command.strip()
        if command.startswith("task_start:"):
            msg = command[len("task_start:"):].strip() or "Görev çalışıyor…"
            self._manual_task = True
            self.task_started.emit(msg)
        elif command.startswith("task_done:"):
            msg = command[len("task_done:"):].strip() or "Tamamlandı!"
            self._manual_task = False
            self.task_done.emit(msg)
        elif command.startswith("task_wait:"):
            msg = command[len("task_wait:"):].strip() or "Onay bekleniyor…"
            self.task_waiting.emit(msg)
        elif command in ("task_cancel", "task_cancelled"):
            self._manual_task = False
            self.task_cancelled.emit()

    # ── Auto process detection ─────────────────────────────────────────────

    def _check_processes(self):
        if self._manual_task:
            return  # Manual IPC takes priority; don't clobber it

        try:
            result = subprocess.run(
                ["pgrep", "-l", "-f", "|".join(WATCHED_PROCESSES)],
                capture_output=True, text=True, timeout=2
            )
            found = bool(result.stdout.strip())
        except Exception:
            found = False

        if found and not self._auto_mode:
            self._auto_mode = True
            # Detect which tool is running
            lines = result.stdout.strip().split("\n") if result.stdout else []
            name = "AI görevi"
            for line in lines:
                for proc in WATCHED_PROCESSES:
                    if proc in line.lower():
                        name = proc.capitalize()
                        break
            self.task_started.emit(f"{name} arka planda çalışıyor")

        elif not found and self._auto_mode:
            self._auto_mode = False
            self.task_done.emit("Görev tamamlandı")
