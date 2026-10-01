# Omavolt

A quiet Omarchy battery popup with PowerTOP diagnostics. Plugin ID: `ncfrontiersman.omavolt`.

This is a proof of concept. It uses the installed PowerTOP executable, with a small Python adapter producing JSON. A future Rust collector can replace that adapter without changing the popup's data format.

## What it shows

- Battery charge, discharge rate, capacity, charge cycles, and power profiles.
- Up to ten apps, grouped by executable name rather than individual PID.
- Estimated watts when PowerTOP includes its power-estimation column.
- Wakeups per second when per-app watts are unavailable. Wakeups are activity diagnostics, **not measured battery consumption**.
- A timestamp for the most recent sample. The list is a snapshot, not a live stream.

On the initial Apple Silicon / Asahi test, PowerTOP reported total battery discharge and process wakeups, but no per-app watts. It explicitly requested more measurements on battery before showing power estimates. GPU and disk activity were also missing from that report; absence is not evidence of zero consumption. Omavolt does not invent an energy score or allocate the laptop's total watts in proportion to CPU usage.

## Requirements

Omarchy Quattro's Quickshell UI modules, Python 3, PowerTOP, and polkit with a running authentication agent. The popup follows the installed Omarchy theme and UI components.

```bash
omarchy pkg add powertop
omarchy plugin add https://github.com/wesleygrimes/omavolt
```

Enable `ncfrontiersman.omavolt` through Omarchy's plugin/bar configuration and use it in place of the battery-status popup widget. Keep the built-in low-battery warning service enabled. This plugin supplies only a bar widget; it does not duplicate that service or the shutdown menu.

Click **Measure** to authenticate and collect a ten-second sample. Reopening the popup reads the cached sample without requesting root. Measurement does not run automatically, apply PowerTOP tunables, or trigger calibration.

## Collector

```bash
python3 collector.py capture
python3 collector.py read
python3 collector.py parse /path/to/powertop.csv
```

`capture` runs `/usr/bin/pkexec /usr/bin/powertop --csv=/dev/stdout --time=10 --iteration=1`. Only the installed PowerTOP binary runs as root. The adapter and popup remain unprivileged. Reports are parsed in memory; the cache at `$XDG_CACHE_HOME/omavolt/sample.json` (default `~/.cache/omavolt/sample.json`) contains app names and aggregated values, not raw process command lines. PowerTOP also maintains its own learning state.

The JSON contract contains `schemaVersion`, `source`, `mode` (`power` or `activity`), `sampledAt` (Unix seconds), `dischargeWatts` (number or null), and `apps` (name, watts or null, wakeups per second, process count). Missing estimates remain null. For grouping, all processes with the same executable basename are combined; unrelated programs with identical basenames may also be combined.

PowerTOP's watt values are modeled estimates. It needs battery observations and may benefit from calibration. Calibration changes brightness and exercises devices; Omavolt never starts it automatically. See the [PowerTOP documentation](https://github.com/fenrus75/powertop#calibrating-power-estimates).

## Development

```bash
python3 -m unittest discover -s tests -v
omarchy plugin validate .
/usr/lib/qt6/bin/qmlformat -n Panel.qml >/dev/null
```

The UI is derived from Omarchy's MIT-licensed battery/power popup. PowerTOP remains a separately installed GPL-licensed executable; no PowerTOP source is copied into this repository.
