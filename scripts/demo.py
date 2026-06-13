"""End-to-end example: matches a 5-item list and prints the single-store plan, the
multi-store split, and the per-item reasons. No server needed.

    python scripts/demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copy import deepcopy                                # noqa: E402

from app import config                                   # noqa: E402
from app.config import SETTINGS, Weights                 # noqa: E402
from app.data import simulator                           # noqa: E402
from app.data.store import Repository                    # noqa: E402
from app.matching.matcher import ProductMatcher          # noqa: E402
from app.models import UserCartItem                      # noqa: E402
from app.optimization import greedy, ortools_solver      # noqa: E402

CART = ["chicken breast", "rice", "eggs", "milk", "spinach"]


def rule(c="-", n=78):
    print(c * n)


def print_plan(label, plan):
    rule("=")
    print(label)
    rule("=")
    for a in plan.assignments:
        print(f"  {a.item:<16} -> {a.store_name:<14} ${a.unit_price:>5.2f}  "
              f"[{a.product_name}]  ({a.match_method} {a.match_score:.2f})")
    if plan.missing_items:
        print(f"  missing: {', '.join(plan.missing_items)}")
    print(f"  basket ${plan.total_cost:.2f} | {plan.num_stores} store(s) "
          f"({', '.join(plan.stores_used)}) | {plan.total_distance_km:.1f} km "
          f"round-trip | coverage {plan.coverage:.0%} | objective {plan.objective}")


def main():
    if not config.STORES_FILE.exists():
        simulator.write_dataset()
    repo = Repository.load()
    matcher = ProductMatcher(repo)

    print(f"\nmatcher backend: {matcher.backend}")
    print(f"stores: {len(repo.all_store_ids())} | cart: {CART}\n")

    rule()
    print("matching (best product per item):")
    rule()
    for q in CART:
        ms = [m for m in matcher.match_across_stores(q).values() if m.available]
        if ms:
            best = min(ms, key=lambda m: (-m.score, m.price))
            print(f"  {q:<15} -> {best.product_name}  "
                  f"({best.method}, conf {best.score:.2f}, "
                  f"{len(ms)}/{len(repo.all_store_ids())} stores)")
        else:
            print(f"  {q:<15} -> no match")
    print()

    cart = [UserCartItem(raw_text=i) for i in CART]
    result = greedy.optimize_cart(repo, matcher, cart, SETTINGS)

    print_plan("A) best single store", result["single_store"])
    print()
    print_plan("B) best multi-store split", result["multi_store"])

    print()
    rule("=")
    print("C) why (multi-store plan)")
    rule("=")
    for e in result["multi_store"].explanation:
        print(f"  - {e}")
    print()
    for a in result["multi_store"].assignments:
        print(f"  {a.item}: {a.reason}")

    # Same cart, a shopper who doesn't mind extra stops: lower distance/visit weights.
    print()
    rule("=")
    print("same cart, weights tuned for a price-focused shopper")
    rule("=")
    price_focused = deepcopy(SETTINGS)
    price_focused.weights = Weights(price_weight=1.0, distance_weight=0.05,
                                    substitution_penalty=2.0, store_visit_penalty=0.30,
                                    coverage_penalty=25.0)
    r2 = greedy.optimize_cart(repo, matcher, cart, price_focused)
    s2, m2 = r2["single_store"], r2["multi_store"]
    print(f"  single store : ${s2.total_cost:5.2f}  {s2.num_stores} store   "
          f"obj {s2.objective:6.2f}  ({', '.join(s2.stores_used)})")
    print(f"  multi store  : ${m2.total_cost:5.2f}  {m2.num_stores} stores  "
          f"obj {m2.objective:6.2f}  ({', '.join(m2.stores_used)})")
    winner = "multi-store" if m2.objective < s2.objective else "single-store"
    print(f"  -> prefers {winner} "
          f"(basket diff ${s2.total_cost - m2.total_cost:.2f})")

    print()
    if ortools_solver.is_available():
        options = greedy._collect_options(matcher, cart)
        qty = {ci.raw_text: ci.quantity for ci in cart}
        oneway = {s: repo.distance_km(s, SETTINGS.user_lat, SETTINGS.user_lon)
                  for s in repo.all_store_ids()}
        ilp = ortools_solver.optimize_multi_store_ilp(
            options, qty, oneway, repo, SETTINGS.weights, SETTINGS.max_stores)
        if ilp:
            print(f"ILP optimal objective {ilp.objective} "
                  f"(greedy got {result['multi_store'].objective})")
    else:
        print("OR-Tools not installed; run `pip install ortools` for the exact solver.")


if __name__ == "__main__":
    main()
