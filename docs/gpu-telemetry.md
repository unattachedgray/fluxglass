# GPU telemetry: what Fluxglass reads, and why

Fluxglass answers one question about the GPU — *how hard is it working right now* —
and a second about memory — *how much video memory is in use*. Neither has a single
portable answer on Linux. This document records which interfaces Fluxglass uses, in
what order, which ones were measured and rejected, and how to reproduce the
measurements rather than trusting this page.

Every claim below was measured on 2026-08-25 against Intel HD Graphics 4000
(Ivy Bridge gen7, `8086:0166`, `i915`) on Linux 7.0.0-30, with a discrete
NVS 5400M (`10de:0def`, `nouveau`) also present. Numbers from other hardware will
differ; the *method* is the portable part.

## Compute load, in priority order

Fluxglass takes the best source the kernel allows and records which one it used, in
`util_source`. The UI never presents a coarse reading as though it were an exact one.

| Order | Source | `util_source` | Shown as | Requires |
| --- | --- | --- | --- | --- |
| 1 | AMD `gpu_busy_percent` | `counter` | `42%` | nothing |
| 2 | i915 PMU engine-busy | `pmu` | `42%` | `CAP_PERFMON`, or `perf_event_paranoid` <= 0 |
| 3 | GPU frequency P-state | `frequency` | `≈ 42%` | nothing |
| 4 | none available | `None` | `Not measurable` | — |

### 2. The i915 PMU — exact, and it discriminates

`/sys/bus/event_source/devices/i915/` exposes per-engine busy counters
(`rcs0-busy` render, `bcs0-busy` blitter, `vcs0-busy` video, `vecs0-busy` video
enhance) in nanoseconds, read through `perf_event_open(2)`. Busy percent is the
delta over wall-clock elapsed. Fluxglass reports the busiest engine, so a
video-only workload still registers.

This is the only source measured that separates partial load from full load:

| Workload | `rcs0-busy` | `gt_act_freq_mhz` | measured |
| --- | --- | --- | --- |
| idle desktop | 16.9% | 350 MHz (= RPn) | — |
| `glxgears`, vsync-capped | 42.4% | 650 MHz | 67.5 FPS |
| `glxgears`, uncapped | 99.9% | 1250 MHz (= RP0) | 1174.8 FPS |

Cross-checked independently against `intel_gpu_top` running as root on the same
workload, which reported the render engine ramping 80.8% -> 100.0%.

It is gated. `perf_event_open` on a system-wide PMU needs `CAP_PERFMON` or
`perf_event_paranoid` <= 0. The measured machine ships `paranoid=4`, where the call
returns `EACCES`; at `0`, an ordinary uid-1000 process read the counters fine.
Opening and reading a PMU counter is read-only: Fluxglass still never writes to the
GPU, changes clocks, or signals a process.

### 3. GPU frequency — free, coarse, honest about it

`gt_act_freq_mhz` scaled between `gt_RPn_freq_mhz` and `gt_RP0_freq_mhz` is
world-readable and needs no permission at all. Across the same three workloads it
tracked load monotonically: 350 / 650 / 1250 MHz, i.e. 0% / 33% / 100%.

Two properties make it an approximation rather than a measurement, and both are why
the UI prefixes it with `≈`:

- **It saturates.** Once the GPU pegs at RP0 there is no headroom left in the
  signal, so a 60% load and a 100% load read alike.
- **It steps and bounces.** The GPU moves between discrete P-states, so consecutive
  one-second samples at a steady light load can read 0% and 33% alternately.

It is still worth having: it is the only compute signal available on an unmodified
system with integrated graphics, and it is right about the shape of the load.

## Video memory

Integrated graphics have **no dedicated VRAM**. They draw from system RAM, so the
truthful reading is the shared system pool, explicitly labelled as shared
(`시스템 RAM 공유` / `shared with system RAM`) rather than an empty gauge.

`is_integrated()` decides this from PCI topology: integrated GPUs sit on the PCI
root bus (`0000:00:…`), discrete cards sit behind a bridge (`0000:01:…`). This is
cheaper and more reliable than matching driver or vendor names.

One trap worth naming, because it is invisible until it fires: `resource_metrics`
checks `vram >= 90` **before** `ram >= 85`. With a shared pool those are the same
number, so a machine at 92% RAM would have reported `VRAM PRESSURE` — one pool
counted twice, under the wrong name. The VRAM check is skipped when
`shared_memory` is set.

## Measured dead ends

Recorded so they are not re-attempted. Each was rejected on evidence, not on
expectation.

**RC6 residency is frozen.** `power/rc6_residency_ms` and the `gt/gt0/` copy both
returned a delta of **0 ms over 3000 ms** while idle, despite `rc6_enable` reading
`1`. A busy formula built on it (`100 × (1 − Δrc6/Δwall)`) therefore reports a
constant 100% busy in every phase — idle, light and heavy alike. `intel_gpu_top`
independently reports `RC6 0%` on this hardware, confirming the GPU never enters
the state rather than the counter being misread.

**DRM fdinfo has no engine counters here.** The modern per-process interface
(`drm-engine-render`, used by `nvtop` and friends) is absent: a grep across every
`/proc/*/fdinfo/*` on a running system found **zero** `drm-engine-*` keys. i915 on
gen7 does not implement them. fdinfo *does* expose per-client GPU **memory**
(`drm-total-system0`, `drm-resident-system0`, `drm-active-system0`), which is a real
per-process number and a candidate for future per-process attribution.

**Runtime PM accounting is unavailable.** `power/runtime_active_time` is permanently
`0` because `power/runtime_status` reads `unsupported`.

**Untested, not disproven:** the media engine (`vcs0`). The VAAPI probe failed to
initialise `iHD_drv_video.so`; Ivy Bridge requires the **i965** driver, so the video
engine was never exercised. Absence of a reading here is absence of a test.

## Enabling the exact source

The PMU is preferred automatically whenever `perf_event_open` succeeds — no
configuration and no restart logic beyond starting the program.

```bash
sudo sysctl kernel.perf_event_paranoid=0    # system-wide; every local user gains system-wide profiling
```

The scoped alternative, `setcap cap_perfmon+ep`, is the approach the kernel's own
security guide recommends — but **it does not work for Fluxglass as shipped**. File
capabilities are not inherited by an interpreter, so setting them on the
`/usr/bin/fluxglass` shell wrapper has no effect, and setting them on `python3`
itself would grant `CAP_PERFMON` to every Python program on the machine. It is a
route for packagers shipping a small compiled helper, not a step for users.

Weigh it accordingly: relaxing `perf_event_paranoid` machine-wide to improve one
desktop gauge is a real security trade, and the frequency proxy is already
directionally correct. Fluxglass works unmodified either way.

## Reproducing the measurements

Do not trust the tables above; re-run them. The A/B below is the one that produced
the numbers — idle, then a real GL workload, then idle again, with the load's own
FPS output as the liveness check that the treatment was actually applied.

```bash
# what this GPU exposes at all
ls /sys/class/drm/card*/device/ | grep -E 'mem_info|gpu_busy'   # AMD counters
ls /sys/bus/event_source/devices/i915/events/                   # PMU events
cat /proc/sys/kernel/perf_event_paranoid                        # the gate

# is RC6 residency alive? (a frozen counter reads as 100% busy forever)
a=$(cat /sys/class/drm/card1/power/rc6_residency_ms); sleep 3
b=$(cat /sys/class/drm/card1/power/rc6_residency_ms); echo "delta=$((b-a)) ms over 3000 ms"

# does any process expose per-engine busy?
grep -lsa '^drm-engine' /proc/*/fdinfo/* | head

# frequency proxy, idle vs load
cat /sys/class/drm/card1/gt_act_freq_mhz
vblank_mode=0 glxgears >/tmp/g.log 2>&1 &
sleep 5; cat /sys/class/drm/card1/gt_act_freq_mhz; grep -o '[0-9.]* FPS' /tmp/g.log | tail -1
kill %1
```

Two rules carried over from how these numbers were produced. A null reading is
inadmissible without a liveness check in the same run — that is exactly what caught
the frozen RC6 counter, which otherwise reads as a confident 100%. And verify the
treatment landed, not that it was requested: the FPS line proves the GPU was
actually loaded, and the VAAPI probe above is in the "untested" list precisely
because its driver never initialised.
