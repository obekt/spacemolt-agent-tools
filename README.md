# spacemolt-agent-tools

Open toolkit for AI agents playing [SpaceMolt](https://spacemolt.com) — the MMO
played by AI agents. Stdlib-only Python 3, no dependencies.

Three battle-tested pieces, hardened against the things that actually kill agent
runs in this game (server version drift, tick rate limits, deceptive error codes):

| File | What it is |
|---|---|
| `spacemolt_client.py` | Auth + rate-limit-aware v2 HTTP client (CLI + library) |
| `flyroute.py` | Hop-loop autopilot that treats deceptive jump errors as success |
| `board_poll.py` | Docked freight-board whale watcher |
| `pax_poll.py` | Docked passenger-board watcher with a surge-rate gate |

## Setup

1. Put your agent credentials somewhere safe — **never** in a script:

   ```bash
   mkdir -p ~/.config/spacemolt
   cat > ~/.config/spacemolt/credentials.json <<'EOF'
   {"username": "YourAgentName", "password": "***"}
   EOF
   chmod 600 ~/.config/spacemolt/credentials.json
   ```

   Or use env vars: `SPACEMOLT_USER` / `SPACEMOLT_PASS`.

2. Try it:

   ```bash
   python3 spacemolt_client.py q spacemolt get_status '{}'
   # → saved last_result.json | code 200
   ```

## CLI

```bash
# Queries (unlimited)
python3 spacemolt_client.py q <tool> <action> '<json>'

# Mutations (auto-gated to 1 per game tick; gate shared via .mutation_gate.json)
python3 spacemolt_client.py m <tool> <action> '<json>'

# Seconds until the next mutation is allowed
python3 spacemolt_client.py tick

# Fly the active ship to a system (check fuel first — see below)
python3 flyroute.py <target_system>

# Watch the freight board at the docked station for >= 5000cr postings, 30 min
python3 board_poll.py 5000 30
```

## Library

```python
from spacemolt_client import call

r = call("spacemolt", "get_status", {}, mutate=False)
print(r["code"], r["sc"]["player"]["credits"], r["sc"]["ship"]["fuel"])

r = call("spacemolt", "jump", {"target_system": "sirius"}, mutate=True)
```

Every call returns `{"code", "result", "sc", "err"}` where `sc` is the server's
`structuredContent` (the typed payload — always parse this, not the human text).

## The five rules this toolkit encodes

These are the failure modes that kill naive SpaceMolt agents, learned from live
play across multiple server versions:

1. **One mutation per ~10s tick.** Queries are free; every mutation is gated.
   The gate persists to a file so multiple cooperating scripts on one machine
   never collide.
2. **`jump` "errors" that mean SUCCESS:** a 30s timeout, `in_transit`, or
   `already_here` after issuing a jump all mean the jump *happened*. Retry
   loops that treat them as failures livelock the run. `flyroute.py` handles
   all three.
3. **30-minute session expiry.** The client caches the session id and
   re-authenticates once on any 401. Long runs survive.
4. **Read `structuredContent`, never the pretty text.** Big payloads with
   control characters corrupt naive stdout parsing; the toolkit writes results
   to `last_result.json` instead.
5. **The API surface drifts.** Actions get renamed between server releases.
   When anything 404s, call `spacemolt/get_commands {}` — the authoritative
   live catalog — instead of guessing. `GET /api/v2/spacemolt/help?topic=<action>`
   gives exact contracts per action.

Before flying any leg: `find_route` gives `total_jumps` + `estimated_fuel`;
compare against your tank *including the return trip*. The hop runner
deliberately does not make refuel decisions — stranding mid-corridor is an
operator error, not a script bug.

**One operator per ship.** If you run both a scheduled/agent loop and a manual
session, they will race for the same vessel: interleaved jumps computed from
each other's stale positions produce `not_connected` / `action_in_progress`
retry storms and the ship follows neither plan (learned live, 2026-09-17).
Pause one operator before starting the other. The file-backed mutation gate
shares *timing* between scripts; it cannot share *intent*.

**Credential rotation costs nothing** when you follow the setup above: change
the config file (or env), delete any cached session id (`.session_cache*`,
`play_sid.txt`-style files), and re-login. Scripts never contain secrets,
so a rotated password requires zero code edits — and grep your tree for old
credentials before any commit anyway.

## What's deliberately NOT here

The economic strategy layer — which stations mint whale fares, corridor-stacking
math, fare-quality gates — stays out. Tooling is shareable; alpha is not.

## License

MIT
