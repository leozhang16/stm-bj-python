"""Igor's control types, as small Tk composites.

Igor had five controls on these panels: SetVariable (label + numeric entry
with limits and an optional increment), ValDisplay (read-only number),
CheckBox, Button (coloured, sometimes two-line) and GroupBox. These are the
same five. Every SetVariable and CheckBox is bound to a :class:`Param`, so
editing it writes straight into the ``RigConfig`` / ``GuiOptions``, exactly
as Igor's ``value= G_Something`` binding did.

Every control also carries a tooltip. Hover over a button and it says what
the click does and which Igor procedure it mirrors (the text is the
controller method's docstring); hover over an entry or checkbox and it
names the Igor global it was bound to and the config attribute it writes
now. Igor only had a ``help=`` string on Start Writing.
"""

from __future__ import annotations

import re
import sys
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .state import GuiState, Param

FONT = ("Arial", 12)
FONT_BOLD = ("Arial", 12, "bold")
FONT_BIG = ("Arial", 14, "bold")
FONT_TITLE = ("Arial", 16, "bold")

# Igor's 16-bit RGB triples, converted. Panel backgrounds and button text.
PANEL_BG = "#bfcfff"      # BreakJunctionMeasurement cbRGB=(48896,52992,65280)
TAB_BG = "#bfffdf"        # TabControl labelBack
OFFSET_BG = "#dddddd"     # Voltage_Offset cbRGB=(56576,56576,56576)
ECHEM_BG = "#bfffff"      # EChem cbRGB=(48896,65280,65280)
BLUE = "#000099"          # Start Writing fColor=(0,0,39168)
RED = "#cc0000"           # Kill Tasks fColor=(52224,0,0)
GREEN = "#00cc66"         # Start Measurement fColor=(0,52224,26368)
SKY = "#00aaff"           # Start Approach fColor=(0,43520,65280)
ORANGE = "#cc8800"        # Zero Correct fColor=(52224,34816,0)
LIME = "#00ff00"          # Find Suppress fColor=(0,65280,0)
MAGENTA = "#ff00cc"       # CV LowRes fColor=(65280,0,52224)

MAC = sys.platform == "darwin"


# --------------------------------------------------------------------------
# Tooltips
# --------------------------------------------------------------------------

def tip_text(doc) -> str:
    """Tooltip text from a docstring (paragraphs kept) or, given a
    controller method, the full description: what it does, the Igor
    procedure, the Python file:line, and the stmlab functions it calls."""
    if not doc:
        return ""
    if callable(doc):
        from .controller import describe_command
        return describe_command(doc)
    paragraphs = re.split(r"\n\s*\n", doc.strip())
    return "\n\n".join(" ".join(p.split()) for p in paragraphs)


class Tooltip:
    """A hover label. Shows after half a second, hides on leave or click."""

    DELAY_MS = 350

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._after = None
        self._win = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _show(self) -> None:
        if self._win is not None or not self.text:
            return
        try:
            x = self.widget.winfo_pointerx() + 14
            y = self.widget.winfo_pointery() + 12
            win = tk.Toplevel(self.widget)
            win.wm_overrideredirect(True)
            if MAC:
                # Without this, macOS never maps a borderless Toplevel
                # (the same call idlelib's tooltip makes).
                try:
                    win.tk.call("::tk::unsupported::MacWindowStyle", "style",
                                win._w, "help", "noActivates")
                except tk.TclError:
                    pass
            tk.Label(win, text=self.text, justify="left",
                     background="#ffffe0", foreground="#111111",
                     relief="solid", borderwidth=1, wraplength=560,
                     font=("Arial", 10), padx=6, pady=4).pack()
            win.wm_geometry(f"+{x}+{y}")
            try:
                win.wm_attributes("-topmost", True)
            except tk.TclError:
                pass
            win.update_idletasks()
            win.lift()
            self._win = win
        except tk.TclError:
            self._win = None

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._win is not None:
            try:
                self._win.destroy()
            except tk.TclError:
                pass
            self._win = None


# Right-click (or Control-click) on any control opens the Inspector with the
# same text as its tooltip. The App installs the hook; without one the
# binding does nothing.
INSPECT_HOOK = None


def bind_inspect(widget, text_or_method) -> None:
    """Right-click / Control-click -> INSPECT_HOOK(text)."""
    def show(_event=None):
        if INSPECT_HOOK is not None:
            INSPECT_HOOK(tip_text(text_or_method))
        return "break"
    for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
        widget.bind(seq, show, add="+")


def param_tip(param: Param, extra: str | None = None) -> str:
    lo, hi, inc = param.limits
    parts = [f"Igor global: {param.igor}", f"bound to: {param.path}"]
    if param.scale != 1.0:
        parts.append(f"shown x{param.scale:g}")
    if not (lo == float("-inf") and hi == float("inf")):
        parts.append(f"limits: {lo:g} .. {hi:g}"
                     + (f", step {inc:g}" if inc else ""))
    text = "\n".join(parts)
    if extra:
        text = tip_text(extra) + "\n\n" + text
    return text


# --------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------

class SetVariable(ttk.Frame):
    """Igor SetVariable: ``title`` label plus a numeric entry.

    Limits with a non-zero increment become a spinbox (Igor's arrow
    buttons). The value is committed on Return, on focus-out, and on the
    spinbox arrows; ``on_commit(value)`` then fires with the stored value in
    display units.
    """

    def __init__(self, parent, param: Param, state: GuiState,
                 on_commit: Callable[[float], None] | None = None,
                 width: int = 9, title: str | None = None,
                 font=FONT, tip: str | None = None, **kw):
        super().__init__(parent, **kw)
        self.param = param
        self.state = state
        self.on_commit = on_commit
        self.var = tk.StringVar()
        self.label = ttk.Label(self, text=title if title is not None
                               else param.title, font=font)
        self.label.pack(side="left", padx=(0, 4))
        lo, hi, inc = param.limits
        if inc:
            self.entry = ttk.Spinbox(
                self, textvariable=self.var, width=width, font=font,
                from_=lo if lo != float("-inf") else -1e12,
                to=hi if hi != float("inf") else 1e12, increment=inc,
                command=self._commit)
        else:
            self.entry = ttk.Entry(self, textvariable=self.var, width=width,
                                   font=font)
        self.entry.pack(side="left")
        self.entry.bind("<Return>", self._commit)
        self.entry.bind("<KP_Enter>", self._commit)
        self.entry.bind("<FocusOut>", self._commit)
        text = param_tip(param, tip)
        self.tooltip = Tooltip(self.entry, text)
        Tooltip(self.label, text)
        bind_inspect(self.entry, text)
        bind_inspect(self.label, text)
        self.refresh()

    def refresh(self) -> None:
        value = self.param.get(self.state)
        try:
            self.var.set(self.param.fmt % value)
        except (TypeError, ValueError):
            self.var.set(str(value))

    def _commit(self, _event=None) -> None:
        text = self.var.get().strip()
        try:
            value = float(text)
        except ValueError:
            self.refresh()
            return
        if self.param.kind is int:
            value = int(round(value))
        before = self.param.get(self.state)
        stored = self.param.set(self.state, value)
        self.refresh()
        if self.on_commit is not None and (stored != before or _event is None):
            self.on_commit(stored)

    def set_enabled(self, on: bool) -> None:
        self.entry.state(["!disabled"] if on else ["disabled"])


class ValDisplay(ttk.Frame):
    """Igor ValDisplay: a read-only number with a title."""

    def __init__(self, parent, title: str, fmt: str = "%g", width: int = 10,
                 font=FONT, bold: bool = False, tip: str | None = None, **kw):
        super().__init__(parent, **kw)
        self.fmt = fmt
        self.var = tk.StringVar(value="")
        if title:
            ttk.Label(self, text=title, font=FONT_BOLD if bold else font)\
                .pack(side="left", padx=(0, 4))
        self.entry = ttk.Entry(self, textvariable=self.var, width=width,
                               font=FONT_BOLD if bold else font,
                               state="readonly", justify="right")
        self.entry.pack(side="left")
        if tip:
            Tooltip(self.entry, tip_text(tip))

    def set(self, value) -> None:
        try:
            self.var.set(self.fmt % value)
        except (TypeError, ValueError):
            self.var.set(str(value))


class CheckBox(ttk.Checkbutton):
    """Igor CheckBox bound to a bool Param; ``on_toggle(bool)`` fires after
    the value is stored."""

    def __init__(self, parent, param: Param, state: GuiState,
                 on_toggle: Callable[[bool], None] | None = None,
                 title: str | None = None, tip: str | None = None, **kw):
        self.var = tk.BooleanVar(value=param.get(state))
        super().__init__(parent, text=title if title is not None
                         else param.title, variable=self.var,
                         command=self._toggle, **kw)
        self.param = param
        self.state_ = state
        self.on_toggle = on_toggle
        text = param_tip(param, tip)
        self.tooltip = Tooltip(self, text)
        bind_inspect(self, text)

    def refresh(self) -> None:
        self.var.set(self.param.get(self.state_))

    def _toggle(self) -> None:
        value = bool(self.var.get())
        self.param.set(self.state_, value)
        if self.on_toggle is not None:
            self.on_toggle(value)

    def set_enabled(self, on: bool) -> None:
        self.state(["!disabled"] if on else ["disabled"])


def button(parent, text: str, command: Callable[[], None],
           fg: str | None = None, bg: str | None = None,
           font=FONT_BOLD, width: int | None = None,
           tip: str | None = None, **kw) -> tk.Button:
    """Igor Button. Colours are Igor's fColor; macOS Aqua ignores ``bg`` on
    native buttons, so the text colour carries the meaning there. ``tip`` is
    the hover text -- pass the controller method's docstring."""
    opts = dict(text=text, command=command, font=font, justify="center")
    if fg:
        opts["fg"] = fg
        opts["activeforeground"] = fg
    if bg and not MAC:
        opts["bg"] = bg
        opts["activebackground"] = bg
    if MAC and bg:
        opts["highlightbackground"] = bg
    if width:
        opts["width"] = width
    opts.update(kw)
    b = tk.Button(parent, **opts)
    if tip:
        b.tooltip = Tooltip(b, tip_text(tip))
        bind_inspect(b, tip)
    return b


def groupbox(parent, title: str, **kw) -> ttk.LabelFrame:
    """Igor GroupBox."""
    return ttk.LabelFrame(parent, text=title, padding=6, **kw)


def set_enabled(widget, on: bool) -> None:
    """Enable/disable any of the composites above or a plain widget."""
    if hasattr(widget, "set_enabled"):
        widget.set_enabled(on)
    elif isinstance(widget, (tk.Button, tk.Scale)):
        widget.configure(state="normal" if on else "disabled")
    else:
        try:
            widget.state(["!disabled"] if on else ["disabled"])
        except (AttributeError, tk.TclError):
            pass
