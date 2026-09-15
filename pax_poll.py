#!/usr/bin/env python3
"""While docked, poll the PASSENGER board and log fares >= MIN with surge >= MINSURGE.

  python3 pax_poll.py <min_cr> [min_surge] [max_minutes]   # defaults 5000 / 1.0 / 30

Companion to board_poll.py (which watches freight). High-surge boards mint
fares at 1.5-2x base; at a surging empire hub the next rotation is worth
waiting for instead of rotating hubs (idle at a station costs fuel nothing).
Logs only hits — silent while dry. Never accepts; operator decides.
"""
import sys
import time

from spacemolt_client import call

LOG = "pax_poll.log"


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def main():
    min_cr = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    min_surge = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    max_min = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    t0 = time.time()
    seen = set()
    while time.time() - t0 < max_min * 60:
        try:
            sc = call("spacemolt", "list_station_passengers", {}, mutate=False).get("sc") or {}
            surge = sc.get("fare_surge") or 0
            for x in sc.get("waiting") or []:
                fare = x.get("estimated_fare") or 0
                key = f"{x.get('name')}:{x.get('destination')}"
                if fare >= min_cr and surge >= min_surge and key not in seen:
                    seen.add(key)
                    log(f"HIT {fare}cr {x.get('class')} surge={surge:.1f} -> "
                        f"{x.get('destination_name')} ({x.get('destination_system')}) "
                        f"id {x.get('destination')}")
        except Exception as e:
            log(f"err {e}")
        time.sleep(60)
    log("pax poll done")


if __name__ == "__main__":
    main()
