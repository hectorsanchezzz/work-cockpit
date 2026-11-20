# Work Cockpit

One local page with everything on my plate across lanes (NTT, university subjects, hockey, personal), so quiet lanes stop being deferred. The weekly timetable and the university calendar feed give the days; GitHub is read only.

Live at http://127.0.0.1:8765/ (localhost only, served by `serve.py`), with settings at http://127.0.0.1:8765/settings.html, and `out/summary.json` holds what is left today ("N today") for any tray or status tool you want to point at it.

This copy runs on **Windows**. Apple Reminders and Calendar do not exist there, so the calendar comes from iCal feeds and Reminders are off (see Sources).

## Sources

- Linear: GraphQL API, read-only queries. Personal API key from the `COCKPIT_LINEAR_KEY` environment variable, or from the OS credential store (`pip install keyring`, then `python -m keyring set cockpit-linear cockpit`). Never written to disk.
  To not use Linear at all, set `"linear": false` in `config.json`: no calls, no error line.
- Calendar: iCal / `.ics` feeds listed in `calendar_ics` in `config.json` (name + URL), read only. Works with Moodle, Google Calendar's secret address, Outlook's published calendar, etc. The URL often carries a secret token, so it lives only in `config.json` (git-ignored) and errors never print it. Map a feed to a lane with `calendars` (feed name to lane).
- Weekly timetable: `weekly_schedule` in `config.json` (day, start, end, title, lane) repeats every week as calendar events (`schedule.py`). Feed events go to a lane by `title_keywords`, matched against the title and the feed's category (for Moodle, the course name).
- Apple Reminders (macOS only, `~/bin/ekctl`): without `ekctl` there are no reminders and the reminder actions refuse.
- GitHub: `gh` (install the GitHub CLI and run `gh auth login`). Without it the section shows one quiet error line.
- Local git repos under `code_root`, and the vault git log.

## Test sources (each can be switched off)

Marked "Test" on the page. Each has a switch on the settings page, under Sources; the setting is saved in `data/sources.json` and survives refreshes and restarts. A source that is off makes no calls and its section is not drawn at all.

- GitHub pull requests (`github_prs`, on by default): open PRs where your review is requested, plus your own open PRs, with age and a red "quiet Nd" past `stale_days`. One `gh search prs` per login in `github_accounts`, the token passed per call as `GH_TOKEN=$(gh auth token -u <login>)`, never `gh auth switch`. If a login fails (signed out, offline) the section shows one quiet line and the rest of the page loads.
- Include Blvck Sigma repos (`github_prs_bs`, off by default): adds the logins in `github_bs_accounts` (default `blvcksigma-app`) and repos owned by Blvck-Sigma. Titles go through `redact_words` like everything else.
- Rize tracked time (`rize`, on by default): hours per lane this week (Monday to now) against last week, from the Rize GraphQL API (`timeAllocation` grouped by project). The key comes from `COCKPIT_RIZE_KEY` or the credential store (`python -m keyring set cockpit-rize cockpit`) on each run and never written anywhere. A Rize project maps to a lane through `rize_projects` in `config.json` (exact name, any case), then `linear_projects`, then `title_keywords`; the rest shows as "No lane for project" or "No project in Rize". Rize project names name clients, so only per-lane totals reach `data/extras.json` and the page.

- Claude sessions (`claude_sessions`, off by default): Claude Code sessions active in the last 7 days, newest first, each with an Open link (`claude://claude.ai/epitaxy/<session id>`) into the desktop app. Read from the app's local session files (`%APPDATA%\Claude\claude-code-sessions\`). Those files are undocumented and may change with any app update, so a read failure is one quiet line and the rest of the page loads. Only id, title, folder name, lane (from `code_path_keywords`, then `title_keywords`) and times are kept; no transcript, prompt or report text. Scheduled-task runs and archived sessions are left out. Titles go through `redact_words`.

To turn one off by hand: set its key to `false` in `data/sources.json`. It takes effect on the next refresh, or run `./run.sh`.

Not built, on purpose:
- A "waiting on you" status for Claude sessions: the desktop app keeps that in memory only. Its session files have no reliable field for it, so the sessions list shows last activity and does not guess from transcripts.

## Reminder actions

Tick the circle on an open reminder to mark it done. Its menu also has Tomorrow, Next week, Pick a date, Remove date, Rename and Cancel; in Possible duplicates, keeping one cancels the other. Two reminders count as possible duplicates when their titles are nearly the same and carry the same numbers (so "1M net worth" and "5M net worth" stay apart), or when they are due the same day and share at least 3 words (small words left out) making up 40% of the shorter title. That section is small and sits last by default; it shows 3 pairs and folds the rest. Every action waits 5 seconds with an Undo (or Cmd+Z) before it is sent. Cancel adds a note ("Cancelled in cockpit on <date>", naming the kept reminder for a duplicate), stops a repeat and completes it. `ekctl` has no delete on purpose, so a cancelled reminder stays in Completed and can be reopened in Reminders. Only open reminders in lists that are read can be touched. Every write is one line in `logs/actions.log`.

Carried over is split by age: This week (up to 7 days late), Slipping (8 to 30) and Stale (over 30). The Triage button walks through everything more than 7 days late, reminders first, oldest first, one card at a time. Keys for a reminder: D done, T tomorrow, W next week, S someday (removes the date), K needs thinking, C cancel, N skip. A Linear item only gets O (open in Linear) and N, since Linear stays read-only. Z undoes the last one within the 5 seconds, Esc closes. Skipped items stay in Carried over.

Needs thinking moves a reminder to a list called Think in Reminders, with no date and a note saying which list it came from. That list has to exist (`ekctl` cannot create one); until it does, the option is shown greyed out. Think items get their own section, Needs thinking, and leave Carried over. Giving one a date moves it back to the list it came from.

## Links between sections

Each day in a lane's "Next 7 days" opens Day by day filtered to that lane, with that day ringed in the lane's colour (on a phone it scrolls to the day itself). The lane chips above Day by day filter it by hand; "All lanes" clears it. The filter lives in the address (`#days?lane=axis&day=2026-11-18`), so Back undoes it and a reload keeps it. The cells are links only while Day by day is shown. The target is the cockpit's own Day by day, not the Calendar app: Calendar has no link to open a given date, and it would not show reminders or Linear items.

A Linear issue opens in the Linear app (the page turns `https://linear.app/...` into `linear://...`, the address the app registers). Cmd-click or a middle click opens the website instead. The first time, the browser may ask to open Linear; tick Always allow.

The summary tiles open the section behind their number: Overdue opens Carried over, Waiting on you opens the first lane with something waiting, and Lanes going quiet opens the first quiet lane, while each quiet lane's name opens its own. The lane it opens rings once in its colour. A tile is plain text while its target section is hidden.

## Settings page

`/settings.html` saves as you change things:
- Sources: the test sources above.
- Sections of the main page: show or hide, and order (drag the grip or use the arrows). Saved in `data/layout.json`.
- Lanes: order, name and hours per week. Freshness: `stale_days`. Reminder lists and calendars to read or skip. These edit `config.json` in place (same key order); the previous version is kept as `config.json.bak`.

Lane mapping rules (including `rize_projects`) and `redact_words` are not on the page, on purpose: edit them in `config.json` by hand.

## Files

- `run.ps1`: one refresh. Takes a lock, then runs collect, Linear, extras, render_v2, proposals --live and build_local.
- `platform_util.py`: what differs per system: Python path, lock folder, UTF-8 for child scripts, API keys.
- `ics_feed.py`: iCal feeds into calendar events (standard library only). `schedule.py`: the weekly timetable into events.
- `sources.py`: which test sources are on (`data/sources.json`).
- `extras.py`: the enabled test sources into `data/extras.json`.
- `serve.py`: the localhost server. Serves `out/`, plus `GET`/`POST /api/settings` and `POST /api/reminder` (JSON, own host and origin only). A save rebuilds only what it needs, under the refresh lock.
- `settings.py`: what the settings page reads and validates before writing anything.
- `reminder_actions.py`: the reminder actions, through `ekctl` (macOS only), logged to `logs/actions.log`.
- `collect.py`: Calendar, GitHub, local repos and vault (and Reminders where `ekctl` exists) into `data/local.json`.
- `linear_fetch.py`: Linear into `data/linear.json`. On failure it keeps the last good snapshot (an empty one the first time) and shows the error on the page.
- `render_v2.py`: the data model, `out/summary.json` and the older v2 page `out/cockpit-v2.html`. `render.py` is the retired v1.
- `build_local.py`: `out/index.html` (title, icon, auto-reload) from `out/cockpit-d.html`, falling back to the v2 page if the D step failed that run.
- `proposals.py`: the live design. `--live` (run by the refresh) writes design D, Precision, to `out/cockpit-d.html`, and the settings page to `out/settings.html`. Without the flag it writes all four design proposals to `out/proposals/{a,b,c,d}.html` for comparing.
- `model.py`: shared lane mapping and helpers.
- `windows/`: `install-tasks.ps1` and `uninstall-tasks.ps1` (Task Scheduler).

## Setup on Windows

Needs Python 3.10+ and git. Optional: the GitHub CLI `gh`, and `pip install keyring`.

1. `copy config.example.json config.json`, then fill in lanes, mappings, `calendar_ics`, `github_accounts`, `code_root`, `vault_path` and `redact_words`. `config.json` is git-ignored on purpose: it names clients and holds feed tokens.
2. Linear key: `setx COCKPIT_LINEAR_KEY lin_api_...` (then open a new terminal), or the keyring command above.
3. First run: `powershell -ExecutionPolicy Bypass -File run.ps1`, then `python serve.py` and open http://127.0.0.1:8765/. `run.ps1` and `serve.py` set `PYTHONUTF8=1` themselves; set it too if you run the other scripts by hand, or accents break.
4. Automatic: `powershell -ExecutionPolicy Bypass -File windows\install-tasks.ps1` registers "Cockpit refresh" (at logon, then every 30 minutes) and "Cockpit server" (at logon). `windows\uninstall-tasks.ps1` removes them.

5. Desktop shortcut: `powershell -ExecutionPolicy Bypass -File windows\create-shortcut.ps1` puts "Work Cockpit" on the Desktop and in the Start menu. It starts the server if needed, refreshes if the data is over 30 minutes old, and opens the page.

The macOS pieces (launchd agents, SwiftBar plugin, `run.sh`, Keychain) were removed in the Windows port; they are in the git history before it.

## Not in the repo

`config.json`, `config.json.bak`, `data/`, `out/` (except the icon) and `logs/`. They hold client names, issue titles and personal calendar data.
