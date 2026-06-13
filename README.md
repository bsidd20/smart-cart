# smart-cart

Turn a grocery list into a shopping plan. Given items like
`["chicken breast", "rice", "eggs", "milk", "spinach"]`, smart-cart returns the
best single store to buy everything, the cheapest practical multi-store split, and
a short reason for each item.

It runs locally with no paid APIs. The parts I cared about are the product matcher
(fuzzy, with optional embeddings) and the multi-store assignment, which is a small
constrained-optimization problem solved greedily, with an exact ILP available when
you want a provably optimal answer.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/generate_data.py   # build the local catalog
python scripts/demo.py            # run an example end to end
```

API:

```bash
uvicorn app.main:app --reload     # docs at http://127.0.0.1:8000/docs
```

Tests: `pytest`

## Endpoints

- `GET /stores` - stores near the user with distances
- `POST /match-items` - `{"items": ["milk", "spinach"]}` -> best product per item
- `POST /optimize-cart` - `{"items": [...], "max_stores": 3, "use_ilp": false}` ->
  single-store plan, multi-store plan, and per-item reasons

```json
POST /optimize-cart
{ "items": ["chicken breast", "rice", "eggs", "milk", "spinach"] }
```

Each plan comes back with an `objective` score so you can see which one the engine
prefers and why.

## How it works

**Data.** Real grocery prices aren't freely available, so `app/data/simulator.py`
generates a catalog: a fixed product list (with synonyms) and several stores whose
chains have different price profiles and coverage - a cheap-pantry warehouse, an
organic produce market, a butcher, and so on. It's seeded, so the data is identical
every run. Swapping this module for a scraper or a real feed is the only change
needed to use live data.

**Matching** (`app/matching/`). Each list item is matched to a product at each
store. Fuzzy matching (RapidFuzz) handles typos, plurals and word order; an optional
embedding matcher handles meaning. The embedder is pluggable - a small hashing
vector by default so there are no heavy dependencies, or `sentence-transformers` if
it's installed. A score threshold keeps bad substitutions out, so "spinach" doesn't
get matched to "spaghetti".

**Optimization** (`app/optimization/`). The single-store answer scores each store's
basket and picks the best. The multi-store answer assigns each item to a store to
minimize one objective:

```
price·basket + distance·round_trip_km + subs·sum(1 - match_score)
  + visit·num_stores + coverage·num_missing
```

The greedy solver starts from each item's cheapest store, consolidates down to
`max_stores`, and drops any store that isn't worth the extra trip. The weights live
in `app/config.py`: raising the distance/visit weights pushes plans toward a single
store, lowering them lets plans fan out to cheaper specialists. `ortools_solver.py`
solves the same objective exactly as an ILP if OR-Tools is installed.

## Notes

- The default embedder is a cheap hashing vector and is only used to re-rank, not to
  accept a match on its own - install `sentence-transformers` for real semantic
  matching of synonyms.
- The greedy solver is fast and easy to follow but isn't guaranteed optimal; the ILP
  is there for when that matters.
- For a larger catalog, swap the JSON repository for SQLite/Postgres and precompute
  embeddings into a FAISS index.

## Layout

```
app/
  main.py            FastAPI app
  models.py          data models
  config.py          paths, location, weights
  data/              catalog generator + repository
  matching/          fuzzy, semantic, orchestrator
  optimization/      ranking, greedy, ortools
scripts/             generate_data.py, demo.py
tests/
```
