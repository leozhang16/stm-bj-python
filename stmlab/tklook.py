"""The Windows window on any platform: Tk's "clam" theme in Windows' colours
and sizes, light whatever the Mac's dark mode says. Shared by pullout.py and
rigcheck.py; see windows_look() for the whole story."""
from __future__ import annotations

import sys


WIN_BG = "#f0f0f0"      # Windows' window grey, the colour the layout was made on


def _light_window(win) -> None:
    """A light window whatever the Mac's dark mode says. Tk 8.6.10 and later
    on the Mac have the command; an older Tk, or any other platform, has
    nothing to do."""
    if sys.platform == "darwin":
        try:
            win.tk.call("::tk::unsupported::MacWindowStyle", "appearance", win, "aqua")
        except Exception:                                 # noqa: BLE001
            pass


def windows_look(root, style, zoom: float = 1.0) -> None:
    """The Windows window on another platform.

    Tk's own flat "clam" theme, recoloured to Windows' greys, with Windows'
    tick boxes and radio dots (borrowed from Tk's "alt" theme), Windows'
    font sizes (9 pt, which on a Mac Tk draws a third smaller unless the
    scaling is set to 96 dpi, so it is), the classic widgets (labels, the
    readout, the slider, the Status box) on the same light palette, and
    the system's dark mode kept out. ``zoom`` makes everything bigger or
    smaller (1.2 = a fifth bigger) for a small or a very sharp screen.
    """
    from tkinter import font as tkfont
    style.theme_use("clam")
    if sys.platform == "darwin":
        root.tk.call("tk", "scaling", 96.0 / 72.0 * zoom)
    elif zoom != 1.0:
        root.tk.call("tk", "scaling", float(root.tk.call("tk", "scaling")) * zoom)
    # The classic widgets take the palette (which also colours the root and
    # every widget made from now on); the themed ones take the style.
    root.tk_setPalette(background=WIN_BG, foreground="#000000",
                       activeBackground="#e5e5e5", activeForeground="#000000",
                       highlightBackground=WIN_BG, highlightColor="#0078d7",
                       selectBackground="#0078d7", selectForeground="#ffffff",
                       insertBackground="#000000", troughColor="#d6d6d6",
                       disabledForeground="#6d6d6d", selectColor="#ffffff")
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                 "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont",
                 "TkTooltipFont"):
        tkfont.nametofont(name).configure(family="Arial", size=9)
    tkfont.nametofont("TkFixedFont").configure(family="Courier", size=9)
    style.configure(".", background=WIN_BG, foreground="#000000",
                    fieldbackground="#ffffff", troughcolor="#d6d6d6",
                    selectbackground="#0078d7", selectforeground="#ffffff",
                    font="TkDefaultFont")
    # Windows 10's buttons: a light face, a thin outline, blue when the
    # mouse is over them.
    style.configure("TButton", background="#e1e1e1", lightcolor="#e1e1e1",
                    darkcolor="#e1e1e1", bordercolor="#adadad")
    style.map("TButton",
              background=[("disabled", "#cccccc"), ("pressed", "#cce4f7"),
                          ("active", "#e5f1fb")],
              lightcolor=[("pressed", "#cce4f7"), ("active", "#e5f1fb")],
              darkcolor=[("pressed", "#cce4f7"), ("active", "#e5f1fb")],
              bordercolor=[("disabled", "#bfbfbf"), ("pressed", "#005499"),
                           ("active", "#0078d7")])
    style.configure("TEntry", bordercolor="#7a7a7a")
    style.configure("TCombobox", bordercolor="#7a7a7a", arrowcolor="#606060")
    style.map("TCombobox", fieldbackground=[("readonly", "#ffffff")],
              selectbackground=[("readonly", "#ffffff")],
              selectforeground=[("readonly", "#000000")])
    style.configure("TNotebook.Tab", background="#e1e1e1", lightcolor="#e1e1e1",
                    darkcolor="#e1e1e1", bordercolor="#adadad")
    style.map("TNotebook.Tab", background=[("selected", WIN_BG)],
              lightcolor=[("selected", WIN_BG)])
    style.configure("TScrollbar", background="#cdcdcd", troughcolor=WIN_BG,
                    bordercolor=WIN_BG, lightcolor="#cdcdcd", darkcolor="#cdcdcd",
                    arrowcolor="#606060")
    # Windows' tick box and radio dot in place of clam's black square and
    # filled dot: the indicator elements of Tk's "alt" theme, in clam's layout.
    try:
        style.element_create("Tick.Checkbutton.indicator", "from", "alt",
                             "Checkbutton.indicator")
        style.element_create("Tick.Radiobutton.indicator", "from", "alt",
                             "Radiobutton.indicator")
    except Exception:                                     # noqa: BLE001
        pass                                              # no alt theme: clam's own
    else:
        for kind in ("Checkbutton", "Radiobutton"):
            style.layout(f"T{kind}", [
                (f"{kind}.padding", {"sticky": "nswe", "children": [
                    (f"Tick.{kind}.indicator", {"side": "left", "sticky": ""}),
                    (f"{kind}.focus", {"side": "left", "sticky": "w", "children": [
                        (f"{kind}.label", {"sticky": "nswe"})]})]})])
            style.configure(f"T{kind}", indicatorcolor="#ffffff",
                            indicatormargin=(1, 1, 4, 1))
    _light_window(root)
