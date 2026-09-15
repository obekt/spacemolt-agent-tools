#!/usr/bin/env python3
"""Whale poller: while DOCKED, watch the freight board and log big postings.

  python3 board_poll.py <min_cr> [max_minutes]   # defaults 3000 cr / 20 min

The freight/pax boards rotate roughly every 100 game ticks. Instead of flying
hub-to-hub hunting, park at a station whose board has just minted rich
postings and wait: a rich board regenerates rich postings inside its window.
Idling cheaply where whales live beats flying to hunt them.

Design notes:
  * Queries only (free, un-rate-limited) — it never accepts anything.
    The accept decision belongs to the operator/agent session.
  * Silent while dry: the log file appears on the FIRST hit. Missing file
    means "still dry", not "poller broken".
  * Pair with a pattern-notify on "HIT" if running under an agent runner.
  * Fare-racing caveat at crowded hubs: by the time a human/agent wakeup
    round-trip completes, a big fare may be gone. Treat "no waiting
    passengers" on a fresh hit as raced, not broken.
"""
import sys
import time

from spacemolt_client import call

LOG = "board_poll.log"


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def main() -> None:
    min_cr = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    max_min = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    t0 = time.time()
    seen = set()
    while time.time() - t0 < max_min * 60:
        try:
            sc = call("spacemolt_shipping", "list", {}, mutate=False).get("sc") or {}
            shipments = sc.get("shipments") or []
            for s in shipments:
                c = s.get("contract", {})
                rew = c.get("base_reward", 0)
                if rew >= min_cr and c.get("id") not in seen:
                    seen.add(c.get("id"))
                    log(f"HIT {rew}cr | {c.get('origin_base_id')} -> "
                        f"{c.get('destination_base_id')} | hops {c.get('route_hops')} "
                        f"| id {c.get('id')}")
            if not shipments:
                log("board empty")
        except Exception as e:  # keep polling through transient failures
            log(f"err {e}")
        time.sleep(90)
    log("poll done")


if __name__ == "__main__":
    main()
