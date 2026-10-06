# Leuven appointment sniper

Polls the Leuven Qmatic booking API every 5 minutes (GitHub Actions) for a slot before the
deadline (default 15/10/2026). Tries 4 people, then 3, 2, 1, and books automatically.
Sends push notifications through ntfy.sh. Your existing 15/10 appointment is never touched,
so cancel it yourself once everyone is covered.

## Setup
1. Install the **ntfy** app on your phone and subscribe to a long random topic,
   for example `leuven-appt-7f3k9x2q`.
2. Create a GitHub repo and push this folder. A public repo gives unlimited Actions minutes.
3. Repo > Settings > Secrets and variables > Actions, add these secrets:
   `FIRST_NAME`, `LAST_NAME`, `DOB` (DD/MM/YYYY), `EMAIL`, `PHONE` (optional), `NTFY_TOPIC`.
4. Actions tab > run **leuven-appointment-sniper** once with "Run workflow".

## Local testing
```
pip install -r requirements.txt
python snipe.py --check                       # read-only: earliest slot for 1-4 people
NTFY_TOPIC=your-topic python snipe.py --test-notify
DEADLINE=2026-12-31 python snipe.py --dry-run # reserves a slot, then releases it
```

## Notes
- Slot length is 15 minutes per person, which is why a group of 4 has fewer slots.
- If a slot is found but booking is refused, you get an urgent push with the link.
- GitHub cron can run late by several minutes, so very short-lived slots may be missed.
- To stop it: disable the workflow, or it stops by itself once everyone is booked or the deadline passes.
