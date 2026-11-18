#!/usr/bin/env python3


import re
import sys
import time
import random
import requests

# ============================ CONFIG ============================

BANNER_BASE = "https://studentregistration.ku.ac.ae/StudentRegistrationSsb"
TERM = "202620"          # Spring 2027

# CRNs to watch. Add more like: ["20009", "20010"]
CRNS = ["20009"]         # AERO 225-02 Mechanics of Solids

NTFY_TOPIC = "s-ku-aero-8241"   # same topic you subscribe to in ntfy
CHECK_EVERY_SECONDS = 180             # 3 min; please don't go much lower

# Alert every time seats go UP (someone dropped), not only when going 0 -> open
ALERT_ON_ANY_INCREASE = True

# ================================================================

UA = {"User-Agent": "Mozilla/5.0 (personal seat watcher)"}
REGISTER_URL = f"{BANNER_BASE}/ssb/registration"


def notify(title, message):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": "high",
                     "Tags": "rotating_light", "Click": REGISTER_URL},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"[!] Notification failed: {e}")


def page_text(s, endpoint, crn):
    r = s.get(f"{BANNER_BASE}/ssb/searchResults/{endpoint}",
              params={"term": TERM, "courseReferenceNumber": crn}, timeout=30)
    r.raise_for_status()
    text = re.sub(r"<[^>]+>", " ", r.text)          # strip HTML tags
    return re.sub(r"\s+", " ", text)


def field(text, label):
    m = re.search(re.escape(label) + r"\s*:?\s*(-?\d+)", text)
    return int(m.group(1)) if m else None


def course_name(s, crn):
    try:
        t = page_text(s, "getClassDetails", crn)
        subj = re.search(r"Subject:\s*(.+?)\s+Course Number", t)
        num = re.search(r"Course Number:\s*(\S+)", t)
        sec = re.search(r"Section Number:\s*(\S+)", t)
        title = re.search(r"Title:\s*(.+?)\s+Credit Hours", t)
        return (f"{subj.group(1)} {num.group(1)}-{sec.group(1)} "
                f"{title.group(1)} (CRN {crn})")
    except Exception:
        return f"CRN {crn}"


def seats(s, crn):
    """Real open seats = the smaller of the section's own seats and the
    shared cross-list seats (e.g. AERO 225 / CIVE 225 / MEEN 325 share one cap)."""
    t = page_text(s, "getEnrollmentInfo", crn)
    avail = field(t, "Enrollment Seats Available")
    if avail is None:
        raise ValueError(f"Couldn't read seats for CRN {crn} (check CRN/term)")
    actual, cap = field(t, "Enrollment Actual"), field(t, "Enrollment Maximum")

    x = page_text(s, "getXlstSections", crn)
    x_avail = field(x, "Cross List Seats Available")
    if x_avail is not None:
        avail = min(avail, x_avail)
        actual, cap = field(x, "Cross List Actual"), field(x, "Cross List Maximum")
    return avail, actual, cap


def main():
    if "--test" in sys.argv:
        notify("Seat watcher test", "If you see this, notifications work ✅")
        print("Test notification sent.")
        return

    s = requests.Session()
    s.headers.update(UA)
    names = {crn: course_name(s, crn) for crn in CRNS}
    last = {}

    print(f"Watching {len(CRNS)} CRN(s) every ~{CHECK_EVERY_SECONDS}s. Ctrl+C to stop.")
    while True:
        for crn in CRNS:
            try:
                avail, actual, cap = seats(s, crn)
            except (requests.RequestException, ValueError) as e:
                print(f"[!] {e}")
                continue
            print(time.strftime("[%H:%M:%S] ") +
                  f"{names[crn]}: {max(avail, 0)} open ({actual}/{cap} enrolled)")

            prev = last.get(crn)
            if prev is None:
                if avail > 0:
                    notify(f"Seats open now: CRN {crn}",
                           f"{names[crn]}\n{avail} seat(s) available right now.")
            elif avail > max(prev, 0) and (ALERT_ON_ANY_INCREASE or prev <= 0):
                notify(f"Someone dropped! CRN {crn}",
                       f"{names[crn]}\nSeats: {max(prev, 0)} → {avail}. Register now!")
            last[crn] = avail
            time.sleep(2)
        time.sleep(CHECK_EVERY_SECONDS + random.randint(0, 30))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
