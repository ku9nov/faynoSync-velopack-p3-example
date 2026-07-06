# faynoSync + Velopack example client

A minimal desktop app (`hello-velopack`) showing how a [Velopack](https://velopack.io)
client consumes updates from a [faynoSync](https://faynosync.com) feed, with optional
TUF verification, telemetry, and failure reporting.

The app self-checks for updates on launch: it reads the Velopack feed from faynoSync,
optionally binds the artifacts it's about to install to faynoSync's TUF root of trust,
then downloads and applies the update in place.

## Layout

| File | Purpose |
|------|---------|
| `app.py` | Entry point. Wires config, runs the Velopack update check/apply flow. |
| `app_version.py` | Single source of truth for the app version (`vpk pack` reads it). |
| `tuf_verify.py` | Verifies feed artifacts against faynoSync TUF metadata before apply. |
| `telemetry.py` | Fire-and-forget beacon to `/telemetry/beacon` (never raises). |
| `report.py` | POSTs update failures to `/reports/ingest` (never raises). |
| `build.sh` | PyInstaller → `vpk pack` into `releases/`. |

## Prerequisites

- Python 3.9+ with a `.venv` in the repo root (deps: `velopack`, `tuf`,
  `securesystemslib`, `cryptography`, `pyinstaller`).
- [Velopack CLI (`vpk`)](https://docs.velopack.io) on `PATH`. `build.sh` prepends
  `$HOME/.dotnet/tools`, so `dotnet tool install -g vpk` works out of the box.
- A running faynoSync instance serving the feed + TUF metadata.

Set up the venv:

```bash
python3 -m venv .venv
.venv/bin/pip install velopack tuf securesystemslib cryptography pyinstaller
```

## Build

```bash
./build.sh
```

What it does:

1. Reads the version from `app_version.py`.
2. `pyinstaller --windowed --name HelloVelopack app.py` → `dist/HelloVelopack.app`.
3. `vpk pack` bundles it into `releases/` with the channel baked in.

The channel is baked into the package at pack time and **must match** the faynoSync
channel — the client requests `releases.{channel}.json` from the feed. Override with:

```bash
CHANNEL=stable ./build.sh
```

`build/`, `dist/`, `releases/`, and `*.spec` are gitignored build output.

## Run

The update flow only works from a Velopack-*installed* copy — running `app.py`
directly logs `Update check skipped (app not installed?)` and exits (this is expected).

To exercise updates end to end: publish `releases/` to faynoSync, install the app via
the Velopack installer, then re-launch it. On launch it checks the feed, applies any
update, and exits — re-run to relaunch the new version.

For a quick smoke test of the app itself:

```bash
.venv/bin/python app.py
```

## Environment variables

All config is env-overridable; defaults target a local dev faynoSync.

### Feed / endpoints

| Var | Default | Notes |
|-----|---------|-------|
| `FAYNOSYNC_BASE` | `http://cb-faynosync-s3-public.web.garage.localhost:3902` | Garage/CDN host. Serves the Velopack feed **and** TUF metadata. |
| `FAYNOSYNC_API_BASE` | `http://localhost:9000` | faynoSync API (gin). Telemetry + reports hit this — a **different host** from the feed. |
| `FAYNOSYNC_OWNER` | `admin` | Feed path component. |
| `FAYNOSYNC_APP` | `HelloVelopack` | Feed path component; also the per-user data dir name. |
| `FAYNOSYNC_CHANNEL` | `nightly` | **Display only.** The real channel comes from the installed package (baked at `vpk pack`). |
| `UPDATE_URL` | — | Overrides the whole computed feed URL. Otherwise built as `{BASE}/velopack/{owner}/{app}/{platform}/{arch}`. Velopack appends `/releases.{channel}.json`. |

### TUF verification

| Var | Default | Notes |
|-----|---------|-------|
| `TUF_ENABLED` | off | `true` binds each artifact's SHA256/size to a TUF-signed target before applying. Any mismatch aborts the update. |
| `FAYNOSYNC_TUF_METADATA_URL` | `{BASE}/tuf_metadata/{owner}/{app}/` | Where TUF role metadata is served. |
| `FAYNOSYNC_TUF_TARGETS_URL` | `{BASE}/` | Targets (`.nupkg, etc...`) resolve from the bucket root. |
| `FAYNOSYNC_TUF_TRUST_DIR` | `<app-data>/tuf` | Local TUF trust store. |

> **TOFU caveat:** on first run with no local `root.json`, `tuf_verify.py` fetches the
> initial root over the network (trust-on-first-use). There is **no pinned/embedded
> root** — acceptable for this internal example, **not** for a production client, where
> the root must ship with the app.

### Telemetry & reports

| Var | Default | Notes |
|-----|---------|-------|
| `TELEMETRY_ENABLED` | off | `true` sends a beacon to `{API_BASE}/telemetry/beacon` on each check. Best-effort, never blocks updates. |
| `REPORTS_ENABLED` | off | `true` POSTs update failures to `{API_BASE}/reports/ingest`. |
| `FAYNOSYNC_REPORT_KEY` | — | Bearer key for `/reports/ingest`. Reports are skipped if unset. |
| `FAYNOSYNC_DEVICE_ID` | auto | Override the device id. Otherwise generated once and persisted in `<app-data>/device_id`. |

Boolean flags are parsed as the literal lowercased string `true`; anything else is off.

### App data directory

Stable per-user dir, kept **outside** the app bundle (Velopack replaces the bundle on
apply, which would wipe anything stored inside it). Holds `device_id` and the TUF trust
store.

- Windows: `%LOCALAPPDATA%\{APP}`
- macOS: `~/Library/Application Support/{APP}`
- Linux: `$XDG_DATA_HOME/{APP}` (or `~/.local/share/{APP}`)
