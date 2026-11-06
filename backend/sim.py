"""Stellavex mission simulation (Python port of the game's JavaScript engine).

The same design, mission, difficulty, upgrades, seed and in-flight decisions give exactly the same
result as the game in the browser, so scores can be verified on the server.
Data comes from data/game-data.json (exported from the game).
"""
import json
import math
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "data" / "game-data.json").read_text(encoding="utf-8"))
G0 = DATA["g0"]
BY = {k: {x["id"]: x for x in DATA[k]} for k in ("rockets", "buses", "payloads", "power", "batteries", "antennas", "orbits", "windows")}
STAGES = [("launch", "Launch"), ("transfer", "Transfer"), ("orbit", "Orbit"), ("landing", "Landing")]
# design field -> (data table, default id). Missing fields use the first entry, like the game.
FIELDS = {"w": "power", "y": "batteries", "a": "antennas", "o": "orbits", "l": "windows"}


class DesignError(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def js_round(x):
    """JavaScript's Math.round (half rounds up), so results match the browser."""
    return math.floor(x + 0.5)


def _imul(a, b):
    return (a * b) & 0xFFFFFFFF


def mulberry32(seed):
    """The same random generator the game uses."""
    a = seed & 0xFFFFFFFF

    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rnd


def setup(mission, difficulty="standard", upgrades=()):
    if mission not in DATA["missions"]:
        raise DesignError(["Unknown mission."])
    difficulty = str(difficulty).lower()
    if difficulty not in DATA["difficulty"]:
        raise DesignError(["Unknown difficulty."])
    ups = {u for u in upgrades if u in {x["id"] for x in DATA["upgrades"]}}
    base, df = DATA["missions"][mission], DATA["difficulty"][difficulty]
    m = dict(base)
    m["bud"] = js_round(base["bud"] * df["b"]) + (30 if "bud" in ups else 0)
    m["ev"] = [min(x * df["e"], 0.9) for x in base["ev"]]
    rl = df["r"] * (1.02 if "rel" in ups else 1)
    return m, df, rl, ups


def evaluate(d, m, ups):
    """Validate a design and compute cost, weight, power, data and delta-v. Raises DesignError if invalid."""
    errors = []
    r, b0 = BY["rockets"].get(d.get("r")), BY["buses"].get(d.get("b"))
    t = next((x for x in m["tr"] if x["id"] == d.get("t")), None)
    ids = list(dict.fromkeys(d.get("p", [])))
    if not r:
        errors.append("Unknown rocket.")
    if not b0:
        errors.append("Unknown spacecraft.")
    if not t:
        errors.append("Unknown route.")
    if any(i not in BY["payloads"] for i in ids):
        errors.append("Unknown instrument.")
    sub = {}
    for key, table in FIELDS.items():
        want = d.get(key)
        if want is None:
            sub[key] = DATA[table][0]
        elif want in BY[table]:
            sub[key] = BY[table][want]
        else:
            errors.append("Unknown option for %s." % table)
    if errors:
        raise DesignError(errors)
    pw, bt, an, ob, lw = (sub[k] for k in ("w", "y", "a", "o", "l"))
    fuel = float(d.get("f", 0))
    if fuel < 0 or fuel > b0["max"]:
        errors.append("Fuel must be between 0 and %d kg for this craft." % b0["max"])
    b = dict(b0, dry=b0["dry"] * (0.94 if "mass" in ups else 1), isp=b0["isp"] * (1.04 if "isp" in ups else 1))
    p = [x for x in DATA["payloads"] if x["id"] in ids]  # game order
    pm = sum(x["m"] for x in p)
    sub_mass = pw["m"] + bt["m"] + an["m"]
    lm = pm + sub_mass + b["dry"] + fuel
    cost = r["c"] + b["c"] + pw["c"] + bt["c"] + an["c"] + sum(x["c"] for x in p) + fuel / 1000 * 1.5
    me = pm + sub_mass + b["dry"]
    dv = b["isp"] * G0 * math.log((me + fuel) / me) if fuel > 0 else 0.0
    if pm > m["plim"]:
        errors.append("Instruments weigh over %d kg." % m["plim"])
    if lm > r["cap"]:
        errors.append("Too heavy for this rocket to lift.")
    if cost > m["bud"]:
        errors.append("Over budget.")
    if errors:
        raise DesignError(errors)
    power = pw["w"] if pw.get("w") else pw["area"] * m["irr"] * 0.28 * 0.45
    demand = 25 + sum(x["pw"] for x in p) + an["pw"]
    bf = 1 if pw.get("w") else 0.7 + 0.3 * min(1, bt["wh"] / (demand * 8))
    pwr = min(1, power / demand) * bf
    rate = an["k"] * min(100, 1 / (m["dau"] * m["dau"]))
    cap = rate * 14400 / 8 / 1000 * (2 if "relay" in ids else 1)
    gen = sum(x["dt"] for x in p if x["pts"])
    cr = min(1, cap / gen) if gen else 1
    return {"r": r, "b": b, "t": t, "p": p, "pw": pw, "bt": bt, "an": an, "ob": ob, "lw": lw, "pm": pm, "lm": lm, "cost": cost, "dv": dv,
            "req": t["dv"] + lw["dv"] + m["o"] * ob["dvm"] + m["l"], "P": power, "D": demand, "bf": bf, "pwr": pwr, "cap": cap, "gen": gen, "cr": cr}


def _ask(aid, text, opts):
    c = yield {"type": "ask", "id": aid, "text": text, "opts": opts}
    return c if any(o["id"] == c for o in opts) else opts[0]["id"]


def sim_gen(design, seed, mission="mars", difficulty="standard", upgrades=()):
    """Runs the mission as a generator. Yields {'type':'ask'} for decisions and {'type':'stage'} per stage."""
    m, df, rl, ups = setup(mission, difficulty, upgrades)
    s = evaluate(design, m, ups)
    rnd = mulberry32(int(seed))
    r, b, t, lw, ob, ids = s["r"], s["b"], s["t"], s["lw"], s["ob"], list(design.get("p", []))
    pool = s["dv"]
    tot = max(pool, 1.0)
    dmg, mult, fail, st = [], 1.0, False, []
    extra_t, dust, lrel = 0, False, 1.0
    any_pts = any(x["pts"] for x in s["p"])
    orbit_name = {"moon": "lunar", "mars": "Mars", "europa": "Europa"}.get(mission, "asteroid")

    for si, (sid, sname) in enumerate(STAGES):
        o = {"id": sid, "n": sname, "ok": False, "ev": [], "det": "Not reached."}
        st.append(o)
        if not fail:
            def burn(need, ok_text):
                nonlocal pool
                if pool >= need:
                    pool -= need
                    o["ok"] = True
                    o["det"] = "%s %d m/s left." % (ok_text, js_round(pool))
                else:
                    o["det"] = "Short by %d m/s of delta-v." % js_round(need - pool)
                    pool = 0.0

            if sid == "launch":
                if lw["scrub"] and rnd() < min(lw["scrub"] * df["e"], 0.9):
                    o["ev"].append("Launch scrubbed by weather.")
                    c = yield from _ask("scrub", "The launch was scrubbed by weather. What now?", [
                        {"id": "wait", "t": "Wait for the next opportunity (transfer needs 300 m/s more)"},
                        {"id": "go", "t": "Launch now in poor weather (launch reliability -8%)"}])
                    if c == "wait":
                        extra_t = 300
                    else:
                        lrel = 0.92
                o["ok"] = rnd() < r["rel"] * rl * lrel
                o["det"] = "Liftoff. Orbit reached." if o["ok"] else "The %s failed during ascent." % r["n"]
            elif sid == "transfer":
                if rnd() < m["ev"][0]:
                    c = yield from _ask("engine", "An engine is underperforming. How do you respond?", [
                        {"id": "accept", "t": "Accept the shortfall (lose 8% of delta-v)"},
                        {"id": "divert", "t": "Divert power to the engine (lose 3% of delta-v, science -10%)"}])
                    if c == "accept":
                        pool *= 0.92
                        o["ev"].append("Engine underperformed: lost 8% of delta-v.")
                    else:
                        pool *= 0.97
                        mult *= 0.9
                        o["ev"].append("Engine underperformed: power diverted, lost 3% of delta-v and 10% of science.")
                if rnd() < m["ev"][1] * min(t["days"] / 260, 1) and "shield" not in ids and any_pts:
                    c = yield from _ask("flare", "A solar flare is heading for your spacecraft. What do you do?", [
                        {"id": "ride", "t": "Ride it out (an instrument may be damaged)"},
                        {"id": "safe", "t": "Enter safe mode (no damage, lose 3% of delta-v)"}])
                    if c == "ride":
                        q = [x for x in s["p"] if x["pts"]]
                        dmg.append(q[math.floor(rnd() * len(q))]["id"])
                        o["ev"].append("Solar flare damaged an instrument.")
                    else:
                        pool *= 0.97
                        o["ev"].append("Safe mode protected the instruments: lost 3% of delta-v.")
                if rnd() < m["ev"][4] and "shield" not in ids and any_pts:
                    c = yield from _ask("rock", "An asteroid is on a collision course. What do you do?", [
                        {"id": "accept", "t": "Accept the risk (an instrument may be damaged)"},
                        {"id": "evade", "t": "Evade with thrusters (lose 5% of delta-v)"}])
                    if c == "accept":
                        q = [x for x in s["p"] if x["pts"]]
                        dmg.append(q[math.floor(rnd() * len(q))]["id"])
                        o["ev"].append("A small asteroid struck the craft and damaged an instrument.")
                    else:
                        pool *= 0.95
                        o["ev"].append("You dodged the asteroid but used 5% of your delta-v.")
                if rnd() < m["ev"][5]:
                    pool *= 0.94
                    o["ev"].append("Fuel leak: lost 6% of your delta-v.")
                if rnd() < m["ev"][8] and "shield" not in ids:
                    mult *= 0.9
                    o["ev"].append("Micrometeoroids pitted an instrument: science return drops 10%.")
                burn(t["dv"] + lw["dv"] + extra_t, "Burn complete.")
            elif sid == "orbit":
                if rnd() < m["ev"][2] and "relay" not in ids:
                    c = yield from _ask("blackout", "Radio contact is lost during orbit insertion. What do you do?", [
                        {"id": "wait", "t": "Wait it out (science -25%)"},
                        {"id": "backup", "t": "Switch to the backup link (science -10%, lose 2% of delta-v)"}])
                    if c == "wait":
                        mult *= 0.75
                        o["ev"].append("Signal blackout: science return drops 25%.")
                    else:
                        mult *= 0.9
                        pool *= 0.98
                        o["ev"].append("Backup link restored contact: science -10%, lost 2% of delta-v.")
                if rnd() >= b["rel"] * rl:
                    o["det"] = "Engine failed to restart for orbit insertion."
                else:
                    gl = 0
                    if rnd() < m["ev"][6]:
                        g0v = 40 if "navcam" in ids else 120
                        c = yield from _ask("guide", "A guidance glitch is pushing you off course.", [
                            {"id": "fix", "t": "Fix it with spare fuel (costs %d m/s)" % g0v},
                            {"id": "upload", "t": "Upload new software (costs %d m/s, science -5%%)" % (g0v // 2)}])
                        if c == "fix":
                            gl = g0v
                            o["ev"].append("Guidance glitch: a course fix cost %d m/s." % gl)
                        else:
                            gl = g0v // 2
                            mult *= 0.95
                            o["ev"].append("Guidance glitch: a software fix cost %d m/s and 5%% of science." % gl)
                    burn(m["o"] * ob["dvm"] + gl, "In %s orbit." % orbit_name)
            else:
                need = m["l"]
                if m["ev"][3] and rnd() < m["ev"][3]:
                    dust = True
                    c = yield from _ask("dust", "A dust storm is blowing over the landing site.", [
                        {"id": "land", "t": "Land now (needs 150 m/s more)"},
                        {"id": "wait", "t": "Wait in orbit for it to pass (lose 2% of delta-v, science -5%)"}])
                    if c == "land":
                        need += 150
                        o["ev"].append("Dust storm: landing needs 150 m/s more.")
                    else:
                        pool *= 0.98
                        mult *= 0.95
                        o["ev"].append("You waited out the dust storm: lost 2% of delta-v and 5% of science.")
                if rnd() < m["ev"][7]:
                    bd = 40 if "navcam" in ids else 120
                    c = yield from _ask("boulder", "Your cameras spot a boulder field at the landing site.", [
                        {"id": "land", "t": "Land anyway (costs %d m/s)" % bd},
                        {"id": "divert", "t": "Divert to a safer spot (costs %d m/s, science -10%%)" % (bd // 2)}])
                    if c == "land":
                        need += bd
                        o["ev"].append("Boulder field: dodging boulders cost %d m/s." % bd)
                    else:
                        need += bd // 2
                        mult *= 0.9
                        o["ev"].append("You diverted around the boulders: cost %d m/s and 10%% of science." % (bd // 2))
                burn(need, "Touchdown on %s." % m["n"])
            if not o["ok"]:
                fail = True
        yield {"type": "stage", "i": si, "o": o}

    landed = st[3]["ok"]
    done = sum(1 for x in st if x["ok"])
    work = set()
    if landed:
        for x in s["p"]:
            if x["pts"] and x["id"] not in dmg and rnd() < x["rel"] * rl:
                work.add(x["t"])
    gg = [g for g in DATA["goals"] if g[0] in m["g"]]
    lab = m.get("lab") or {}
    goals = [{"n": lab.get(g[0], g[1]), "p": g[2], "ok": g[0] in work} for g in gg]
    mx = sum(g[2] for g in gg)
    pwr = min(1, s["P"] * 0.5 / s["D"]) * s["bf"] if dust and not s["pw"].get("w") else s["pwr"]
    sci = sum(g["p"] for g in goals if g["ok"]) / mx * mult * pwr * (0.3 + 0.7 * s["cr"]) * ob["sci"]
    suc = done / 4
    eff = ((m["bud"] - s["cost"]) / m["bud"] + min(pool / tot, 1.0)) / 2 * suc
    score = js_round(100 * (0.4 * suc + 0.3 * sci + 0.3 * eff))
    return {
        "seed": int(seed), "mission": mission, "difficulty": str(difficulty).lower(), "score": score, "landed": landed,
        "breakdown": {"mission_success": round(suc, 3), "science_return": round(sci, 3), "resource_efficiency": round(eff, 3)},
        "power": {"supply_w": round(s["P"], 1), "demand_w": round(s["D"], 1), "ratio": round(pwr, 3)},
        "comms": {"mb_per_day": round(s["cap"], 2), "generated_mb": s["gen"], "ratio": round(s["cr"], 3)},
        "stages": st, "science_goals": goals,
        "design": {"cost_musd": round(s["cost"], 1), "launch_mass_kg": round(s["lm"]), "delta_v_ms": round(s["dv"]), "required_delta_v_ms": round(s["req"])},
        "_ratios": {"power": pwr, "comms": s["cr"]},
    }


def simulate(design, seed, mission="mars", difficulty="standard", upgrades=(), choices=()):
    """Run a whole mission. `choices` are the in-flight decisions in the order they were asked."""
    g = sim_gen(design, seed, mission, difficulty, upgrades)
    ci = 0
    try:
        msg = next(g)
        while True:
            if msg["type"] == "ask":
                c = choices[ci] if ci < len(choices) else None
                ci += 1
                msg = g.send(c)
            else:
                msg = g.send(None)
    except StopIteration as stop:
        res = stop.value
        res["choices_used"] = min(ci, len(choices))
        return res
