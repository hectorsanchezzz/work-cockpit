# Work Cockpit

One local page with everything on my plate across lanes (Axis, Blvck Sigma, Delvion, PBE, TFG, Personal), so quiet lanes stop being deferred. Linear and Apple Reminders stay the source of truth. Linear, Calendar and GitHub are only read; the one thing the page writes is a reminder action you click (see below).

Live at http://127.0.0.1:8765/ (localhost only, served by `serve.py`), with settings at http://127.0.0.1:8765/settings.html, plus a SwiftBar counter in the menu bar showing what is left today ("N today": everything dated today, minus events that already started).

## Sources

- Linear: GraphQL API, read-only queries. Personal API key in the macOS Keychain, service `cockpit-linear`, never written to disk.
- Apple Reminders and Calendar: `~/bin/ekctl` (EventKit), never AppleScript.
- GitHub: `gh`.
- Local git repos under `code_root`, and the vault git log.

## Test sources (each can be switched off)

Marked "Test" on the page. Each has a switch on the settings page, under Sources; the setting is saved in `data/sources.json` and survives refreshes and restarts. A source that is off makes no calls and its section is not drawn at all.

- GitHub pull requests (`github_prs`, on by default): open PRs where your review is requested, plus your own open PRs, with age and a red "quiet Nd" past `stale_days`. One `gh search prs` per login in `github_accounts`, the token passed per call as `GH_TOKEN=$(gh auth token -u <login>)`, never `gh auth switch`. If a login fails (signed out, offline) the section shows one quiet line and the rest of the page loads.
- Include Blvck Sigma repos (`github_prs_bs`, off by default): adds the logins in `github_bs_accounts` (default `blvcksigma-app`) and repos owned by Blvck-Sigma. Titles go through `redact_words` like everything else.
- Rize tracked time (`rize`, on by default): hours per lane this week (Monday to now) against last week, from the Rize GraphQL API (`timeAllocation` grouped by project). The key is read from the Keychain, service `cockpit-rize` (`security add-generic-password -s cockpit-rize -a "$USER" -w`), on each run and never written anywhere. A Rize project maps to a lane through `rize_projects` in `config.json` (exact name, any case), then `linear_projects`, then `title_keywords`; the rest shows as "No lane for project" or "No project in Rize". Rize project names name clients, so only per-lane totals reach `data/extras.json` and the page.

- Claude sessions (`claude_sessions`, off by default): Claude Code sessions active in the last 7 days, newest first, each with an Open link (`claude://claude.ai/epitaxy/<session id>`) into the desktop app. Read from the app's local session files (`~/Library/Application Support/Claude/claude-code-sessions/`). Those files are undocumented and may change with any app update, so a read failure is one quiet line and the rest of the page loads. Only id, title, folder name, lane (from `code_path_keywords`, then `title_keywords`) and times are kept; no transcript, prompt or report text. Scheduled-task runs and archived sessions are left out. Titles go through `redact_words`.

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

- `run.sh`: one refresh. Takes a lock, then runs collect, Linear, extras, render_v2, proposals --live and build_local.
- `sources.py`: which test sources are on (`data/sources.json`).
- `extras.py`: the enabled test sources into `data/extras.json`.
- `serve.py`: the localhost server. Serves `out/`, plus `GET`/`POST /api/settings` and `POST /api/reminder` (done, move, nodate, rename, cancel, think; JSON, own host and origin only). A save rebuilds only what it needs, under the refresh lock.
- `settings.py`: what the settings page reads and validates before writing anything.
- `reminder_actions.py`: the reminder actions, through `ekctl`, logged to `logs/actions.log`.
- `collect.py`: Reminders, Calendar, GitHub, local repos and vault into `data/local.json`.
- `linear_fetch.py`: Linear into `data/linear.json`. On failure it keeps the last good snapshot and shows the error on the page.
- `render_v2.py`: the data model, `out/summary.json` (menu bar) and the older v2 page `out/cockpit-v2.html`. `render.py` is the retired v1.
- `build_local.py`: `out/index.html` (title, icon, auto-reload) from `out/cockpit-d.html`, falling back to the v2 page if the D step failed that run.
- `proposals.py`: the live design. `--live` (run by the refresh) writes design D, Precision, to `out/cockpit-d.html`, and the settings page to `out/settings.html`. Without the flag it writes all four design proposals to `out/proposals/{a,b,c,d}.html` (A private desk, B instrument, C agenda, D precision) with a switcher, for comparing.
- `model.py`: shared lane mapping and helpers.
- `menubar/cockpit.1m.py`: SwiftBar plugin, reads `out/summary.json` every minute and shows what is left today; events that already started are greyed in its menu.
- `launchd/`: the three LaunchAgents (refresh every 30 minutes, the localhost server `serve.py`, and the calendar helper).

## Setup on a new Mac

1. `cp config.example.json config.json` and fill in lanes, mappings, emails and `redact_words`. `config.json` is git-ignored on purpose: it names clients.
2. Store the Linear key: `security add-generic-password -s cockpit-linear -a "$USER" -w` (it prompts for the key).
3. Copy `launchd/*.plist` to `~/Library/LaunchAgents/`, fix the paths if the user or folder differ, then `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.cockpit.<name>.plist` for each.
4. SwiftBar: `brew install --cask swiftbar`, plugin folder `menubar/`.

## Why the calendar helper exists

macOS denies Calendar access to `ekctl` when it runs as a child of bash or python under launchd. `collect.py` falls back to kickstarting `local.cockpit.calendar`, which runs `ekctl` directly and writes `data/agenda.json`.

## Not in the repo

`config.json`, `config.json.bak`, `data/`, `out/` (except the icon) and `logs/`. They hold client names, issue titles and personal calendar data.
