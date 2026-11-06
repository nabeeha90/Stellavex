# Stellavex

A 3D mission design game for the NASA Space Apps Challenge 2026 (Space Mission Design Game).
Theme: **The Next Frontier**. Fly to the Moon, Mars, an asteroid, and Europa, an ocean world at the outer frontier. Built by Team Nova Nexus, Karachi.

Design a rocket under a budget, fly it through a 3D launch, and land it, or lose it.
Real physics (the rocket equation) and NASA data decide every outcome.

## Quick start (no install needed to play)

Play the game only:

    python -m http.server -d game 8080

Then open http://localhost:8080. (Opening `game/index.html` directly also works, but the page needs
internet to load the 3D library and fonts.)

## Run the full project (game + API + verified leaderboard)

    python -m venv .venv
    source .venv/bin/activate          # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    python run.py

Open http://127.0.0.1:8000. The leaderboard works only on this server. Posted scores are verified:
the server re-runs the mission with your design, seed and every in-flight decision, so scores cannot be faked.

## Real imagery, crew and shop

- The game page embeds real NASA and ESA photos (Hubble nebulae and galaxies as the universe sky, Earth, the Moon,
  Mars, Jupiter, a real launch photo, NASA SR-1 Freedom illustrations). Credits: `docs/CREDITS.md` and under each image.
- Build a crew astronaut (name, suit, visor, patch). The astronaut stands beside your rocket and plants a flag after landing.
- Earn credits by landing, then buy the Colossus rocket, the Nuclear-electric craft and the Fission reactor
  (inspired by NASA SR-1 Freedom) in the shop. Ownership is client-side progression; the server verifies flights, not purchases.
- A mission map and telemetry show your route during flight; asteroids arrive as fireballs.

## What is inside

    game/index.html            The whole game (about 1.1 MB with embedded photos): 3D scenes, UI, simulation, 5 languages
    backend/sim.py             Python port of the game's simulation (exact same results)
    backend/main.py            FastAPI server: simulate, verified scores, leaderboard, stats
    backend/db.py              SQLite storage (WAL mode, one best score per player)
    backend/data/game-data.json  Rockets, crafts, instruments, missions, hazards, difficulty
    tests/test_parity.py       Checks Python matches the game on 1,200 cases across all four missions, including in-flight decisions and the nuclear parts
    tests/test_api.py          API tests (need requirements-dev.txt)
    docs/SUBMISSION.md         Project description, demo script, limitations, credits

Run the tests:

    python -m unittest discover -s tests

## How the game works (advanced level)

1. Pick a mission: the Moon (tutorial), Mars, an asteroid, then Europa. Each unlocks after landing on the one before,
   and your Frontier Rank grows from Cadet to Frontier Pathfinder.
2. Spend credits on lab upgrades, then design the whole mission: rocket, spacecraft, fuel, **power system**
   (solar panels or a nuclear battery, plus a battery), **antenna**, instruments, route, **launch window**
   and **arrival orbit**. Each part has mass, cost and power draw, and instruments generate data.
3. Launch. Four stages play out: launch, transfer, arrival, landing.
4. Ten hazards can strike (launch scrub, engine underperformance, solar flare, asteroid strike, fuel leak,
   micrometeoroids, signal blackout, guidance glitch, dust storm, boulder field). Most ask for **your decision**
   mid-flight, each with a real trade-off between fuel, science and risk.
5. Score = 40% mission success, 30% science return, 30% resource efficiency. Science depends on power
   (instruments run at the share of demand your supply covers) and data (what your antenna can send home).

Physics: delta-v = Isp x g0 x ln(m0 / mf). Fuel adds delta-v but also mass and cost.
Solar power = area x sunlight x 28% efficiency x 45% average. Data rate falls with the square of distance.
The same design and seed always give the same result.

## NASA data used

Solar irradiance (Mars 586.2 W/m2, Earth 1,361 W/m2), Perseverance's nuclear battery (about 110 W, 45 kg)
and UHF relay (up to 2 Mbps) from NASA JPL, Mars gravity 3.73 m/s2, air pressure about 0.6 kPa, atmosphere 95.3% CO2, day length 24.7 h,
Europa Clipper (launched 14 Oct 2024, reaches Jupiter April 2030, huge solar arrays; NASA JPL),
Earth-Mars distance 54.6 to 401 million km, signal delay 3 to 22 minutes, launch windows about every
26 months, Moon gravity 1.62 m/s2, Moon distance 384,400 km. Sources are listed in the game
(NASA resources page): NASA Mars and Moon Fact Sheets, NASA Europa Clipper, NASA Mars Exploration, JPL Solar System
Dynamics, NASA Artemis, NASA Image and Video Library.

## Performance notes

- Graphics quality is chosen automatically (Low on weak phones) and can be changed under Access.
- Planet and galaxy textures are generated in small slices so the page never freezes.
- Shared materials, disposal of old 3D objects, a frame cap on info pages, and a 1.75x pixel-ratio cap.
- The API uses gzip, SQLite WAL mode, a short leaderboard cache, and a per-address rate limit.

## Keeping Python and the game in sync

`backend/data/game-data.json` and `tests/golden.json` were exported from the game's engine
(`node` script, see the note in tests/test_parity.py).
If you change game rules in `game/index.html`, re-export both and run the parity test.

## Limitations

- Physics is simplified (flat transfers, no gravity losses); part values are balancing numbers.
- Players choose their own seeds, so the verified leaderboard proves the score is real for that seed,
  not that the seed was chosen fairly. Use the Daily challenge seed for a fairer board.
- Interface translations (Spanish, French, Arabic, Urdu) were not reviewed by native speakers,
  and the long research pages are English only.
- Photo credits follow the sources shown in the screenshots they were cut from; check them against the NASA Image and Video Library before publishing.
- The NASA logo is a simple recreation: use the official artwork and follow NASA brand rules.
- Not yet tested with real students.

Stellavex is an independent project made for the NASA Space Apps Challenge. It is not endorsed by NASA.

## License

MIT, see LICENSE.
