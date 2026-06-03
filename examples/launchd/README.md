# Scheduled ingestion with launchd (macOS)

Keep one Context-Hub project in sync automatically by running
`context-hub ingest all` on a fixed interval — **no long-running `serve`
process required**. `ingest all` pulls every *enabled* source (Slack / Backlog /
Redmine / Gmail) and, when `CH_INBOX_DIR` is set, scans the inbox folder, all in
one run. A failure in one source is logged and the others continue.

> Why launchd instead of the in-process scheduler? `context-hub serve` has its
> own APScheduler that can sync on an interval, but it only runs while the server
> is up. A launchd agent keeps syncing even when nothing else is running and
> restarts cleanly across reboots — the simplest, most durable option for a
> Mac mini running one instance per project.

## One command, by hand

```bash
# From the instance directory (the one with .env + data/)
CH_PROFILE=personal INGEST_MODE=live context-hub ingest all
```

Sample output:

```
Ingest-all: project_id='429d1efd-…', 2 enabled source(s), mode=live.
  + slack: status=completed items=12
  + backlog: status=completed items=3
Ingest-all complete. project_id='429d1efd-…' succeeded=2 failed=0
```

## Automate it (every 15 minutes)

1. Find your executable path:

   ```bash
   which context-hub
   ```

2. Edit `com.yohakuforce.context-hub.ingest.plist` and replace the three
   placeholders:

   | Placeholder | Replace with |
   |---|---|
   | `__CONTEXT_HUB_BIN__` | output of `which context-hub` |
   | `__PROJECT_DIR__` | the instance dir holding `.env` + `data/` |
   | `__CH_PROFILE__` | `personal` or `production` |

3. Create the log dir, install, and load:

   ```bash
   mkdir -p "<__PROJECT_DIR__>/logs"
   cp com.yohakuforce.context-hub.ingest.plist \
      ~/Library/LaunchAgents/com.yohakuforce.context-hub.ingest.plist
   launchctl load -w ~/Library/LaunchAgents/com.yohakuforce.context-hub.ingest.plist
   ```

4. Verify it ran (RunAtLoad fires once immediately):

   ```bash
   tail -f "<__PROJECT_DIR__>/logs/ingest.out.log"
   ```

### Change the interval

Edit `StartInterval` (seconds) in the plist, then reload:

```bash
launchctl unload ~/Library/LaunchAgents/com.yohakuforce.context-hub.ingest.plist
launchctl load  -w ~/Library/LaunchAgents/com.yohakuforce.context-hub.ingest.plist
```

### Multiple projects on one machine

Run **one agent per project**. Copy the plist with a unique name and `Label`
(e.g. `…​.ingest.clientA`, `…​.ingest.clientB`) and point each `WorkingDirectory`
at that project's instance dir. Each instance keeps its own `.env`, `data/`, and
log files — no cross-contamination.

### Stop / remove

```bash
launchctl unload ~/Library/LaunchAgents/com.yohakuforce.context-hub.ingest.plist
rm ~/Library/LaunchAgents/com.yohakuforce.context-hub.ingest.plist
```

## Linux (cron / systemd) equivalent

cron — every 15 minutes:

```cron
*/15 * * * * cd /srv/context-hub/projectA && CH_PROFILE=production INGEST_MODE=live /usr/local/bin/context-hub ingest all >> logs/ingest.log 2>&1
```

systemd — a `context-hub-ingest@.service` (oneshot, `WorkingDirectory=` per
instance) paired with a `*.timer` using `OnUnitActiveSec=15min` achieves the
same with journald logging.

## Windows (Task Scheduler) equivalent

Register a task that runs `context-hub ingest all` every 15 minutes from the
instance directory. In PowerShell (adjust the paths):

```powershell
$ctx = (Get-Command context-hub).Source        # path to context-hub.exe
$dir = "C:\context-hub\projectA"                # holds .env + data\

$action  = New-ScheduledTaskAction -Execute $ctx -Argument "ingest all" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
             -RepetitionInterval (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "ContextHub-IngestA" -Action $action -Trigger $trigger `
  -Description "Context-Hub: sync all sources for project A"
```

Set `CH_PROFILE` / `INGEST_MODE=live` either in the instance's `.env` (read from
`WorkingDirectory`) or as machine environment variables.

> On stock python.org Windows, SQLite profiles run in FTS-only mode (no semantic
> search) because `sqlite-vec` can't load there — see the project README's
> "Windows support" section. Keyword search and ingestion still work. For full
> semantic search use a conda/miniforge Python or the PostgreSQL profile.

Alternatively, skip the scheduler entirely and keep `context-hub serve` running
as a service — its built-in scheduler auto-syncs every enabled source.
