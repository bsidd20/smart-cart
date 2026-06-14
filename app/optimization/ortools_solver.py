"""Exact multi-store optimization as an ILP (optional, needs OR-Tools).

Same objective as the greedy solver, solved to optimality:

  variables
    x[i,s] in {0,1}  item i bought at store s (only where s stocks i)
    y[s]   in {0,1}  store s is visited
    u[i]   in {0,1}  item i left unmet

  minimise  price*qty*price_is*x + substitution*(1-score_is)*x
          + store_visit*y + distance*2*dist_s*y + coverage*u

  subject to  sum_s x[i,s] + u[i] = 1  (each item assigned or unmet)
              x[i,s] <= y[s]           (can't buy at an unvisited store)
              sum_s y[s] <= max_stores

Import-guarded: if OR-Tools isn't installed the caller falls back to greedy. Both
solvers use the same objective, so their results are directly comparable.
"""

from __future__ import annotations

from app.config import Weights
from app.data.store import Repository
from app.models import OptimizationResult
from app.optimization.greedy import _build_result


def is_available() -> bool:
    try:
        from ortools.linear_solver import pywraplp  # noqa: F401

        return True
    except Exception:
        return False


def optimize_multi_store_ilp(
    options, qty, oneway_km, repo: Repository, w: Weights, max_stores: int
) -> OptimizationResult | None:
    try:
        from ortools.linear_solver import pywraplp
    except Exception:
        return None

    solver = pywraplp.Solver.CreateSolver("CBC")
    if solver is None:
        return None

    items = list(options)
    stores = repo.all_store_ids()

    x, u, y = {}, {}, {}
    for s in stores:
        y[s] = solver.BoolVar(f"y_{s}")
    for i in items:
        u[i] = solver.BoolVar(f"u_{i}")
        for s in options[i]:  # only stores that stock i
            x[(i, s)] = solver.BoolVar(f"x_{i}_{s}")

    # assign-once (or unmet)
    for i in items:
        solver.Add(sum(x[(i, s)] for s in options[i]) + u[i] == 1)
    # cannot buy at an unopened store
    for (i, s), var in x.items():
        solver.Add(var <= y[s])
    # practicality cap
    solver.Add(sum(y[s] for s in stores) <= max_stores)

    obj = solver.Objective()
    for (i, s), var in x.items():
        cost = w.price_weight * qty[i] * options[i][s]["unit_price"] + w.substitution_penalty * (
            1 - options[i][s]["score"]
        )
        obj.SetCoefficient(var, cost)
    for s in stores:
        obj.SetCoefficient(y[s], w.store_visit_penalty + w.distance_weight * 2 * oneway_km[s])
    for i in items:
        obj.SetCoefficient(u[i], w.coverage_penalty)
    obj.SetMinimization()

    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        return None

    chosen, missing = {}, []
    for i in items:
        if u[i].solution_value() > 0.5:
            missing.append(i)
            continue
        for s in options[i]:
            if x[(i, s)].solution_value() > 0.5:
                chosen[i] = s
                break

    result = _build_result(
        "multi_store", chosen, missing, options, qty, oneway_km, repo, w, len(items)
    )
    result.explanation.append("Solved to proven optimality via ILP (OR-Tools CBC).")
    return result
