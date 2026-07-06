import logging
import urllib.parse
import urllib.request

log = logging.getLogger("hello-velopack")


def send_beacon(base, owner, app, version, channel, platform, arch, is_latest, device_id, timeout=5):
    """Fire-and-forget GET /telemetry/beacon. Never raises — telemetry must not
    break the update flow. Server replies 204 and requires X-Device-ID."""
    if not device_id:
        log.debug("telemetry: no device id, beacon skipped")
        return
    q = urllib.parse.urlencode({
        "owner": owner,
        "app_name": app,
        "version": version,
        "channel": channel,
        "platform": platform,
        "arch": arch,
        "is_latest": "true" if is_latest else "false",
    })
    url = f"{base}/telemetry/beacon?{q}"
    req = urllib.request.Request(url, headers={"X-Device-ID": device_id})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            log.debug("telemetry beacon sent (HTTP %s, is_latest=%s)", r.status, is_latest)
    except Exception as e:
        log.debug("telemetry beacon failed (ignored): %s", e)
