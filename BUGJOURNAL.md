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

## Phase 2 — one-off `UniqueViolation` on chunk redelivery, could not reproduce (unresolved, documented rather than "fixed")

**Symptom:** `test_upload_ingests_and_reupload_is_idempotent` failed once:
`psycopg.errors.UniqueViolation: duplicate key value violates unique constraint
"uq_chunks_document_index"` — a fresh `_run_ingestion` insert (4 new chunk rows,
fresh UUIDs) conflicted with 4 pre-existing rows for the same document_id from an
earlier successful ingestion of the same (deterministic-checksum) test content.

**Hypotheses tried, in order:**
1. The DELETE in `_run_ingestion` doesn't actually remove old rows before the
   INSERT — tested directly: ran the exact DELETE against this exact document_id in
   an isolated script, recounted rows in the same uncommitted transaction. Result:
   4 -> 0. Refuted — the delete works correctly in isolation.
2. Delete-then-insert-in-one-transaction has some ordering issue specific to this
   codebase — tested by replicating delete + add_all + commit in an isolated
   script against the same document_id. Result: committed successfully. Refuted.
3. `_run_ingestion` itself has a real bug — called the actual function (not a
   reimplementation) directly, twice in a row, against the same document. Both
   calls succeeded. Refuted.
4. The full `ingest_document` task wrapper (not just `_run_ingestion`) has a bug —
   called it directly outside pytest/Celery entirely. Succeeded, ended in `status
   = "ready"`. Refuted.
5. Ran `tests/test_ingestion.py` alone, then the full suite, multiple times after
   the above. 22/22 passed every time, including this exact test.

**Conclusion:** every direct reproduction of the real code path (not a simplified
stand-in) succeeded. Could not reproduce after 4 independent attempts targeting the
exact same document/code. Treating this as a one-off environmental hiccup during
that specific run (this session had already had significant Docker/WSL2 instability
— see the disk-corruption entry above — so a transient connection blip during that
one process's lifetime is plausible) rather than a confirmed code defect. Not
"fixed" because there is nothing confirmed to fix — the idempotency logic has been
independently verified correct via direct reproduction of the exact failing
scenario, multiple times, immediately after the failure.

**Lesson:** per this project's own Loop A discipline — do not stack an invented fix
on an unconfirmed hypothesis. If this recurs, capture the DB state (`chunks` table
for the affected document_id) *before* touching anything, since re-running
diagnostics mutates the very state needed to compare "before" vs "after" the
failure.

## Phase 2 (resumed session) — C: drive hit 0 bytes free, then Docker crash-looped on every boot

**Symptom:** after resuming this session ~10 days later, `docker compose up` failed
with `request returned 502 Bad Gateway ... Docker Desktop is unable to start`, and
even a plain `tail` command failed with `No space left on device`.

**Root cause, confirmed directly:** `Get-PSDrive C` showed **0 GB free** on the
entire C: drive (231.53 GB used of 231.53 GB). Not a Docker-specific problem — the
whole system was out of disk space, which explains the 502, the crash, and plausibly
contributed to *why* Docker kept re-crashing afterward (see below).

**Fix (partial, machine-wide, flagged to the user rather than silently expanded
into general system cleanup):** reclaimed Docker's own `docker_data.vhdx` (~13GB,
entirely reproducible build cache/images from this project's repeated
torch/sentence-transformers builds) via the same unregister-and-delete approach as
the first disk-corruption incident. Freed C: from 0 -> ~19GB. Did not touch anything
outside Docker's own footprint — a fully-full system drive is the user's call, not
something to unilaterally "clean up" by deleting arbitrary files.

**Follow-on symptom:** even with free space restored, Docker Desktop crash-looped on
*every single boot* — not a leftover-from-unclean-shutdown pattern (the usual stale
dockerInference/docker-secrets-engine socket issue, both of which recurred here too
and were fixed the same way as before), but recreating the same crash fresh each
time, cycling between the two known sockets.

**Actual root cause of the boot-loop:** `C:\Users\hardi\AppData\Local\Temp\
DockerDesktopUpdates\` contained a fully-downloaded but not-yet-applied Docker
Desktop updater installer (148MB), timestamped right in the disk-full window. Docker
Desktop's own internal auto-update sequence (`shutting down engines` ->
attempt install -> restart) was very plausibly what triggered the repeated internal
restarts that kept re-tripping the socket bug — an update download/apply is
exactly the kind of large disk write that a 0-free-space window could plausibly
interrupt or corrupt.

**Fix:** deleted the entire `DockerDesktopUpdates` temp folder (a safe target —
it's a re-downloadable installer cache, not user or project data), cleared the
known stale sockets one more time, relaunched. Booted clean on the first attempt.

**Lesson:** "crashes on a known stale-socket bug" and "crashes on *every* boot with
no stale-socket leftover to explain it" are different failure classes needing
different fixes — the second one meant something was actively re-triggering the
crash on each fresh start, not just leftover state from the last unclean exit.
Check `%TEMP%\DockerDesktopUpdates` for a stuck update whenever Docker Desktop
crash-loops immediately after a low-disk-space event.

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
