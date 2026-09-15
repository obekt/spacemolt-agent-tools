#!/usr/bin/env python3
"""Hop-loop autopilot: fly the active ship along find_route to <target_system>.

Jumps one system at a time and treats timeout / in_transit / already_here as
SUCCESS — the jump already happened server-side (verified against live server
drift; these three "errors" are the classic way runs die if you retry them).

  python3 flyroute.py <target_system>

Notes:
  * Safe to start while docked — `jump` auto-undocks.
  * Do NOT issue your own dock/undock/jump while this runs: a competing
    mutation livelocks it on 409 action_in_progress.
  * This runner makes NO refuel decisions. Check remaining_hops * fuel_per_jump
    vs the tank before launching, or you will strand the ship mid-corridor.
  * Progress appends to flyroute.log next to this script.
"""
import json
import sys
import time

from spacemolt_client import call

LOG = "flyroute.log"


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def q(tool: str, action: str, body=None):
    return call(tool, action, body or {}, mutate=False)


def m(tool: str, action: str, body=None):
    return call(tool, action, body or {}, mutate=True)


def where_am_i():
    s = q("spacemolt", "get_status")["sc"]
    loc = s.get("location", {})
    return loc.get("system_id"), loc


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: flyroute.py <target_system>")
    target = sys.argv[1]

    route = q("spacemolt", "find_route", {"target_system": target})["sc"].get("route") or []
    hops = [h["system_id"] for h in route][1:]  # route[0] is current system
    me, _ = where_am_i()
    if me == target:
        log("already there")
        return
    start = hops.index(me) + 1 if me in hops else 0
    log(f"route to {target}: {len(hops[start:])} hops: {hops[start:]}")

    for hop in hops[start:]:
        for attempt in range(6):
            r = m("spacemolt", "jump", {"target_system": hop})
            err = (r.get("err") or {}).get("code") if isinstance(r.get("err"), dict) else r.get("err")
            if r["code"] == 200 or err in ("in_transit", "already_here"):
                break
            # livelock guard: some 400s mean we are actually moving
            me2, _ = where_am_i()
            if me2 == hop:
                break
            log(f"jump {hop} attempt {attempt + 1} err {err}; retry")
        # wait for arrival
        for _ in range(14):
            time.sleep(5)
            me2, _ = where_am_i()
            if me2 == hop:
                break
        fuel = q("spacemolt", "get_status")["sc"].get("ship", {}).get("fuel")
        log(f"arrived {hop} (fuel {fuel})")

    me, _ = where_am_i()
    sysinfo = q("spacemolt", "get_system")["sc"]
    pois = (sysinfo.get("system", {}) or {}).get("pois") or []
    log(f"DONE at {me}; POIs: {[p.get('poi_id') or p.get('id') for p in pois]}")


if __name__ == "__main__":
    main()
