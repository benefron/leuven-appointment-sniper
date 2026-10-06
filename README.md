# Leuven appointment sniper

Polls the Leuven Qmatic booking API every 5 minutes and sends a push (ntfy.sh) when a slot
before the deadline (default 15/10/2026) appears, listing the earliest slot for 4, 3, 2 and 1
people. You book it yourself. Each slot is only announced once. Auto-booking exists but is off
unless `BOOK=1` and your details are set in `.env`.

It runs on your Mac through launchd, whenever the Mac is awake. (GitHub Actions does not
work: the Leuven site drops connections from GitHub's servers.)

## Setup
1. Install the **ntfy** app and subscribe to the topic in `.env` (`NTFY_TOPIC`).
2. `.env` only needs `NTFY_TOPIC` (already set).
3. Run `./install.sh`. It checks `.env`, installs the launchd job and starts it.
4. Watch `snipe.log`. A healthy pass ends with "No bookable slot before the deadline."

Stop it with `./uninstall.sh`. It also stops by itself once everyone is booked or the
deadline passes.

## Manual commands
```
.venv/bin/python snipe.py --check          # read-only: earliest slot for 1-4 people
set -a; source .env; set +a; .venv/bin/python snipe.py --test-notify
DEADLINE=2026-12-31 .venv/bin/python snipe.py --dry-run   # reserves a slot, then releases it
```

## Notes
- Slot length is 15 minutes per person; children count as people (no separate child service).
- If a slot is found but booking is refused, you get an urgent push with the link.
- While the Mac sleeps nothing runs; one pass runs right after wake. To keep it awake while
  plugged in: `caffeinate -s` in a terminal, or System Settings > Battery > prevent sleep.
- `.env`, `state.json` and `snipe.log` are git-ignored.
