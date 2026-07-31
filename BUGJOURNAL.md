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
