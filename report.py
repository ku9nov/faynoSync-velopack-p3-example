import base64
import gzip
import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger("hello-velopack")

DETAILS_ENCODING = "gzip+base64"
DETAILS_CONTENT_TYPE = "application/json"


def _encode_details(obj):
    raw = json.dumps(obj).encode()
    return {
        "encoding": DETAILS_ENCODING,
        "content_type": DETAILS_CONTENT_TYPE,
        "payload": base64.standard_b64encode(gzip.compress(raw)).decode(),
    }


def send_report(base, report_key, device_id, app, version, channel, platform, arch,
                event_type, reason, details=None, timeout=5):
    """POST /reports/ingest with a Bearer report key + X-Device-ID. Details, when
    given, are gzip+base64 JSON per the server contract. Never raises."""
    if not report_key:
        log.warning("report: FAYNOSYNC_REPORT_KEY not set, report skipped")
        return
    if not device_id:
        log.debug("report: no device id, report skipped")
        return

    body = {
        "application": {"name": app, "version": version, "channel": channel},
        "system": {"platform": platform, "arch": arch},
        "event": {"type": event_type, "reason": reason},
    }
    if details is not None:
        body["details"] = _encode_details(details)

    req = urllib.request.Request(
        f"{base}/reports/ingest",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {report_key}",
            "X-Device-ID": device_id,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            log.info("report sent: %s/%s (HTTP %s)", event_type, reason, r.status)
    except urllib.error.HTTPError as e:
        log.warning("report rejected (HTTP %s): %s", e.code, e.read().decode(errors="replace")[:200])
    except Exception as e:
        log.warning("report failed (ignored): %s", e)
