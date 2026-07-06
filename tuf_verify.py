import logging
import os
import urllib.request

from tuf.ngclient import Updater

log = logging.getLogger("hello-velopack")


class VerificationError(Exception):
    pass


def _load_root(trust_dir, metadata_url):
    root_path = os.path.join(trust_dir, "root.json")
    if os.path.exists(root_path):
        with open(root_path, "rb") as f:
            return f.read()
    os.makedirs(trust_dir, exist_ok=True)
    # Trust-on-first-use: fetch the initial root over the network. No pinned/embedded
    # root — acceptable for this internal example, NOT for a production client.
    for name in ("1.root.json", "root.json"):
        try:
            with urllib.request.urlopen(metadata_url + name) as r:
                data = r.read()
        except Exception:
            continue
        with open(root_path, "wb") as f:
            f.write(data)
        log.warning("TUF: bootstrapped root via TOFU from %s%s (no pinned root)", metadata_url, name)
        return data
    raise VerificationError("could not bootstrap TUF root from " + metadata_url)


def verify_assets(assets, metadata_url, target_base_url, owner, app, platform, arch, trust_dir):
    """Bind the artifacts Velopack is about to install to faynoSync's TUF root of
    trust. `assets` are VelopackAsset objects (FileName/SHA256/Size). Raises
    VerificationError on any mismatch, unknown target, or metadata failure."""
    root_bytes = _load_root(trust_dir, metadata_url)

    updater = Updater(
        metadata_dir=trust_dir,
        metadata_base_url=metadata_url,
        target_base_url=target_base_url,
        target_dir=trust_dir,
        bootstrap=root_bytes,
    )
    # verifies signatures, thresholds, expiration, and version monotonicity
    updater.refresh()

    prefix = f"velopack/{owner}/{app}/{platform}/{arch}"
    for asset in assets:
        target_path = f"{prefix}/{asset.FileName}"
        info = updater.get_targetinfo(target_path)
        if info is None:
            raise VerificationError(f"no TUF-signed target for {target_path}")

        want = asset.SHA256.lower()
        got = (info.hashes.get("sha256") or "").lower()
        if got != want:
            raise VerificationError(f"sha256 mismatch for {target_path}: feed={want} tuf={got}")
        if info.length != asset.Size:
            raise VerificationError(f"size mismatch for {target_path}: feed={asset.Size} tuf={info.length}")

        log.info("TUF: verified %s (sha256 ok, %d bytes)", asset.FileName, info.length)
