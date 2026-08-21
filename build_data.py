#!/usr/bin/env python3
"""
Build the data payload for the FPL decision dashboard.

Pulls live data from the official Fantasy Premier League API, runs the
projection model, and writes data.json. The dashboard reads that file, so
every run leaves a dated snapshot of exactly what the model saw.
"""
import json, math, os, sys, urllib.request, datetime, zoneinfo
from collections import defaultdict

API = "https://fantasy.premierleague.com/api"
LONDON = zoneinfo.ZoneInfo("Europe/London")
HERE = os.path.dirname(os.path.abspath(__file__))

# The 15 currently in the squad, as (web_name, team short_name).
# Update this list when a transfer is made.
SQUAD = [
    ("Raya", "ARS"), ("Verbruggen", "BHA"),
    ("Gabriel", "ARS"), ("Calafiori", "ARS"), ("Wieffer", "BHA"),
    ("Ballard", "SUN"), ("Sessegnon", "FUL"),
    ("Cherki", "MCI"), ("Mbeumo", "MUN"), ("Enzo", "CHE"),
    ("Damsgaard", "BRE"), ("Gomez", "BHA"),
    ("Haaland", "MCI"), ("João Pedro", "CHE"), ("Beto", "EVE"),
]
CAPTAIN, VICE = "Haaland", "João Pedro"
BENCH_ORDER = ["Verbruggen", "Beto", "Gomez", "Sessegnon"]

HORIZON = 6
POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
ATT_MULT = {1: 1.30, 2: 1.18, 3: 1.00, 4: 0.86, 5: 0.74}
DEF_MULT = {1: 1.35, 2: 1.20, 3: 1.00, 4: 0.82, 5: 0.68}
GOAL_PTS = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
CS_PTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}


def get(path, cache=None):
    if cache and os.path.exists(cache):
        return json.load(open(cache))
    req = urllib.request.Request(f"{API}/{path}", headers={"User-Agent": "fpl-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    if cache:
        json.dump(data, open(cache, "w"))
    return data


def p_at_least(lam, k):
    """Poisson P(X >= k)."""
    if lam <= 0:
        return 0.0
    c, term = 0.0, math.exp(-lam)
    for i in range(k):
        c += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - c)


def cs_prob(xgc90):
    return math.exp(-xgc90) if xgc90 and xgc90 > 0 else 0.22


def build():
    boot = get("bootstrap-static/", os.environ.get("FPL_BOOT_CACHE"))
    fixtures = get("fixtures/", os.environ.get("FPL_FIX_CACHE"))

    teams = {t["id"]: t for t in boot["teams"]}
    tn = {t["id"]: t["short_name"] for t in boot["teams"]}
    tfull = {t["id"]: t["name"] for t in boot["teams"]}

    # ---- gameweek context -------------------------------------------------
    events = boot["events"]
    nxt = next((e for e in events if e.get("is_next")), None) \
        or next((e for e in events if not e["finished"]), events[-1])
    played = sum(1 for e in events if e["finished"])
    deadline = datetime.datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))

    fx_count = defaultdict(int)
    for f in fixtures:
        if f["event"]:
            fx_count[f["event"]] += 1

    # ---- fixture runs per team -------------------------------------------
    runs = defaultdict(list)
    for f in fixtures:
        ev = f["event"]
        if not ev or ev < nxt["id"] or ev >= nxt["id"] + HORIZON:
            continue
        runs[f["team_h"]].append({"gw": ev, "opp": tn[f["team_a"]], "home": True,
                                  "fdr": f["team_h_difficulty"]})
        runs[f["team_a"]].append({"gw": ev, "opp": tn[f["team_h"]], "home": False,
                                  "fdr": f["team_a_difficulty"]})
    for t in runs:
        runs[t].sort(key=lambda x: x["gw"])

    fdr = {}
    for tid in teams:
        g = runs.get(tid, [])
        n = max(len(g), 1)
        fdr[tid] = {
            "games": len(g),
            "avg": round(sum(x["fdr"] for x in g) / n, 2),
            "att": sum(ATT_MULT[x["fdr"]] for x in g) / n,
            "def": sum(DEF_MULT[x["fdr"]] for x in g) / n,
            "run": g,
        }

    # ---- rolling team form (kicks in once results exist) ------------------
    results = [f for f in fixtures if f.get("finished")]
    team_form = {}
    if results:
        recent = defaultdict(list)
        for f in sorted(results, key=lambda x: x["kickoff_time"] or ""):
            recent[f["team_h"]].append((f["team_h_score"], f["team_a_score"]))
            recent[f["team_a"]].append((f["team_a_score"], f["team_h_score"]))
        for tid, gs in recent.items():
            last = gs[-6:]
            if last:
                team_form[tid] = {
                    "played": len(last),
                    "gf": round(sum(a for a, _ in last) / len(last), 2),
                    "ga": round(sum(b for _, b in last) / len(last), 2),
                }

    # ---- player projections ----------------------------------------------
    rows = []
    for e in boot["elements"]:
        if e.get("removed"):
            continue
        p = POS[e["element_type"]]
        mins = e["minutes"]
        n90 = mins / 90 if mins else 0
        tid = e["team"]
        xg90 = float(e["expected_goals_per_90"] or 0)
        xa90 = float(e["expected_assists_per_90"] or 0)
        xgc90 = float(e["expected_goals_conceded_per_90"] or 0)
        dc90 = float(e["defensive_contribution_per_90"] or 0)
        sv90 = float(e["saves_per_90"] or 0)
        starts90 = float(e["starts_per_90"] or 0)

        thresh = 10 if p == "DEF" else 12
        csp = cs_prob(xgc90) if mins > 500 else 0.20
        dcp = p_at_least(dc90, thresh) if mins > 500 else 0.0

        xp90 = 2.0 + xg90 * GOAL_PTS[p] + xa90 * 3
        if p in ("GK", "DEF"):
            xp90 += csp * CS_PTS[p] - (xgc90 / 2) * 0.5
        elif p == "MID":
            xp90 += csp * CS_PTS[p]
        if p == "GK":
            xp90 += sv90 / 3
        else:
            xp90 += dcp * 2
        bps90 = (e["bps"] / n90) if n90 > 3 else 0
        xp90 += min(1.6, max(0.0, (bps90 - 14) / 14))

        ppg90 = (e["total_points"] / n90) if n90 >= 5 else None
        if ppg90 is not None:
            conf = min(1.0, n90 / 25)
            base = 0.55 * xp90 + 0.45 * ppg90
            base = conf * base + (1 - conf) * (0.75 * base)
        else:
            base, conf = xp90 * 0.55, 0.0

        # weight this season in as results accumulate
        w_now = min(0.8, played / 12) if played else 0.0

        if n90 >= 5:
            exp_min = min(1.0, 0.15 + 0.85 * min(1.0, starts90)) * min(1.0, n90 / 30 + 0.35)
        else:
            exp_min = 0.35

        status, chance = e["status"], e["chance_of_playing_next_round"]
        avail = 0.0 if status in ("i", "u", "s") else (chance or 50) / 100 if status == "d" else 1.0
        if chance is not None and status not in ("i", "u", "s"):
            avail = min(avail, chance / 100)

        fm = fdr[tid]
        if p in ("GK", "DEF"):
            fix = 0.35 * fm["att"] + 0.65 * fm["def"]
        elif p == "MID":
            fix = 0.75 * fm["att"] + 0.25 * fm["def"]
        else:
            fix = fm["att"]

        proj_gw = base * fix * exp_min * avail
        rows.append({
            "id": e["id"], "name": e["web_name"],
            "full": f"{e['first_name']} {e['second_name']}".strip(),
            "team": tn[tid], "tid": tid, "pos": p, "price": e["now_cost"] / 10,
            "own": float(e["selected_by_percent"]), "form": float(e["form"] or 0),
            "pts": e["total_points"], "mins": mins,
            "xg90": round(xg90, 2), "xa90": round(xa90, 2),
            "dc90": round(dc90, 1), "csp": round(csp * 100), "dcp": round(dcp * 100),
            "proj": round(proj_gw, 2), "projH": round(proj_gw * fm["games"], 1),
            "ppm": round(proj_gw * fm["games"] / (e["now_cost"] / 10), 2),
            "status": status, "news": e["news"][:120],
            "pen": e["penalties_order"], "sp": e["corners_and_indirect_freekicks_order"],
            "netT": e["transfers_in_event"] - e["transfers_out_event"],
            "fix": round(fix, 2), "wNow": round(w_now, 2),
        })

    by_key = {(r["name"], r["team"]): r for r in rows}

    # ---- squad ------------------------------------------------------------
    squad = []
    for nm, tm in SQUAD:
        r = by_key.get((nm, tm))
        if not r:
            print(f"WARNING: {nm} ({tm}) not found — squad list may be stale", file=sys.stderr)
            continue
        r = dict(r)
        r["captain"] = r["name"] == CAPTAIN
        r["vice"] = r["name"] == VICE
        r["bench"] = BENCH_ORDER.index(r["name"]) if r["name"] in BENCH_ORDER else None
        r["run"] = fdr[r["tid"]]["run"]
        squad.append(r)

    squad_ids = {r["id"] for r in squad}
    xi = [r for r in squad if r["bench"] is None]
    bench = sorted([r for r in squad if r["bench"] is not None], key=lambda r: r["bench"])
    shape = f"{sum(1 for r in xi if r['pos']=='DEF')}-{sum(1 for r in xi if r['pos']=='MID')}-{sum(1 for r in xi if r['pos']=='FWD')}"

    # ---- watchlist: best alternatives not already owned --------------------
    pool = [r for r in rows if r["id"] not in squad_ids and r["status"] == "a"
            and (r["mins"] >= 600 or r["price"] <= 4.5)]
    watch = {}
    for p in ("GK", "DEF", "MID", "FWD"):
        watch[p] = sorted([r for r in pool if r["pos"] == p],
                          key=lambda r: -r["projH"])[:6]

    # ---- team table -------------------------------------------------------
    table = []
    for tid, t in teams.items():
        fm = fdr[tid]
        table.append({
            "team": tn[tid], "name": tfull[tid], "fdr": fm["avg"],
            "run": fm["run"], "form": team_form.get(tid),
            "owned": sorted({r["name"] for r in squad if r["tid"] == tid}),
        })
    table.sort(key=lambda x: x["fdr"])

    decisions = []
    dpath = os.path.join(HERE, "decisions.json")
    if os.path.exists(dpath):
        decisions = json.load(open(dpath))
    decisions.sort(key=lambda d: (d["gw"], d["date"]), reverse=True)

    payload = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "generatedUK": datetime.datetime.now(LONDON).strftime("%a %-d %b %Y, %H:%M %Z"),
        "stamp": datetime.datetime.now(LONDON).strftime("%-d %b · %H:%M"),
        "gw": nxt["id"],
        "deadline": nxt["deadline_time"],
        "deadlineUK": deadline.astimezone(LONDON).strftime("%a %-d %b, %H:%M %Z"),
        "gwPlayed": played,
        "horizon": HORIZON,
        "seasonWeight": round(min(0.8, played / 12) if played else 0.0, 2),
        "fixtureCounts": {str(k): v for k, v in sorted(fx_count.items())},
        "shape": shape,
        "captain": CAPTAIN, "vice": VICE,
        "squadValue": round(sum(r["price"] for r in squad), 1),
        "xiProj": round(sum(r["proj"] for r in xi), 1),
        "squad": squad, "xi": xi, "bench": bench,
        "watch": watch, "table": table, "log": decisions,
        "calendar": [{
            "gw": e["id"],
            "deadline": e["deadline_time"],
            "uk": datetime.datetime.fromisoformat(e["deadline_time"].replace("Z", "+00:00"))
                 .astimezone(LONDON).strftime("%a %-d %b · %H:%M"),
            "fixtures": fx_count.get(e["id"], 0),
            "half": 1 if e["id"] <= 19 else 2,
        } for e in events],
    }

    out = os.path.join(HERE, "data.json")
    json.dump(payload, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB)  GW{payload['gw']}  "
          f"deadline {payload['deadlineUK']}  squad £{payload['squadValue']}m")
    return payload


if __name__ == "__main__":
    build()
