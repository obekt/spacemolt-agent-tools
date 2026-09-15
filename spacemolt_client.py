#!/usr/bin/env python3
"""SpaceMolt v2 HTTP client with credential loading and a mutation rate gate.

Credentials are read (in order) from:
  1. $SPACEMOLT_USER / $SPACEMOLT_PASS environment variables
  2. a local config file at ~/.config/spacemolt/credentials.json
     {"username": "...", "password": "***"}   (chmod 600 recommended)

Never hardcode your agent password in scripts that you share.

Usage as a CLI:
  python3 spacemolt_client.py q <tool> <action> '<json>'   # query (free)
  python3 spacemolt_client.py m <tool> <action> '<json>'   # mutation (11s gate)
  python3 spacemolt_client.py tick                         # gate countdown

Usage as a library:
  from spacemolt_client import call, brief
  r = call("spacemolt", "get_status", {}, mutate=False)
  print(r["code"], r["sc"].get("player", {}).get("credits"))

Response envelope (every call):
  {"code": int, "result": str, "sc": <structuredContent dict>, "err": ...|None}

Game docs: https://spacemolt.com/skill.md
API base : https://game.spacemolt.com/api/v2
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("SPACEMOLT_BASE", "https://game.spacemolt.com/api/v2")
HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, ".mutation_gate.json")   # persists last mutation time
SID_FILE = os.path.join(HERE, ".session_id")      # cached session id
MUTATION_INTERVAL = 11.0                          # server tick is 10s; 11 avoids races

CONFIG_PATH = os.path.expanduser("~/.config/spacemolt/credentials.json")


def _load_creds():
    user = os.environ.get("SPACEMOLT_USER")
    pw = os.environ.get("SPACEMOLT_PASS")
    if user and pw:
        return user, pw
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            d = json.load(f)
        return d["username"], d["password"]
    sys.exit("No credentials: set $SPACEMOLT_USER/$SPACEMOLT_PASS or create "
            + CONFIG_PATH + ' {"username","password"}')


def _post(path, body, sid=None, timeout=45):
    req = urllib.request.Request(
        BASE + "/" + path.lstrip("/"),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                **({"X-Session-Id": sid} if sid else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode()), e.code
        except Exception:
            return {"error": str(e)}, e.code


def _extract_sid(s: dict) -> str:
    """Session id lives at session.id, sometimes nested under structuredContent."""
    for src in (s.get("structuredContent") or {}, s):
        if not isinstance(src, dict):
            continue
        inner = src.get("session")
        if isinstance(inner, dict) and inner.get("id"):
            return str(inner["id"])
        if src.get("id"):
            return str(src["id"])
    raise RuntimeError("no session id in response: " + json.dumps(s)[:200])


def login() -> str:
    user, pw = _load_creds()
    s, _ = _post("session", {})
    sid = _extract_sid(s)
    r, code = _post("spacemolt_auth/login", {"username": user, "password": pw}, sid)
    if code != 200:
        sys.exit("login failed: " + json.dumps(r)[:300])
    return sid


def get_sid() -> str:
    if os.path.exists(SID_FILE):
        sid = open(SID_FILE).read().strip()
        if sid:
            return sid
    sid = login()
    with open(SID_FILE, "w") as f:
        f.write(sid)
    return sid


def call(tool, action, body, mutate=False, _retried=False):
    """One API call. Mutations respect the 1-per-tick gate via .mutation_gate.json
    so multiple cooperating scripts on one box never collide. 401 re-logins once."""
    sid = get_sid()
    if mutate:
        gate = {}
        if os.path.exists(GATE):
            try:
                gate = json.load(open(GATE))
            except Exception:
                gate = {}
        wait = MUTATION_INTERVAL - (time.time() - gate.get("last", 0))
        if wait > 0:
            time.sleep(wait)
    out, code = _post(f"{tool}/{action}", body, sid)
    if code == 401 and not _retried:
        try:
            os.remove(SID_FILE)
        except OSError:
            pass
        return call(tool, action, body, mutate=mutate, _retried=True)
    if mutate:
        json.dump({"last": time.time()}, open(GATE, "w"))
    sc = out.get("structuredContent") or {}
    return {"code": code,
            "result": (out.get("result") or "")[:600],
            "sc": sc,
            "err": out.get("error") or sc.get("error")}


def brief(x, n=1500):
    return json.dumps(x, ensure_ascii=False, default=str)[:n]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "tick"
    if mode == "tick":
        g = json.load(open(GATE)) if os.path.exists(GATE) else {"last": 0}
        print(f"{MUTATION_INTERVAL - (time.time() - g['last']):.1f}s until next mutation allowed")
    else:
        tool, action = sys.argv[2], sys.argv[3]
        body = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        res = call(tool, action, body, mutate=(mode == "m"))
        with open(os.path.join(HERE, "last_result.json"), "w") as f:
            json.dump(res, f, ensure_ascii=False, default=str)
        print("saved last_result.json | code", res["code"], "| err:", str(res.get("err"))[:200])
        print("result:", res["result"][:300].replace("\n", " | "))
