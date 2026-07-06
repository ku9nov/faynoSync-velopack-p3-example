import logging
import os
import platform as pyplatform
import sys
import uuid

import velopack

import app_version
import report
import telemetry
import tuf_verify

VERSION = app_version.version

log = logging.getLogger("hello-velopack")

# faynoSync velopack endpoint pieces (env-overridable). The client points at
# {BASE}/velopack/{owner}/{app}/{platform}/{arch}; Velopack itself appends
# /releases.{channel}.json (channel is baked at `vpk pack --channel`).
BASE = os.environ.get("FAYNOSYNC_BASE", "http://cb-faynosync-s3-public.web.garage.localhost:3902")
OWNER = os.environ.get("FAYNOSYNC_OWNER", "admin")
APP = os.environ.get("FAYNOSYNC_APP", "HelloVelopack")
CHANNEL = os.environ.get("FAYNOSYNC_CHANNEL", "nightly")  # display only; real channel comes from the install

# faynoSync serves TUF metadata straight from the public garage bucket at
# tuf_metadata/{owner}/{app}/; targets (the .nupkg) resolve from the bucket root.
# BASE (garage/CDN, :3902) serves the feed + TUF metadata. Telemetry/report hit the
# faynoSync API itself (gin, :9000 by default) — a different host, hence a separate base.
API_BASE = os.environ.get("FAYNOSYNC_API_BASE", "http://localhost:9000")
# By default the feed is fetched from the static CDN (BASE). Set ASK_API=true to
# hit the faynoSync API (API_BASE) instead, which serves the same feed shape but
# computed dynamically (respects intermediate for the given
# localVersion+id that Velopack appends to the request).
ASK_API = os.environ.get("ASK_API", "").lower() == "true"
TUF_ENABLED = os.environ.get("TUF_ENABLED", "").lower() == "true"
TELEMETRY_ENABLED = os.environ.get("TELEMETRY_ENABLED", "").lower() == "true"
REPORTS_ENABLED = os.environ.get("REPORTS_ENABLED", "").lower() == "true"
REPORT_KEY = os.environ.get("FAYNOSYNC_REPORT_KEY", "")
METADATA_URL = os.environ.get("FAYNOSYNC_TUF_METADATA_URL", f"{BASE}/tuf_metadata/{OWNER}/{APP}/")
TARGETS_URL = os.environ.get("FAYNOSYNC_TUF_TARGETS_URL", f"{BASE}/")


def _app_data_dir():
    # Per-user data dir, stable across updates. Must NOT live inside the app bundle:
    # Velopack replaces the bundle on apply, which would wipe anything stored there.
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP)


def _load_device_id():
    override = os.environ.get("FAYNOSYNC_DEVICE_ID")
    if override:
        return override
    path = os.path.join(_app_data_dir(), "device_id")
    try:
        with open(path) as f:
            existing = f.read().strip()
        if existing:
            return existing
    except FileNotFoundError:
        pass
    generated = uuid.uuid4().hex
    os.makedirs(_app_data_dir(), exist_ok=True)
    with open(path, "w") as f:
        f.write(generated)
    return generated


TRUST_DIR = os.environ.get("FAYNOSYNC_TUF_TRUST_DIR") or os.path.join(_app_data_dir(), "tuf")
DEVICE_ID = _load_device_id()

_PLATFORM_MAP = {"darwin": "darwin", "linux": "linux", "windows": "win32"}
_ARCH_MAP = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "amd64": "amd64"}


def detect_platform():
    return _PLATFORM_MAP.get(pyplatform.system().lower(), pyplatform.system().lower())


def detect_arch():
    m = pyplatform.machine().lower()
    return _ARCH_MAP.get(m, m)


def build_update_url():
    override = os.environ.get("UPDATE_URL")
    if override:
        return override
    base = API_BASE if ASK_API else BASE
    return f"{base}/velopack/{OWNER}/{APP}/{detect_platform()}/{detect_arch()}"


def _describe_update(info):
    target = info.TargetFullRelease.Version
    deltas = info.DeltasToTarget or []
    if deltas:
        total = sum(d.Size for d in deltas)
        return target, f"DELTA ({len(deltas)} package(s), {total} bytes)"
    return target, f"FULL ({info.TargetFullRelease.Size} bytes)"


def check_and_update():
    url = build_update_url()
    log.info("Checking updates: %s/%s  platform=%s arch=%s", OWNER, APP, detect_platform(), detect_arch())
    log.info("Feed URL: %s/releases.%s.json", url, CHANNEL)

    try:
        opts = velopack.UpdateOptions(AllowVersionDowngrade=True, MaximumDeltasBeforeFallback=10)
        um = velopack.UpdateManager(velopack.HttpSource(url), opts)
        info = um.check_for_updates()
    except Exception as e:
        log.warning("Update check skipped (app not installed?): %s", e)
        return

    if TELEMETRY_ENABLED:
        telemetry.send_beacon(API_BASE, OWNER, APP, VERSION, CHANNEL,
                              detect_platform(), detect_arch(), info is None, DEVICE_ID)

    # Demo only: this example app never actually crashes, so emit a synthetic
    # crash report to exercise /reports/ingest end-to-end when REPORTS_ENABLED=true.
    _report_event("crash", "synthetic_demo_crash", {
        "note": "synthetic crash emitted by the example app to demonstrate reporting",
        "signal": "SIGSEGV",
        "thread": "main",
        "fault_address": "0x0",
    })

    if info is None:
        log.info("Already on the latest version (%s).", VERSION)
        return

    target, kind = _describe_update(info)
    direction = "DOWNGRADE (revoked?)" if info.IsDowngrade else "upgrade"
    log.info("Update available: %s -> %s  (%s) via %s", VERSION, target, direction, kind)

    if TUF_ENABLED:
        assets = [info.TargetFullRelease] + (info.DeltasToTarget or [])
        try:
            tuf_verify.verify_assets(assets, METADATA_URL, TARGETS_URL, OWNER, APP,
                                     detect_platform(), detect_arch(), TRUST_DIR)
        except tuf_verify.VerificationError as e:
            log.error("TUF verification FAILED, not applying update: %s", e)
            _report_failure("tuf_verification_failed", target, str(e))
            return
    else:
        log.info("TUF verification disabled (set TUF_ENABLED=true to enable)")

    try:
        log.info("Downloading...")
        um.download_updates(info)
        log.info("Downloaded. Applying and exiting; re-run to launch %s.", target)
        um.apply_updates_and_exit(info)
    except Exception as e:
        log.error("Update download/apply failed: %s", e)
        _report_failure("apply_failed", target, str(e))
        return


def _report_event(event_type, reason, details=None):
    if not REPORTS_ENABLED:
        return
    report.send_report(API_BASE, REPORT_KEY, DEVICE_ID, APP, VERSION, CHANNEL,
                       detect_platform(), detect_arch(), event_type, reason, details=details)


def _report_failure(reason, target, error):
    _report_event("update_failure", reason,
                  {"from_version": VERSION, "target_version": target, "error": error})


def main():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    velopack.App().run()
    log.info("Hello from hello-velopack v%s  (%s/%s)", VERSION, detect_platform(), detect_arch())
    check_and_update()


if __name__ == "__main__":
    main()
