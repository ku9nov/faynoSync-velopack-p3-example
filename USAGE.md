# Usage walkthrough

End-to-end walkthrough: stand up faynoSync locally, publish this example app, then
exercise updates, downgrades, TUF verification, intermediate builds, telemetry, and
reports.

> **NOTE:** These steps were written and tested on **macOS arm64**. Depending on your
> machine, some links and commands (platform/arch names, install paths) will differ.

For a config/env reference, see [README.md](README.md).

## 1. Run faynoSync

```bash
git clone https://github.com/ku9nov/faynoSync.git
cd faynoSync
docker compose up --build
docker compose exec -T backend /usr/bin/faynoSync migrate up
```

This brings up all required services:

- API — http://localhost:9000
- Frontend — http://localhost:3000

We work from the frontend for now.

## 2. Dashboard setup

Open http://localhost:3000.

1. **Register** — fill the fields. For `secretKey` use the local-dev default
   `UHp3aKb40fwpoKZluZByWQ`.
2. **Log in.**
3. **Create App** → name `HelloVelopack` → Create.
4. **Channels** → Create Channel → name `nightly`.
5. **Platforms** → Create Platform → create the one matching your machine
   (`darwin` / `windows` / `linux`). In Updaters choose **velopack**, then Create.
6. **Architectures** → Create Architecture → create `amd64` or `arm64` depending on
   your machine.

## 3. Build the example app

From this repo root, set up the venv (once):

```bash
python3 -m venv .venv
.venv/bin/pip install velopack tuf securesystemslib cryptography pyinstaller
```

Build:

```bash
./build.sh
```

You now have everything you need in `releases/`.

## 4. Upload and install the first version

In the dashboard: **Applications** → **Upload the app**. Fill all fields, updater
**velopack**, and upload these files:

```
releases.nightly.json
HelloVelopack-1.0.0-nightly-full.nupkg
HelloVelopack-nightly-Setup.pkg
```

Set the **publish** checkbox to true and click **Upload**.

You now have four objects on S3:

```
.../velopack/admin/HelloVelopack/darwin/arm64/releases.nightly.json
.../velopack/admin/HelloVelopack/darwin/arm64/HelloVelopack-1.0.0-nightly-full.nupkg
.../velopack/admin/HelloVelopack/darwin/arm64/HelloVelopack-nightly-Setup.pkg
.../velopack/admin/HelloVelopack/darwin/arm64/installers/HelloVelopack-nightly-Setup-1.0.0-darwin-arm64.pkg
```

(base host: `http://cb-faynosync-s3-public.web.garage.localhost:3902`)

The fourth object under `installers/` is a version-pinned copy of the Setup artifact —
useful for dev/QA teams that need to install a **specific** version rather than only the
latest.

Download the pinned installer and install it:

```bash
sudo installer -pkg ~/Downloads/HelloVelopack-nightly-Setup-1.0.0-darwin-arm64.pkg -target /
```

Run it:

```bash
/Applications/HelloVelopack.app/Contents/MacOS/HelloVelopack
```

Expected output:

```
[INFO] Hello from hello-velopack v1.0.0  (darwin/arm64)
[INFO] Checking updates: admin/HelloVelopack  platform=darwin arch=arm64
[INFO] Feed URL: .../velopack/admin/HelloVelopack/darwin/arm64/releases.nightly.json
Couldn't write out staging userId.
[INFO] Already on the latest version (1.0.0).
```

## 5. Ship an update (FULL, then DELTA)

Bump the version in `app_version.py` from `1.0.0` to `1.0.1`, then rebuild:

```bash
./build.sh
```

Upload the new version (publish = true) with these files:

```
releases.nightly.json
HelloVelopack-1.0.1-nightly-full.nupkg
HelloVelopack-1.0.1-nightly-delta.nupkg
HelloVelopack-nightly-Setup.pkg
```

Run the app again:

```bash
/Applications/HelloVelopack.app/Contents/MacOS/HelloVelopack
```

```
[INFO] Hello from hello-velopack v1.0.0  (darwin/arm64)
[INFO] Update available: 1.0.0 -> 1.0.1  (upgrade) via FULL (13355053 bytes)
[INFO] TUF verification disabled (set TUF_ENABLED=true to enable)
[INFO] Downloading...
[INFO] Downloaded. Applying and exiting; re-run to launch 1.0.1.
```

`FULL` is expected here — it's the first update. Publish `1.0.2` the same way and the
next update comes down as a `DELTA`:

```
[INFO] Hello from hello-velopack v1.0.1  (darwin/arm64)
[INFO] Update available: 1.0.1 -> 1.0.2  (upgrade) via DELTA (1 package(s), 172110 bytes)
[INFO] Downloading...
[INFO] Downloaded. Applying and exiting; re-run to launch 1.0.2.
```

## 6. Downgrade (revocation) — optional

Say `1.0.2` is installed. On the dashboard set **publish = false** for that version. The
next run rolls back to the latest still-published version:

```
[INFO] Hello from hello-velopack v1.0.2  (darwin/arm64)
[INFO] Update available: 1.0.2 -> 1.0.1  (DOWNGRADE (revoked?)) via FULL (13355053 bytes)
[INFO] Downloading...
[INFO] Downloaded. Applying and exiting; re-run to launch 1.0.1.
```

## 7. TUF verification

> Managing TUF metadata is not trivial, even locally. The dashboard tries to simplify it
> with generated instructions, but it can still be confusing and user error is easy.
> **Reproduce the dashboard's commands and scripts exactly.**

Scenario: `1.0.0` is installed; `1.0.1` and `1.0.2` are uploaded but not yet published.
Whether or not TUF was configured earlier does not affect the TUF algorithms — it's fine.

1. Enable TUF for the app: **Applications** → **Edit** on the app → check **Enable TUF**
   → **Update**.
2. On the dashboard, click the **gear** → **Settings**.
3. Choose **TUF** and your app. You now see generated instructions.
4. Run **Step 1** exactly. From the faynoSync repo root:

   ```bash
   cd tuf_keys
   # ...then follow the rest of the dashboard instructions verbatim
   ```

After a successful bootstrap you can start signing versions.

On the app's versions page, a published-but-unsigned version **blinks red** — that's the
signal it isn't signed yet. Click the **shield** icon to sign it. Publish `1.0.1` and
sign it too.

Run with TUF enabled:

```bash
TUF_ENABLED=true /Applications/HelloVelopack.app/Contents/MacOS/HelloVelopack
```

```
[INFO] Hello from hello-velopack v1.0.0  (darwin/arm64)
[INFO] Update available: 1.0.0 -> 1.0.1  (upgrade) via DELTA (1 package(s), 162465 bytes)
[WARNING] TUF: bootstrapped root via TOFU from .../tuf_metadata/admin/HelloVelopack/1.root.json (no pinned root)
[INFO] TUF: verified HelloVelopack-1.0.1-nightly-full.nupkg (sha256 ok, 13355053 bytes)
[INFO] TUF: verified HelloVelopack-1.0.1-nightly-delta.nupkg (sha256 ok, 162465 bytes)
[INFO] Downloading...
[INFO] Downloaded. Applying and exiting; re-run to launch 1.0.1.
```

Now publish `1.0.2` **without signing it** and run again:

```
[INFO] Hello from hello-velopack v1.0.1  (darwin/arm64)
[INFO] Update available: 1.0.1 -> 1.0.2  (upgrade) via DELTA (1 package(s), 172110 bytes)
[ERROR] TUF verification FAILED, not applying update: no TUF-signed target for velopack/admin/HelloVelopack/darwin/arm64/HelloVelopack-1.0.2-nightly-full.nupkg
```

This is the expected behavior: once TUF is on, trust verification is mandatory. If we
can't be sure the served artifacts are authentic, we reject them.

## 8. Intermediate builds — optional

> **INFO:** Velopack's `VelopackAsset` has a limited set of fields, so we can't natively
> mark **critical** and **intermediate** builds through it. Rather than maintain a large
> number of SDKs across all the languages Velopack supports, these faynoSync features are
> implemented on the plain client with no extra SDK.

Scenario: rolled back to `1.0.0`; `1.0.0`, `1.0.1`, `1.0.2` all published, but `1.0.1` is
marked **intermediate**.

The API-served feed then returns the intermediate as the target instead of the latest:

```bash
curl --location 'http://localhost:9000/velopack/admin/HelloVelopack/darwin/arm64/releases.nightly.json?localVersion=1.0.0&id=HelloVelopack'
```

```json
{
  "Assets": [
    { "PackageId": "HelloVelopack", "Version": "1.0.1", "Type": "Full",  "FileName": "HelloVelopack-1.0.1-nightly-full.nupkg",  "SHA256": "FE9E96E1...", "Size": 13355895 },
    { "PackageId": "HelloVelopack", "Version": "1.0.1", "Type": "Delta", "FileName": "HelloVelopack-1.0.1-nightly-delta.nupkg", "SHA256": "4C1A0C6D...", "Size": 189039 },
    { "PackageId": "HelloVelopack", "Version": "1.0.0", "Type": "Full",  "FileName": "HelloVelopack-1.0.0-nightly-full.nupkg",  "SHA256": "D86DCB18...", "Size": 13355733 }
  ]
}
```

The API checks for updates as usual, sees the intermediate build, and serves the update
to the intermediate instead of the latest.

This only works against the **API** feed (which computes the response dynamically),
so set `ASK_API=true` to point the client at `API_BASE` instead of the static CDN:

```bash
ASK_API=true /Applications/HelloVelopack.app/Contents/MacOS/HelloVelopack
```

```
[INFO] Hello from hello-velopack v1.0.0  (darwin/arm64)
[INFO] Feed URL: http://localhost:9000/velopack/admin/HelloVelopack/darwin/arm64/releases.nightly.json
[INFO] Update available: 1.0.0 -> 1.0.1  (upgrade) via FULL (13355895 bytes)
[INFO] Downloading...
[INFO] Downloaded. Applying and exiting; re-run to launch 1.0.1.
```

Run again and it proceeds from the intermediate to the latest:

```
[INFO] Hello from hello-velopack v1.0.1  (darwin/arm64)
[INFO] Update available: 1.0.1 -> 1.0.2  (upgrade) via DELTA (1 package(s), 151857 bytes)
[INFO] Downloading...
[INFO] Downloaded. Applying and exiting; re-run to launch 1.0.2.
```

## 9. Telemetry

```bash
TELEMETRY_ENABLED=true /Applications/HelloVelopack.app/Contents/MacOS/HelloVelopack
```

Then check the **Statistics** page in the dashboard.

## 10. Reports

Enable reports for the app first: **Applications** → **Edit** → check **Enable reports**
→ **Update**. The app's dashboard page now shows a **Report key** — copy it.

```bash
REPORTS_ENABLED=true FAYNOSYNC_REPORT_KEY=rpk_xxx /Applications/HelloVelopack.app/Contents/MacOS/HelloVelopack
```

(Replace `rpk_xxx` with the key from the dashboard.)

```
[INFO] Hello from hello-velopack v1.0.3  (darwin/arm64)
[INFO] report sent: crash/synthetic_demo_crash (HTTP 202)
[INFO] Already on the latest version (1.0.3).
```

> The example app never actually crashes — it emits a **synthetic** crash report so you
> can exercise `/reports/ingest` end to end. See `_report_event` in `app.py`.

Then check the **Reports** page.
