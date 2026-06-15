"""End-to-end demo. Builds the lakehouse from the committed real-data sample if
needed, shows the ingestion/quality/analytics layers, then matches a grocery list
and prints the single-store and multi-store plans.

    python scripts/demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copy import deepcopy  # noqa: E402

from app.config import SETTINGS, Weights  # noqa: E402
from app.data.store import Repository  # noqa: E402
from app.ingestion import io, paths  # noqa: E402
from app.ingestion.orchestration import pipeline  # noqa: E402
from app.matching.matcher import ProductMatcher  # noqa: E402
from app.models import UserCartItem  # noqa: E402
from app.optimization import greedy, ortools_solver  # noqa: E402

CART = ["chicken breast", "rice", "eggs", "milk", "spinach"]


def rule(c="-", n=78):
    print(c * n)


def print_plan(label, plan):
    rule("=")
    print(label)
    rule("=")
    for a in plan.assignments:
        print(
            f"  {a.item:<16} -> {a.store_name:<14} ${a.unit_price:>5.2f}  "
            f"[{a.product_name}]  ({a.match_method} {a.match_score:.2f})"
        )
    if plan.missing_items:
        print(f"  missing: {', '.join(plan.missing_items)}")
    print(
        f"  basket ${plan.total_cost:.2f} | {plan.num_stores} store(s) "
        f"({', '.join(plan.stores_used)}) | {plan.total_distance_km:.1f} km "
        f"round-trip | coverage {plan.coverage:.0%} | objective {plan.objective}"
    )


def show_platform():
    rule("=")
    print("ingestion platform (Open Food Facts -> bronze -> silver -> gold)")
    rule("=")
    for name, p in [
        ("bronze.raw_products", paths.BRONZE_RAW_PRODUCTS),
        ("silver.dim_product", paths.SILVER_DIM_PRODUCT),
        ("silver.fact_inventory", paths.SILVER_FACT_INVENTORY),
        ("gold.store_product_offers", paths.GOLD_OFFERS),
    ]:
        print(f"  {name:<28} v{io.table_version(p)}  {len(io.read_delta(p)):>4} rows")

    q = io.read_delta(paths.QUALITY_RESULTS)
    q = q[q["run_id"] == q.sort_values("checked_at")["run_id"].iloc[-1]]  # latest run only
    print("\n  data quality checks:")
    for r in q.itertuples(index=False):
        flag = "ok" if r.passed else f"{r.failed_count} failed"
        print(f"    {r.check_name:<20} [{r.severity:<5}] {flag}")

    print("\n  cheapest store per category (gold.category_price_stats):")
    stats = io.read_delta(paths.GOLD_CATEGORY_PRICE_STATS)
    for r in stats[
        stats["category"].isin(["chicken breast", "milk", "spinach", "rice"])
    ].itertuples(index=False):
        print(
            f"    {r.category:<16} ${r.min_price:>5.2f}-${r.max_price:<5.2f}  at {r.cheapest_store}"
        )


def main():
    pipeline.run_fixture()  # deterministic clean rebuild from the committed sample
    repo = Repository.load()
    matcher = ProductMatcher(repo)

    show_platform()
    print(f"\nmatcher backend: {matcher.backend}")
    print(f"stores: {len(repo.all_store_ids())} | cart: {CART}\n")

    rule()
    print("matching (real Open Food Facts products):")
    rule()
    for q in CART:
        ms = [m for m in matcher.match_across_stores(q).values() if m.available]
        if ms:
            best = min(ms, key=lambda m: (-m.score, m.price))
            print(
                f"  {q:<15} -> {best.product_name}  "
                f"({best.method}, conf {best.score:.2f}, {len(ms)} stores)"
            )
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

    print()
    rule("=")
    print("same cart, weights tuned for a price-focused shopper")
    rule("=")
    pf = deepcopy(SETTINGS)
    pf.weights = Weights(
        price_weight=1.0,
        distance_weight=0.05,
        substitution_penalty=2.0,
        store_visit_penalty=0.30,
        coverage_penalty=25.0,
    )
    r2 = greedy.optimize_cart(repo, matcher, cart, pf)
    s2, m2 = r2["single_store"], r2["multi_store"]
    print(
        f"  single store : ${s2.total_cost:5.2f}  {s2.num_stores} store   "
        f"obj {s2.objective:6.2f}  ({', '.join(s2.stores_used)})"
    )
    print(
        f"  multi store  : ${m2.total_cost:5.2f}  {m2.num_stores} stores  "
        f"obj {m2.objective:6.2f}  ({', '.join(m2.stores_used)})"
    )
    winner = "multi-store" if m2.objective < s2.objective else "single-store"
    print(f"  -> prefers {winner} (basket diff ${s2.total_cost - m2.total_cost:.2f})")

    print()
    if not ortools_solver.is_available():
        print("OR-Tools not installed; run `pip install ortools` for the exact solver.")


if __name__ == "__main__":
    main()
