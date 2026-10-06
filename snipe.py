#!/usr/bin/env python3
"""Watch the Leuven Qmatic booking site for an earlier appointment and book it.

Tries a group of 4 first, then 3, 2, 1 (for whatever is still unbooked).
Notifies through ntfy.sh on every booking, failure, or slot it could not book.

Flags: --check (read-only), --test-notify, --dry-run (reserve then release).
"""
import argparse
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE = "https://afspraak.leuven.be/qmaticwebbooking/rest/schedule"
SITE = ("https://afspraak.leuven.be/qmaticwebbooking/#/preselect/services/"
        "b1f4b813c698415d092deff4293eec7d7e649b4116888e28120b03af2e249729?lang=en_GB")
SERVICE = "b1f4b813c698415d092deff4293eec7d7e649b4116888e28120b03af2e249729"
SERVICE_QPID = "52"
SERVICE_NAME = "FOREIGNER Verblijfskaart - aanvraag (niet-Belg)"
BRANCH = "31109068d9785b4c0f07ec342d4040756b1cb8953dd8ba9315f3ab25c560514e"
SLOT_MINUTES = 15  # per person
TZ = ZoneInfo("Europe/Brussels")
STATE_FILE = Path(__file__).with_name("state.json")
MAX_TRIES_PER_GROUP = 5


def env(name, default=None, required=False):
    v = os.environ.get(name, default)
    if required and not v:
        sys.exit(f"Missing required env var {name}")
    return v


def notify(title, message, priority="default", tags=""):
    topic = env("NTFY_TOPIC")
    if not topic:
        print(f"[notify skipped, no NTFY_TOPIC] {title}: {message}")
        return
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority, "Tags": tags, "Click": SITE},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"notify failed: {type(e).__name__}")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"remaining": int(env("PEOPLE", "4")), "bookings": [], "notified": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def normalise_dob(raw):
    raw = raw.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    sys.exit("DOB must look like DD/MM/YYYY or YYYY-MM-DD")


class Qmatic:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["Accept"] = "application/json"
        self.token = self.s.get(f"{BASE}/configuration", timeout=20).json()["token"]

    def _get(self, path):
        r = self.s.get(BASE + path, timeout=20)
        r.raise_for_status()
        return r.json()

    def dates(self, n):
        return [d["date"] for d in self._get(
            f"/branches/{BRANCH}/dates;servicePublicId={SERVICE};customSlotLength={SLOT_MINUTES * n}")]

    def times(self, day, n):
        return [t["time"] for t in self._get(
            f"/branches/{BRANCH}/dates/{day}/times;servicePublicId={SERVICE};customSlotLength={SLOT_MINUTES * n}")]

    def _post(self, path, body):
        r = self.s.post(BASE + path, data=json.dumps(body), timeout=30, headers={
            "Content-Type": "application/json", "X-CSRF-Token": self.token})
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _people(n):
        return [{"publicId": SERVICE, "qpId": SERVICE_QPID, "adult": n,
                 "name": SERVICE_NAME, "child": 0}]

    def reserve(self, day, time, n):
        body = {"services": [{"publicId": SERVICE} for _ in range(n)],
                "custom": json.dumps({"peopleServices": self._people(n)})}
        return self._post(
            f"/branches/{BRANCH}/dates/{day}/times/{time}/reserve;customSlotLength={SLOT_MINUTES * n}", body)

    def release(self, reservation_id):
        try:
            self.s.delete(f"{BASE}/appointments/reserved/{reservation_id}", timeout=20,
                          headers={"X-CSRF-Token": self.token})
        except requests.RequestException:
            pass

    def confirm(self, reservation_id, n, who):
        body = {
            "customer": {
                "firstName": who["first"], "lastName": who["last"],
                "dateOfBirth": who["dob"], "email": who["email"], "phone": who["phone"],
                "allowOverwrite": False, "custom": "{}",
            },
            "languageCode": "en", "countryCode": "GB", "notificationType": "both", "captcha": "",
            "custom": json.dumps({
                "peopleServices": self._people(n), "totalCost": 0,
                "createdByUser": "Qmatic Web Booking", "customSlotLength": SLOT_MINUTES * n,
            }),
            "notes": "", "title": "Qmatic Web Booking",
        }
        return self._post(f"/appointments/{reservation_id}/confirm", body)


def candidate_slots(q, n, deadline, lead_minutes):
    """Yield (date, time) before the deadline, earliest first, respecting lead time."""
    now = datetime.now(TZ)
    for day in q.dates(n):
        if date.fromisoformat(day) >= deadline:
            return
        for t in q.times(day, n):
            start = datetime.fromisoformat(f"{day}T{t}").replace(tzinfo=TZ)
            if (start - now).total_seconds() >= lead_minutes * 60:
                yield day, t


def who_from_env():
    return {
        "first": env("FIRST_NAME", required=True),
        "last": env("LAST_NAME", required=True),
        "dob": normalise_dob(env("DOB", required=True)),
        "email": env("EMAIL", required=True),
        "phone": env("PHONE", ""),
    }


def cmd_check(q, deadline):
    print(f"Deadline: before {deadline}")
    for n in (4, 3, 2, 1):
        first = next(candidate_slots(q, n, date(2999, 1, 1), 0), None)
        flag = "  <-- BEFORE DEADLINE" if first and date.fromisoformat(first[0]) < deadline else ""
        print(f"{n} people: earliest {first}{flag}")


def run_notify_only(q, deadline, lead):
    """Push the earliest slot before the deadline for each group size; never book."""
    state = load_state()
    state.setdefault("notified", [])
    if date.today() >= deadline:
        print("Deadline passed. Nothing to do.")
        return
    found = []
    for n in (4, 3, 2, 1):
        slot = next(candidate_slots(q, n, deadline, lead), None)
        if slot:
            found.append((n, slot[0], slot[1]))
    fresh = [f for f in found if f"{f[0]}:{f[1]}:{f[2]}" not in state["notified"]]
    if not fresh:
        print("No new slot before the deadline." if not found else "Slots exist but already notified.")
        return
    lines = [f"{n} people: {d} {t}" for n, d, t in found]
    notify("EARLIER APPOINTMENT AVAILABLE", "\n".join(lines) + f"\nBook now: {SITE}",
           priority="urgent", tags="rotating_light")
    state["notified"] += [f"{n}:{d}:{t}" for n, d, t in fresh]
    save_state(state)
    print("Notified:", "; ".join(lines))


def run(q, dry_run, deadline, lead):
    state = load_state()
    state.setdefault("notified", [])
    if state["remaining"] <= 0:
        print("All people already booked. Nothing to do.")
        return
    if date.today() >= deadline:
        print("Deadline passed. Nothing to do.")
        return
    who = None if dry_run else who_from_env()

    for n in range(min(4, state["remaining"]), 0, -1):
        tries = 0
        for day, t in candidate_slots(q, n, deadline, lead):
            tries += 1
            if tries > MAX_TRIES_PER_GROUP:
                break
            print(f"Group of {n}: trying {day} {t}")
            try:
                res = q.reserve(day, t, n)
            except requests.RequestException as e:
                print(f"  reserve failed: {e}")
                continue
            rid = res.get("publicId")
            if dry_run:
                print(f"  DRY RUN: reserved ok (id {rid}); releasing.")
                q.release(rid)
                return
            try:
                done = q.confirm(rid, n, who)
            except requests.RequestException as e:
                q.release(rid)
                key = f"{n}:{day}:{t}"
                body = getattr(getattr(e, "response", None), "text", "")[:200]
                print(f"  confirm failed: {e} {body}")
                if key not in state["notified"]:
                    state["notified"].append(key)
                    save_state(state)
                    notify("Slot found but booking FAILED",
                           f"{n} people, {day} {t}. Book by hand NOW: {SITE}",
                           priority="urgent", tags="warning")
                continue
            state["remaining"] -= n
            state["bookings"].append({"people": n, "date": day, "time": t,
                                      "id": done.get("publicId", rid)})
            save_state(state)
            left = state["remaining"]
            notify("Appointment BOOKED",
                   f"{n} people on {day} {t}. Still unbooked: {left}. "
                   f"Check your email. Keep the 15/10 booking until everyone is covered.",
                   priority="high", tags="tada")
            print(f"  BOOKED {n} people on {day} {t}; remaining {left}")
            if left > 0:
                return run(q, dry_run, deadline, lead)
            return
    print("No bookable slot before the deadline.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--test-notify", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    deadline = date.fromisoformat(env("DEADLINE", "2026-10-15"))
    lead = int(env("MIN_LEAD_MINUTES", "30"))

    if a.test_notify:
        notify("Leuven sniper test", "Notifications work.", tags="white_check_mark")
        return
    try:
        q = Qmatic()
        if a.check:
            cmd_check(q, deadline)
        elif env("BOOK") == "1" or a.dry_run:
            run(q, a.dry_run, deadline, lead)
        else:
            run_notify_only(q, deadline, lead)
    except requests.RequestException as e:
        print(f"Network/API error: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
