"""The Button map window: every control -> Python -> Igor -> stmlab.

Igor had nothing like this; the question "what does this button run" was
answered by opening the procedure file. Here it is one window, generated
from ``controller.COMMAND_MAP`` at the moment it opens, so the file:line
numbers are those of the code actually loaded.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..controller import command_table


class ButtonMapWindow(tk.Toplevel):
    def __init__(self, master, position=(120, 80)):
        super().__init__(master)
        self.title("Button map: control -> Python -> Igor -> stmlab")
        self.geometry(f"900x600+{position[0]}+{position[1]}")
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        top = ttk.Frame(self, padding=(8, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Every panel control, the RigController method it "
                            "calls (stmgui/controller.py), the worker-thread "
                            "_impl that does the work, the Igor procedure it "
                            "mirrors, and the stmlab functions it reaches. "
                            "Hover any control on the panels for the same "
                            "text.", wraplength=860, justify="left",
                  font=("Arial", 11)).pack(anchor="w")
        ttk.Button(top, text="Refresh", command=self.refresh).pack(anchor="e")
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self.text = tk.Text(frame, wrap="none", font=_mono(), state="disabled")
        ys = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.text.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        xs.pack(fill="x")
        self.text.tag_configure("control", font=_mono(bold=True),
                                foreground="#8c3a10")
        self.text.tag_configure("key", foreground="#555555")
        self.refresh()

    def refresh(self) -> None:
        rows = command_table()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for row in rows:
            self.text.insert("end", f"{row['control']}\n", "control")
            self.text.insert("end", "  Python: ", "key")
            self.text.insert("end", f"{row['where']}  {row['method']}\n")
            if row["impl"]:
                self.text.insert("end", "          ", "key")
                self.text.insert("end", f"{row['impl']}  (worker thread)\n")
            self.text.insert("end", "  Igor:   ", "key")
            self.text.insert("end", f"{row['igor']}\n")
            if row["calls"]:
                self.text.insert("end", "  Calls:  ", "key")
                self.text.insert("end", "\n          ".join(row["calls"]) + "\n")
            self.text.insert("end", "\n")
        self.text.configure(state="disabled")

    def show(self) -> None:
        self.deiconify()
        self.lift()


class InspectorWindow(tk.Toplevel):
    """Right-click any control: this shows which Python it runs.

    The text is the control's tooltip text -- for a button, the
    RigController method and worker-thread _impl with file:line, the Igor
    procedure, and the stmlab functions called; for an entry or checkbox,
    the Igor global, the attribute it writes, and the limits.
    """

    def __init__(self, master, on_open_map=None, position=(560, 120)):
        super().__init__(master)
        self.title("Inspector: which code runs this control?")
        self.geometry(f"640x300+{position[0]}+{position[1]}")
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        top = ttk.Frame(self, padding=(8, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Right-click (macOS: Control-click or two-finger "
                            "tap) any button, entry or checkbox on a panel; "
                            "its Python appears here.", wraplength=600,
                  justify="left", font=("Arial", 11)).pack(anchor="w")
        if on_open_map is not None:
            ttk.Button(top, text="Open the full Button map",
                       command=on_open_map).pack(anchor="e")
        self.text = tk.Text(self, wrap="word", font=_mono(), state="disabled",
                            height=10)
        self.text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def show_text(self, text: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", text)
        self.text.configure(state="disabled")
        self.deiconify()
        self.lift()


def _mono(bold: bool = False):
    import sys
    family = "Menlo" if sys.platform == "darwin" else "Consolas"
    return (family, 10, "bold") if bold else (family, 10)
