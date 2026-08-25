#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
command -v xvfb-run >/dev/null || { echo "SKIP: xvfb-run is unavailable"; exit 0; }
xvfb-run -a -s '-screen 0 1200x900x24' env -u WAYLAND_DISPLAY GDK_BACKEND=x11 PYTHONPATH="$repo_dir/src" python3 - <<'PY'
import gi
gi.require_version("Gtk","4.0")
from gi.repository import GLib, Gtk
from fluxglass.app import App, ResizeGrip

def settle():
    for _ in range(20): GLib.MainContext.default().iteration(False)

app=App()
assert app.register(None)
app.activate(); settle()
window=app.get_windows()[0]
assert len(app.get_windows())==1 and window.get_mapped()
assert isinstance(window.window_handle,Gtk.WindowHandle)
assert isinstance(window.resize_grip,ResizeGrip) and not window.get_decorated()
assert isinstance(window.get_child().get_child(),Gtk.ScrolledWindow)
assert window.brand_icon.get_icon_name()=="fluxglass"
assert window.get_sensitive() and window.get_can_target()
window.close(); settle(); assert not app.get_windows()
print("PASS: adaptive window has native move, resize, and lifecycle controls")
PY
