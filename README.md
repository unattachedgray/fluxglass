# Fluxglass

Read-only Linux hardware graphs for Ubuntu-family desktops. Fluxglass is
one adaptive, frameless system instrument inspired by classic Linux desktop
monitors. Its GTK4 surface works under Wayland and X11 and uses standard kernel
sensors, AMD/Intel DRM counters, and richer optional NVIDIA counters when
`nvidia-smi` is present.

```bash
./packaging/build-deb
sudo apt install ./dist/fluxglass_*.deb
```

Versioned release tags publish a ready-to-install `.deb` and `SHA256SUMS` on the
[GitHub Releases page](https://github.com/unattachedgray/fluxglass/releases).

For a no-sudo, per-user installation instead:

```bash
./packaging/install-user
```

The source checkout is not used as the installed runtime. The per-user
installer deploys an independent runtime to
`~/.local/lib/fluxglass`, a launcher to `~/.local/bin/fluxglass`, and desktop
assets under `~/.local/share`. The Debian package deploys the runtime to
`/usr/lib/fluxglass` with `/usr/bin/fluxglass`. Neither installed form launches
from the development checkout, and `/usr/local` is deliberately left for
administrator-managed, unpackaged software.

After installation, launch **Fluxglass** from the application menu. Remove it
cleanly with `sudo apt remove fluxglass`.

The interface starts in Korean and can switch live between Korean and English.
The header menu always names the current language in English (`Korean` or
`English`) so it remains discoverable before translation. The selection
persists. Fluxglass bundles the OFL
licensed Pretendard Variable and Bebas Neue fonts, installs them into the
per-user font directory, and keeps Noto Sans KR as its fallback.

The application icon is installed into the freedesktop `hicolor` theme, so it
appears consistently in application menus, docks, switchers, and launchers.

The graph grid reflows automatically from one to two to four columns as the
window changes width. Drag any graph onto another graph to reorder it; the
chosen order is saved under the standard XDG configuration directory. Short
windows scroll vertically, while live metric typography scales down only when
needed to preserve a complete single-line reading.

Fluxglass remembers language, graph order, view options, window size, and
maximized state. Wayland compositors intentionally control application
placement, so portable GTK4 applications cannot reliably restore an exact
screen position; Fluxglass leaves placement to the desktop rather than adding
an X11-only positioning path.

The Resource Compass above the history grid summarizes the present moment. Its
inner ring combines total compute intensity with the CPU/GPU ratio; its split
outer ring shows RAM and VRAM pressure. Exact percentages and a plain-language
state remain visible, so the display never relies on color alone.

Hover any history graph to align all graphs to the same second and reveal the
historical value plus leading GPU process. Click a graph (or press Enter while
focused) to expand it; Escape restores the grid. The View menu controls the PSI
contention halo, state ribbon, and bounded event memory. Recording is opt-in and
writes one-second CSV samples under `~/Documents/Fluxglass recordings/`.
State transitions enter the event ledger only after three stable samples, which
keeps threshold jitter from overwhelming meaningful changes.

Each history card reserves natural plot padding around its title, current value,
focused detail, hover attribution, and footer legend. Traces, fills, and
synchronized cursors remain inside the plot region, so text stays readable
without opaque or translucent label bars.

Drag the header to move the instrument and drag the marked bottom-right corner
to resize it. **Maximize** expands it into a full dashboard, while **Quit**
exits. The graph grid adapts to the available space without a separate mode.

Fluxglass never writes to sysfs, signals processes, changes clocks, or manages
memory. It is a read-only monitor.

Run from a checkout:

```bash
PYTHONPATH=src /usr/bin/python3 -m fluxglass
```

The frameless window works on GNOME, KDE, COSMIC, XFCE, Cinnamon, and other
GTK-capable desktops. Wayland has no universal protocol for pinning a window
behind desktop icons, so Fluxglass remains an ordinary movable window.

## Development

Run `python3 -m unittest discover -s tests` for unit coverage and
`./tests/test_runtime_lifecycle.sh` for the GTK lifecycle check.

Fluxglass is available under the MIT License. Pretendard Variable and Bebas
Neue retain their bundled SIL Open Font License notices under `assets/fonts/`.
