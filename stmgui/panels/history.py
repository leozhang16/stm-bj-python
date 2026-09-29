"""Igor's history window: every Print, every log line, in order."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk


class HistoryWindow(tk.Toplevel):
    MAX_LINES = 5000

    def __init__(self, master, position=(20, 620)):
        super().__init__(master)
        self.title("History")
        self.geometry(f"720x260+{position[0]}+{position[1]}")
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self.text = tk.Text(frame, font=("Menlo", 10) if _is_mac() else
                            ("Consolas", 10), wrap="none", state="disabled")
        ys = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=ys.set)
        self.text.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.text.tag_configure("error", foreground="#cc0000")
        self.text.tag_configure("warn", foreground="#aa6600")
        self._n = 0

    def append(self, line: str, tag: str | None = None) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.text.configure(state="normal")
        self.text.insert("end", f"{stamp}  {line}\n", tag or ())
        self._n += 1
        if self._n > self.MAX_LINES:
            self.text.delete("1.0", "200.0")
            self._n -= 200
        self.text.see("end")
        self.text.configure(state="disabled")

    def on_event(self, kind: str, payload) -> None:
        if kind == "log":
            text = str(payload)
            tag = "warn" if text.startswith("W ") else \
                "error" if text.startswith("E ") else None
            self.append(text, tag)
        elif kind == "error":
            self.append(f"ERROR {payload}", "error")


def _is_mac() -> bool:
    import sys
    return sys.platform == "darwin"
