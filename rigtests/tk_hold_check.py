"""Which parts of Tk keep running while the mouse button is held on a slider?

    python rigtests/tk_hold_check.py

Press and hold the knob of the top slider for three seconds WITHOUT moving,
then drag it slowly to the right, then release. Do the same on the second
slider. Then read the three counters:

    after ticks     a timer that should fire every 100 ms, hold or no hold
    motion events   <B1-Motion> events delivered while dragging
    command calls   the slider's -command, called when its value changes

On Linux all three keep counting during the hold and the drag. Whichever
of them stops on your machine is the one the pull-out program must not rely
on while the mouse is down. Nothing here touches any hardware.
"""

import time
import tkinter as tk
from tkinter import ttk

root = tk.Tk()
root.title("Tk hold test: hold, drag, release, then read the counters")
root.geometry("640x330")

counts = {"after": 0, "motion": 0, "command": 0, "press": 0, "release": 0}
state = {"held_since": None, "longest_gap": 0.0, "last_tick": time.monotonic()}

info = tk.Label(root, text="", font=("Courier", 11), justify="left", anchor="w")


def show():
    held = ("held for %.1f s" % (time.monotonic() - state["held_since"])
            if state["held_since"] else "not held")
    info.config(text=(
        f"after ticks    {counts['after']:6d}   (should rise ~10 per second, always)\n"
        f"motion events  {counts['motion']:6d}   (rise while dragging)\n"
        f"command calls  {counts['command']:6d}   (rise while dragging)\n"
        f"presses {counts['press']}  releases {counts['release']}   {held}\n"
        f"longest pause between after ticks: {state['longest_gap'] * 1e3:.0f} ms"))


def tick():
    now = time.monotonic()
    state["longest_gap"] = max(state["longest_gap"], now - state["last_tick"])
    state["last_tick"] = now
    counts["after"] += 1
    show()
    root.after(100, tick)


def on_command(_value):
    counts["command"] += 1
    show()


def on_motion(_e):
    counts["motion"] += 1
    show()


def on_press(_e):
    counts["press"] += 1
    state["held_since"] = time.monotonic()
    show()


def on_release(_e):
    counts["release"] += 1
    state["held_since"] = None
    show()


for row, (label, widget) in enumerate((
        ("classic tk.Scale (the pull-out program's slider)",
         tk.Scale(root, from_=0, to=10, orient="horizontal", length=560,
                  resolution=0.001, showvalue=True, command=on_command)),
        ("themed ttk.Scale",
         ttk.Scale(root, from_=0, to=10, orient="horizontal", length=560,
                   command=on_command)))):
    tk.Label(root, text=label, anchor="w").pack(fill="x", padx=12, pady=(10, 0))
    widget.pack(padx=12)
    widget.bind("<B1-Motion>", on_motion, add="+")
    widget.bind("<ButtonPress-1>", on_press, add="+")
    widget.bind("<ButtonRelease-1>", on_release, add="+")

info.pack(fill="x", padx=12, pady=12)
tick()
root.mainloop()
