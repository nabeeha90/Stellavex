
from fastapi.middleware.cors import CORSMiddleware
"""Stellavex API and web server.

Run from the project root:   python run.py
Endpoints: /api/health, /api/catalog, /api/simulate, /api/scores (POST), /api/leaderboard, /api/stats
Scores are verified: the server re-runs the mission with the submitted design and seed,
including every in-flight decision, so the posted score always comes from the real simulation, never from the client.
"""
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db
import sim

app = FastAPI(title="Stellavex Mission Control")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)
db.init()


class Design(BaseModel):
    r: str = Field(max_length=20)                       # rocket
    b: str = Field(max_length=20)                       # spacecraft
    f: float = Field(ge=0, le=100000)                   # fuel (kg)
    p: list[str] = Field(default_factory=list, max_length=12)  # instruments
    t: str = Field(max_length=20)                       # route
    w: str = Field(default="solar_s", max_length=20)    # power source
    y: str = Field(default="bat_none", max_length=20)   # battery
    a: str = Field(default="lga", max_length=20)        # antenna
    o: str = Field(default="low", max_length=20)        # arrival orbit
    l: str = Field(default="opt", max_length=20)        # launch window


class SimRequest(BaseModel):
    design: Design
    mission: str = "mars"
    difficulty: str = "standard"
    upgrades: list[str] = Field(default_factory=list, max_length=8)
    seed: int | None = Field(default=None, ge=1, lt=2**32)
    choices: list[str] = Field(default_factory=list, max_length=40)  # in-flight decisions, in order


class ScoreRequest(BaseModel):
    name: str = Field(default="Pilot", max_length=40)
    player_id: str = Field(min_length=6, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    mission: str = "mars"
    difficulty: str = "standard"
    upgrades: list[str] = Field(default_factory=list, max_length=8)
    seed: int = Field(ge=1, lt=2**32)
    design: Design
    choices: list[str] = Field(default_factory=list, max_length=40)


_hits = defaultdict(deque)
_cache = {}


def limited(ip, n=20, per=60):
    """At most n score posts per minute per address."""
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > per:
        q.popleft()
    if len(q) >= n:
        return True
    q.append(now)
    return False


def run(design, seed, mission, difficulty, upgrades, choices=()):
    try:
        res = sim.simulate(design.model_dump(), seed, mission, difficulty, upgrades, choices)
        res.pop("_ratios", None)
        return res
    except sim.DesignError as e:
        raise HTTPException(status_code=422, detail=e.errors)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/catalog")
def catalog():
    return JSONResponse(sim.DATA, headers={"Cache-Control": "public, max-age=3600"})


@app.post("/api/simulate")
def simulate(req: SimRequest):
    import random

    seed = req.seed or random.randrange(1, 2**32)
    return run(req.design, seed, req.mission, req.difficulty, req.upgrades, req.choices)


@app.post("/api/scores")
def post_score(req: ScoreRequest, request: Request):
    ip = request.client.host if request.client else "?"
    if limited(ip):
        raise HTTPException(status_code=429, detail="Too many scores. Try again in a minute.")
    result = run(req.design, req.seed, req.mission, req.difficulty, req.upgrades, req.choices)
    name = " ".join(req.name.split())[:20] or "Pilot"
    improved = db.upsert(req.player_id, name, req.mission, result["difficulty"], result["score"], result["landed"], req.seed)
    _cache.clear()
    return {"score": result["score"], "landed": result["landed"], "improved": improved, "rank": db.rank(req.mission, result["score"])}


@app.get("/api/leaderboard")
def leaderboard(mission: str = "mars", limit: int = 8):
    key = ("lb", mission, limit)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 5:
        return hit[1]
    data = db.leaderboard(mission, max(1, min(limit, 50)))
    _cache[key] = (time.time(), data)
    return data


@app.get("/api/stats")
def stats(mission: str = "mars"):
    return db.stats(mission)


GAME = Path(__file__).resolve().parent.parent / "game"
if GAME.exists():
    app.mount("/", StaticFiles(directory=GAME, html=True), name="game")
