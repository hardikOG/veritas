# Bug Journal

Loop A log: every debugging cycle triggered by an error, failed test, failed build, or
unexpected output. One entry per incident: symptom, hypotheses tried (including
refuted ones), root cause, fix, one-line lesson.

<!-- Entries are appended below as they occur. -->

## Phase 0 — Docker Desktop backend wouldn't start (`docker compose up` failed before touching any project code)

**Symptom:** `docker compose up --build -d` failed immediately:
`unable to get image 'veritas-worker': failed to connect to the docker API at
npipe:////./pipe/dockerDesktopLinuxEngine ... The system cannot find the file
specified.`

**Hypotheses tried:**
1. Daemon just not started yet, `docker info`/process check would confirm — refuted
   at first (no docker process running), then the process launched but `docker info`
   still failed after 12+ minutes of polling.
2. Slow first-time WSL2 startup — refuted: process list showed Docker Desktop's
   processes disappearing entirely between checks, i.e. it was crashing, not slowly
   booting.
3. Confirmed via `electron-errd-*.log`/`monitor.log`: the backend crashed on
   `starting services: initializing Inference manager: listening on
   unix://.../dockerInference: remove ...: The file cannot be accessed by the
   system.` — a stale AF_UNIX socket special-file left over from an unclean previous
   shutdown, which Docker tries to unlink and recreate on every boot and fails.

**Root cause:** stale Unix-domain-socket reparse points under
`%LOCALAPPDATA%\Docker\run\` (`dockerInference`, `dockerEthernetVfkit`,
`userAnalyticsOtlpHttp.sock`) that Windows-side APIs (PowerShell `Remove-Item`
included — `IOException: The file cannot be accessed by the system`) cannot delete,
because they're true Unix sockets exposed through NTFS reparse points. Recurred a
second time on a different socket (`docker-secrets-engine\engine.sock`), confirming
this is a systemic stale-socket issue, not a one-off.

**Fix:** delete the stale socket files from the WSL (Linux) side instead of Windows,
via the already-installed `Ubuntu` WSL distro reaching the same files through its
`/mnt/c/...` bind mount: `wsl -d Ubuntu -- rm -f /mnt/c/Users/.../dockerInference
...`. Windows `rm`/`Remove-Item` cannot unlink these; WSL `rm` can, because it's a
real Unix filesystem operation on what is, underneath, a real Unix socket.

**Lesson:** if Docker Desktop's backend crashes on Windows with "The file cannot be
accessed by the system" / "The filename, directory name, or volume label syntax is
incorrect" while (re)creating a socket under its own AppData `run` directories, don't
try to fix it from Windows (PowerShell delete will fail the same way) — delete the
stale socket file(s) from a WSL shell instead.

## Phase 1 — `torch==2.5.1+cpu` no longer resolvable on the CPU wheel index

**Symptom:** `pip install -r requirements-dev.txt` failed:
`ERROR: Could not find a version that satisfies the requirement torch==2.5.1+cpu
(from versions: 2.6.0, 2.6.0+cpu, 2.7.0, ...)`.

**Hypothesis:** the pinned version had aged out of the `download.pytorch.org/whl/cpu`
index (older CPU wheels get pruned over time); confirmed directly from pip's own
"from versions" list, no guessing needed.

**Fix:** repinned to `torch==2.6.0+cpu`, the oldest version pip's error actually
listed as available.

**Lesson:** when pinning from an external wheel index (not plain PyPI), verify the
exact pin still resolves before trusting it — these indexes prune old CPU builds
more aggressively than PyPI prunes normal releases.

## Phase 1 — `python-multipart` missing for FastAPI file uploads

**Symptom:** `pytest` failed collecting any test that imports `api.main`:
`RuntimeError: Form data requires "python-multipart" to be installed.`

**Root cause:** `api/documents.py`'s `POST /documents` takes an `UploadFile`
parameter, which FastAPI parses as multipart form data — a runtime dependency
(`python-multipart`) that isn't pulled in by `fastapi` itself and wasn't in
requirements.txt.

**Fix:** added `python-multipart==0.0.20` to `requirements.txt` (api-side, no heavy
transitive deps).

**Lesson:** any route taking `UploadFile`/`Form(...)` needs `python-multipart`
installed explicitly — FastAPI only raises this at route-registration time, not at
`pip install` time, so it surfaces as an app-startup crash, not a missing-package
error at install.

## Phase 1 — `send_task` doesn't respect `task_always_eager` (test assumption, not app bug)

**Symptom:** integration test failed: `assert 'queued' == 'ready'` immediately after
POSTing a document, with a captured warning: `AlwaysEagerIgnored: task_always_eager
has no effect on send_task`.

**Hypothesis:** the test assumed setting `celery_app.conf.task_always_eager = True`
would make `celery_app.send_task(...)` execute synchronously in-process.

**Test:** the warning itself confirmed it directly — no need for a second test.

**Root cause:** Celery's eager-mode config only intercepts `Task.apply_async()`/
`.delay()` on a locally bound task object; `send_task()` (used deliberately in
`api/documents.py` so the api process never imports the task's heavy ML deps) always
publishes to the real broker.

**Fix:** the test now invokes `ingestion.tasks.ingest_document(document_id)` directly
after the API call, simulating what a real worker would do — the same pattern the
crash-redelivery test already used correctly.

**Lesson:** this was a test-only bug, not an application bug — the app's dispatch-
by-name design is correct and intentional; don't "fix" `api/documents.py` to call
the task object directly, that would reintroduce the heavy-dependency coupling the
design specifically avoids.

## Phase 1 — mypy can't parse numpy's PEP 695 stub syntax under `python_version = "3.11"`

**Symptom:** `mypy api core db models worker embedding ingestion` failed on the very
first file it opened: `.venv\Lib\site-packages\numpy\__init__.pyi:737: error: Type
statement is only supported in Python 3.12 and greater [syntax]`.

**Hypotheses tried:**
1. Per-module override (`module = "numpy.*"`, then `["numpy", "numpy.*"]`, `follow_imports
   = "skip"`) — refuted twice: identical error both times, because this is a PARSE
   failure, which happens before per-module type-check settings are applied.
2. Upgrade mypy (1.13.0 -> 2.3.0) in case newer mypy unconditionally allows PEP 695
   syntax in `.pyi` stub files regardless of target — refuted: identical error even
   on the latest mypy release.
3. Raise mypy's own `python_version` target to `"3.12"` — confirmed: this is
   mypy's *parsing* target, separate from the app's actual runtime target (still
   3.11 per the Dockerfiles); nothing in this codebase uses 3.12-only syntax, so
   raising it only lets mypy read newer third-party stub syntax without changing
   what's actually deployed.

**Lesson:** a mypy stub-syntax parse error (not a type-check error) can't be
silenced by per-module `ignore_errors`/`follow_imports` overrides — those only apply
post-parse. If a transitive dependency's stubs use syntax newer than
`python_version`, the fix is to raise `python_version` in the mypy config itself,
which is independent of the project's real deployment target.

## Phase 1 — Docker Desktop's WSL2 data disk corrupted mid-build (machine issue, not app)

**Symptom:** `docker compose build` for the worker image failed after `pip install`
fully succeeded: `error committing ...: write
/var/lib/docker/buildkit/containerd-overlayfs/metadata_v2.db: read-only file
system`.

**Hypothesis:** given this machine's history of unclean Docker Desktop shutdowns
earlier the same day (see the stale-socket entry above), the underlying WSL2 data
disk might have sustained real corruption, not just a transient glitch.

**Test:** read the `docker-desktop` WSL distro's own kernel log (`wsl -d
docker-desktop -- dmesg`), rather than guessing from the build error alone.

**Confirmed directly, no ambiguity:** `Buffer I/O error on dev sde`, `Aborting
journal on device sde-8`, `EXT4-fs (sde): Remounting filesystem read-only`. Real
I/O errors on Docker Desktop's data virtual disk (`docker_data.vhdx`, ~9.4GB),
independent of the ~34GB free space on the host D: drive (ruled out disk-full as a
cause).

**Fix (user chose the reset option after being shown the tradeoff):**
1. `wsl --shutdown`, then `wsl --unregister docker-desktop` (releases file locks).
2. Deleted the corrupted `C:\Users\hardi\AppData\Local\Docker\wsl\disk\docker_data.vhdx`
   directly (left `wsl\main\ext4.vhdx`, the distro's own base system, untouched).
3. Relaunched Docker Desktop, which recreated both fresh. Confirmed via `docker ps
   -a`/`docker info` showing 0 containers/images (expected — full reset) and a
   healthy `Server Version`/`Storage Driver` report.

**Side effects hit while recovering, each independently resolved:**
- The known `dockerInference` stale-socket crash (see the earlier entry) recurred
  *repeatedly* on relaunch attempts. Root cause of the recurrence: Docker Desktop's
  own background auto-updater was triggering an internal engine restart
  (`automatic update: found update... shutting down engines`) immediately after
  launch, and that internal restart re-tripped the identical stale-socket bug —
  this was happening independent of anything done manually. Fix stayed the same
  (delete via WSL, relaunch) but had to be reapplied more than once before the
  update cycle finished landing.
- A second, *different* stale file: `C:\Users\hardi\AppData\Local\docker-secrets-engine\engine.sock`.
  This one could NOT be deleted via the WSL trick — `wsl -d Ubuntu -- stat` on it
  returned "No such file or directory" even though Windows' `Get-Item -Force` showed
  it as a real `Archive, ReparsePoint` file. Root cause: unlike the earlier sockets
  (created by Docker's Linux-side components, visible through WSL's DrvFs bridge),
  this one is created directly by a native Windows process
  (`com.docker.backend.exe`) as a native Windows AF_UNIX socket reparse point —
  genuinely invisible to WSL, so the WSL-delete trick doesn't apply to every stale
  Docker socket, only the Linux-originated ones. **Fix:** `Rename-Item` on the
  *containing folder* succeeded where deleting the file itself failed — a rename
  doesn't require Windows to interpret the reparse point's special data the way a
  delete does. Docker recreated a fresh `docker-secrets-engine\engine.sock` on next
  launch without issue.
- One of my own restart attempts hung for 10 minutes for a mundane reason: I ran the
  delete-and-poll step but forgot to actually call `Start-Process` on Docker Desktop
  first, so `docker info` was correctly failing because nothing was launched — not a
  new instance of the bug. Caught by checking `Get-Process` (nothing running) before
  chasing a phantom new failure mode.

**Lesson:** (1) a corrupted WSL2-backed virtual disk shows up first as ordinary-
looking build/write errors ("read-only file system") — always check the WSL
distro's own `dmesg` before assuming it's an application-level problem. (2) not
every "stale Docker socket" fix is the same fix — Linux-side sockets are deletable
via WSL, native-Windows-side sockets are not and need a rename-the-parent-folder
workaround instead. (3) Docker Desktop's own auto-update cycle can independently
retrigger a bug that looks identical to a manually-caused one; don't assume a
recurrence is caused by whatever you just did.

## Phase 0 — `pip install` failed mid-build with a JSONDecodeError on a PyPI index page

**Symptom:** `docker compose up --build` failed during the `worker` image's `pip
install --no-cache-dir -r requirements.txt` step:
`json.decoder.JSONDecodeError: Unterminated string starting at: line 1 column
2944313 (char 2944312)` — a truncated HTTP response while pip parsed a PyPI simple-
index page.

**Hypothesis:** transient network glitch (likely related to Docker's networking
having just restarted alongside the daemon), not a systemic proxy/DNS/MTU problem —
a bare retry should succeed.

**Test:** `docker compose build` again, no other changes.

**Result:** confirmed — the retry built both images cleanly with no errors. No fix
needed beyond retrying.

**Lesson:** don't over-diagnose a single flaky `pip install` failure right after a
Docker Desktop restart — retry once before assuming a real networking config issue.
