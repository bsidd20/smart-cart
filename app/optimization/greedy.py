"""Greedy optimizer for the single-store and multi-store plans.

Single store: score each store's basket (with penalties for items it lacks) and pick
the best. Multi store: assign each item to a store to minimize the objective, capped
at max_stores. The greedy split seeds from each item's cheapest store, consolidates
down to the cap, then drops any store that isn't worth the trip. It's O(items x
stores) and easy to explain per item; ortools_solver.py has an exact version.
"""
from __future__ import annotations

from app.config import Settings, Weights
from app.data.store import Repository
from app.matching.matcher import ProductMatcher
from app.models import Assignment, OptimizationResult, UserCartItem
from app.optimization.ranking import Line, objective


def _collect_options(matcher: ProductMatcher, cart: list[UserCartItem]) -> dict:
    """item_text -> {store_id: {unit_price, score, method, product_name}}."""
    options: dict[str, dict[str, dict]] = {}
    for ci in cart:
        per_store = {}
        for sid, m in matcher.match_across_stores(ci.raw_text).items():
            if m.available:
                per_store[sid] = {
                    "unit_price": m.price, "score": m.score,
                    "method": m.method, "product_name": m.product_name,
                }
        options[ci.raw_text] = per_store
    return options


def _eff_cost(item_opt: dict, qty: int, w: Weights) -> float:
    """Per-item cost for picking a store: price plus substitution penalty."""
    return qty * item_opt["unit_price"] + w.substitution_penalty * (1 - item_opt["score"])


def _plan_metrics(chosen: dict, missing: list, options: dict, qty: dict,
                  oneway_km: dict, w: Weights) -> dict:
    lines = [Line(item, qty[item], sid, options[item][sid]["unit_price"],
                  options[item][sid]["score"])
             for item, sid in chosen.items()]
    return objective(lines, len(missing), oneway_km, w)


def _build_result(strategy: str, chosen: dict, missing: list, options: dict,
                  qty: dict, oneway_km: dict, repo: Repository, w: Weights,
                  total_items: int) -> OptimizationResult:
    assignments: list[Assignment] = []
    for item, sid in chosen.items():
        opt = options[item][sid]
        store = repo.store(sid)
        alts = sorted(((o["unit_price"], s) for s, o in options[item].items() if s != sid))
        if alts:
            alt_price, alt_sid = alts[0]
            alt = f" Next-best was ${alt_price:.2f} at {repo.store(alt_sid).name}."
        else:
            alt = " Only this store carries it."
        reason = (f"${opt['unit_price']:.2f} at {store.name} - matched "
                  f"'{opt['product_name']}' via {opt['method']} "
                  f"(conf {opt['score']:.2f}).{alt}")
        assignments.append(Assignment(
            item=item, quantity=qty[item], store_id=sid, store_name=store.name,
            product_name=opt["product_name"], unit_price=round(opt["unit_price"], 2),
            line_cost=round(qty[item] * opt["unit_price"], 2),
            match_score=opt["score"], match_method=opt["method"], reason=reason,
        ))

    m = _plan_metrics(chosen, missing, options, qty, oneway_km, w)
    coverage = (total_items - len(missing)) / total_items if total_items else 0.0
    stores_used = [repo.store(s).name for s in m["stores_used"]]
    explanation = [
        f"Requested {total_items} items; found {total_items - len(missing)} "
        f"({coverage:.0%} coverage).",
        f"Plan uses {m['num_stores']} store(s): {', '.join(stores_used) or '-'}.",
        f"Basket ${m['basket_price']:.2f}; round-trip {m['total_distance_km']:.1f} km; "
        f"objective {m['objective']} (lower is better).",
    ]
    if missing:
        explanation.append(f"Could not find: {', '.join(missing)}.")

    return OptimizationResult(
        strategy=strategy, assignments=assignments, missing_items=missing,
        total_cost=m["basket_price"], num_stores=m["num_stores"],
        stores_used=stores_used, total_distance_km=m["total_distance_km"],
        coverage=round(coverage, 3), objective=m["objective"], explanation=explanation,
    )


def optimize_single_store(options, qty, oneway_km, repo, w) -> OptimizationResult:
    items = list(options)
    best_sid, best_metrics, best_chosen, best_missing = None, None, None, None
    for sid in repo.all_store_ids():
        chosen, missing = {}, []
        for item in items:
            (chosen.__setitem__(item, sid) if sid in options[item]
             else missing.append(item))
        metrics = _plan_metrics(chosen, missing, options, qty, oneway_km, w)
        if best_metrics is None or metrics["objective"] < best_metrics["objective"]:
            best_sid, best_metrics = sid, metrics
            best_chosen, best_missing = chosen, missing
    return _build_result("single_store", best_chosen, best_missing, options,
                         qty, oneway_km, repo, w, len(items))


def optimize_multi_store(options, qty, oneway_km, repo, w, max_stores) -> OptimizationResult:
    items = list(options)

    def J(c, miss):
        return _plan_metrics(c, miss, options, qty, oneway_km, w)["objective"]

    def reassign_without(store_to_drop, cur_chosen, cur_missing):
        # Prefer reassigning to a store already in the plan, since that adds no new
        # trip; that's what makes consolidation actually reduce the store count.
        used_after = {s for s in cur_chosen.values() if s != store_to_drop}
        new_chosen, new_missing = {}, list(cur_missing)
        for item, sid in cur_chosen.items():
            if sid != store_to_drop:
                new_chosen[item] = sid
                continue
            alts = {s: o for s, o in options[item].items() if s != store_to_drop}
            if not alts:
                new_missing.append(item)            # nobody else carries it
                continue
            used_alts = {s: o for s, o in alts.items() if s in used_after}
            pool = used_alts or alts
            new_chosen[item] = min(pool, key=lambda s: _eff_cost(pool[s], qty[item], w))
        return new_chosen, new_missing

    # Seed with each item's cheapest store and with every all-at-one-store plan,
    # then keep the best. The single-store seeds stop the search from settling on a
    # split that's worse than just shopping at one store.
    seeds: list[tuple[dict, list]] = []
    g_chosen, g_missing = {}, []
    for item in items:
        opts = options[item]
        if not opts:
            g_missing.append(item)
        else:
            g_chosen[item] = min(opts, key=lambda s: _eff_cost(opts[s], qty[item], w))
    seeds.append((g_chosen, g_missing))
    for sid in repo.all_store_ids():
        c, miss = {}, []
        for item in items:
            (c.__setitem__(item, sid) if sid in options[item] else miss.append(item))
        if c:
            seeds.append((c, miss))
    chosen, missing = min(seeds, key=lambda cm: J(*cm))

    # Consolidate down to max_stores, dropping the least costly store each time.
    used = sorted({chosen[i] for i in chosen})
    while len(used) > max_stores:
        best_drop = min(used, key=lambda s: J(*reassign_without(s, chosen, missing)))
        chosen, missing = reassign_without(best_drop, chosen, missing)
        used = sorted({chosen[i] for i in chosen})

    # Drop any remaining store while doing so still lowers the objective.
    improved = True
    while improved:
        improved = False
        for s in sorted({chosen[i] for i in chosen}):
            cand_chosen, cand_missing = reassign_without(s, chosen, missing)
            if J(cand_chosen, cand_missing) < J(chosen, missing) - 1e-9:
                chosen, missing = cand_chosen, cand_missing
                improved = True
                break

    return _build_result("multi_store", chosen, missing, options,
                         qty, oneway_km, repo, w, len(items))


def optimize_cart(repo: Repository, matcher: ProductMatcher,
                  cart: list[UserCartItem], settings: Settings) -> dict:
    options = _collect_options(matcher, cart)
    qty = {ci.raw_text: ci.quantity for ci in cart}
    oneway_km = {sid: repo.distance_km(sid, settings.user_lat, settings.user_lon)
                 for sid in repo.all_store_ids()}
    w = settings.weights

    single = optimize_single_store(options, qty, oneway_km, repo, w)
    multi = optimize_multi_store(options, qty, oneway_km, repo, w, settings.max_stores)

    savings = round(single.objective - multi.objective, 2)
    if savings > 0:
        multi.explanation.append(
            f"Multi-store beats best single store by {savings} objective points "
            f"(basket ${multi.total_cost:.2f} vs ${single.total_cost:.2f})."
        )
    else:
        multi.explanation.append(
            "Best single store is already optimal here; splitting wouldn't help.")
    return {"single_store": single, "multi_store": multi}
