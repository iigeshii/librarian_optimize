import json
from pathlib import Path
import argparse
from collections import defaultdict
import re
import sys

# ==========================================================
# Helpers
# ==========================================================

def current_price_for(villagers, villager_name, enchant):
    """
    Returns the effective trade price for an enchantment on a villager,
    choosing 'post' if villager is cured, otherwise 'pre'.
    Supports:
      - legacy int price
      - new {"pre": int|'X'|None, "post": int|'X'|None}
    Returns None if no usable price.
    """
    data = villagers[villager_name]["enchantments"].get(enchant)
    if data is None:
        return None
    if isinstance(data, int):
        return data
    cured = bool(villagers[villager_name].get("cured"))
    val = data.get("post" if cured else "pre")
    if val in (None, "X"):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def strip_roman_numerals(name):
    return re.sub(r" [IVXLCDM]+$", "", name)


def get_enchantment_index(enchantment, required_list):
    sorted_required = sorted(required_list)
    try:
        return sorted_required.index(enchantment) + 1
    except ValueError:
        return None


# ==========================================================
# Data loading
# ==========================================================

def load_data(villagers_file):
    """
    EXPECTED enchantments.json FORMAT:
    {
      "villager_enchantments": [
        { "name": "Mending", "priority": 1 },
        ...
      ],
      "non_enchantments": ["Bookshelf", "Lantern", ...],
      "enchantment_costs": [
        { "name": "Mending", "pre": 38, "post": 10 },
        ...
      ]
    }
    """
    villagers_path = Path(villagers_file)
    enchants_path = Path(__file__).parent / "enchantments.json"

    if not villagers_path.exists():
        raise FileNotFoundError(f"Missing file: {villagers_path}")
    if not enchants_path.exists():
        raise FileNotFoundError(f"Missing file: {enchants_path}")

    with open(villagers_path, "r", encoding="utf-8") as f:
        villagers = json.load(f)
    with open(enchants_path, "r", encoding="utf-8") as f:
        master = json.load(f)

    # --- villager_enchantments ---
    raw = master.get("villager_enchantments")
    if not isinstance(raw, list) or not raw:
        raise ValueError("enchantments.json must have a non-empty 'villager_enchantments' list.")

    enchant_priority = {}
    names_seen = set()
    for entry in raw:
        name = entry.get("name")
        prio = entry.get("priority")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each enchantment must have a name.")
        if name in names_seen:
            raise ValueError(f"Duplicate enchantment '{name}'.")
        if not isinstance(prio, int) or prio < 1:
            raise ValueError(f"Invalid priority for {name}: {prio}")
        names_seen.add(name)
        enchant_priority[name] = prio

    villager_enchants = set(names_seen)

    # --- non_enchantments ---
    non_raw = master.get("non_enchantments")
    if not isinstance(non_raw, list) or not all(isinstance(x, str) for x in non_raw):
        raise ValueError("'non_enchantments' must be a list of strings.")
    non_enchants = set(non_raw)

    # --- enchantment_costs (optional) ---
    costs_raw = master.get("enchantment_costs", [])
    enchant_costs = {}
    if costs_raw:
        for entry in costs_raw:
            name = entry.get("name")
            if not isinstance(name, str):
                continue
            enchant_costs[name] = {
                "pre": entry.get("pre"),
                "post": entry.get("post")
            }

    # --- validate villagers ---
    all_master = villager_enchants | non_enchants
    invalid_entries = []
    for v_name, data in villagers.items():
        ench_dict = data.get("enchantments", {})
        for ench_name in ench_dict.keys():
            if ench_name not in all_master:
                invalid_entries.append((v_name, ench_name))
    if invalid_entries:
        print("❌ Error: Unrecognized enchantments:")
        for v, e in invalid_entries:
            print(f"  - {v}: '{e}'")
        sys.exit(1)

    return villagers, villager_enchants, non_enchants, enchant_priority, enchant_costs


# ==========================================================
# Cost analysis
# ==========================================================

def compute_observed_costs(villagers):
    observed = {}
    for v_name, vdata in villagers.items():
        cured = bool(vdata.get("cured"))
        for ench, val in vdata.get("enchantments", {}).items():
            pre_val = post_val = None
            if isinstance(val, int):
                if cured:
                    post_val = val
                else:
                    pre_val = val
            elif isinstance(val, dict):
                pre_raw = val.get("pre")
                post_raw = val.get("post")
                pre_val = pre_raw if isinstance(pre_raw, int) else None
                post_val = post_raw if isinstance(post_raw, int) else None

            slot = observed.setdefault(ench, {"pre": None, "post": None})
            if pre_val is not None and (slot["pre"] is None or pre_val < slot["pre"]):
                slot["pre"] = pre_val
            if post_val is not None and (slot["post"] is None or post_val < slot["post"]):
                slot["post"] = post_val
    return observed


def print_cost_guide(enchant_priority, enchant_costs, observed_costs):
    """
    Print alphabetized cost table using observed villager data.
    No * marks — all values come from observed sources.
    """
    # Combine all names
    all_names = sorted(set(enchant_priority.keys()) | set(observed_costs.keys()))

    print("\n📊 Cost Guide (alphabetical):")
    for name in all_names:
        observed = observed_costs.get(name, {})
        pre = observed.get("pre")
        post = observed.get("post")
        pre_str = "—" if pre is None else str(pre)
        post_str = "—" if post is None else str(post)
        print(f"  - {name:<24} pre: {pre_str:>4}   post: {post_str:>4}")

    if not any(isinstance(v.get("pre"), int) or isinstance(v.get("post"), int) for v in observed_costs.values()):
        print("\n⚠️ No cost data found in villagers file.")



# ==========================================================
# Utility printers
# ==========================================================

def get_villager_enchantments(villagers):
    all_enchants = set()
    for data in villagers.values():
        all_enchants.update(data["enchantments"].keys())
    return all_enchants


def get_non_enchantment_codes(name, villagers, non_enchantments):
    hints = {"Glass": "Glass", "Nametag": "Nametag", "Bookshelf": "Bookshelf",
             "Lantern": "Lantern", "Compass": "Compass", "Clock": "Clock"}

    def abbr(item):
        return hints.get(item, "".join(w[0] for w in item.split()).upper())

    codes = [abbr(e) for e in villagers[name]["enchantments"] if e in non_enchantments]
    return f"({', '.join(codes)})" if codes else ""


def print_all_enchantments(villagers, required):
    enchant_map = defaultdict(list)
    for name, data in villagers.items():
        for enchant in data["enchantments"].keys():
            if enchant in required:
                price = current_price_for(villagers, name, enchant)
                price_str = "?" if price is None else str(price)
                enchant_map[enchant].append(f"{name} ({price_str})")

    print("\n📘 Enchantment coverage:")
    max_name_len = max(len(name) for name in sorted(required)) if required else 0
    for i, enchant in enumerate(sorted(required)):
        if enchant in enchant_map:
            holders = ", ".join(sorted(enchant_map[enchant]))
            print(f"{i+1:>2}. {enchant:<{max_name_len}} : {holders}")
        else:
            print(f"{i+1:>2}. {enchant:<{max_name_len}} : ❌ None")


# ==========================================================
# Optimizers
# ==========================================================

def optimize_min_villagers(villagers, required):
    remaining = set(required)
    optimized = {}
    while remaining:
        best_v, best_cov = None, set()
        for name, data in villagers.items():
            cov = {e for e in (set(data["enchantments"]) & remaining)
                   if current_price_for(villagers, name, e) is not None}
            if len(cov) > len(best_cov):
                best_v, best_cov = name, cov
        if not best_v or not best_cov:
            break
        optimized[best_v] = {"enchantments": {e: current_price_for(villagers, best_v, e) for e in best_cov}}
        remaining -= best_cov
    return optimized


def optimize_min_cost(villagers, required):
    result = {}
    for enchant in sorted(required):
        best_name, best_price = None, float("inf")
        for name in villagers:
            price = current_price_for(villagers, name, enchant)
            if price is None:
                continue
            if price < best_price or (price == best_price and (best_name is None or name < best_name)):
                best_name, best_price = name, price
        if best_name is not None:
            result.setdefault(best_name, {"enchantments": {}})
            result[best_name]["enchantments"][enchant] = best_price
    return result


def optimize_priority_tiered(villagers, required, enchant_priority, p2_threshold=10):
    """
    Priority-aware optimization:
      P1 -> absolute cheapest
      P2 -> cheapest if gap>threshold or villager already chosen
      Others -> minimize villager count
    """
    p1 = {e for e in required if enchant_priority.get(e, 10) == 1}
    p2 = {e for e in required if enchant_priority.get(e, 10) == 2}
    p_other = required - p1 - p2

    def cheapest_and_second(e):
        best, best_price, second = None, float("inf"), None
        for v in villagers:
            p = current_price_for(villagers, v, e)
            if p is None:
                continue
            if p < best_price:
                second, best, best_price = best_price, v, p
            elif second is None or p < second:
                second = p
        return best, best_price, second

    chosen = {}
    # P1
    for e in sorted(p1):
        v_best, _, _ = cheapest_and_second(e)
        if v_best:
            chosen.setdefault(v_best, set()).add(e)
    # P2
    for e in sorted(p2):
        v_best, p_best, p_second = cheapest_and_second(e)
        if not v_best:
            continue
        p_chosen_best = min(
            (current_price_for(villagers, v, e) for v in chosen if current_price_for(villagers, v, e) is not None),
            default=None,
        )
        if v_best in chosen:
            chosen[v_best].add(e)
        elif p_chosen_best is not None and (p_chosen_best - p_best) <= p2_threshold:
            # keep with chosen
            pass
        elif p_second is not None and (p_second - p_best) <= p2_threshold:
            pass
        else:
            chosen.setdefault(v_best, set()).add(e)

    optimized = {v: {"enchantments": {e: current_price_for(villagers, v, e) for e in ench}} for v, ench in chosen.items()}

    # Cover remaining enchants minimally
    assigned = {e for data in optimized.values() for e in data["enchantments"]}
    remaining = required - assigned
    while remaining:
        best_v, best_cov = None, set()
        for name, data in villagers.items():
            cov = {e for e in (set(data["enchantments"]) & remaining)
                   if current_price_for(villagers, name, e) is not None}
            if len(cov) > len(best_cov):
                best_v, best_cov = name, cov
        if not best_v or not best_cov:
            break
        optimized.setdefault(best_v, {"enchantments": {}})
        for e in best_cov:
            optimized[best_v]["enchantments"][e] = current_price_for(villagers, best_v, e)
        remaining -= best_cov
    return optimized


# ==========================================================
# Reporting
# ==========================================================

def emit_optimized_report(
    method_label, optimized, villagers, required, non_enchantments, enchant_priority, show_signs=False
):
    def prio_tag(e):
        if e in non_enchantments or e not in enchant_priority:
            return ""
        return f"P{enchant_priority[e]}"

    print(f"\n🧠 Optimized villager set ({method_label}):")
    max_name_len = max(len(name) for name in villagers)
    total_cost = 0
    for i, name in enumerate(sorted(optimized)):
        enchants = optimized[name]["enchantments"]
        ench_str = ", ".join(
            f"{e}{(' [' + prio_tag(e) + ']') if prio_tag(e) else ''} ({'?' if c is None else c})"
            for e, c in sorted(enchants.items())
        )
        total_cost += sum(c for c in enchants.values() if isinstance(c, (int, float)))
        print(f"{i+1:>2}. {name:<{max_name_len}} : {ench_str}")

    if method_label.startswith("min-cost"):
        print(f"\n💰 Total cost: {total_cost}")

    if not show_signs:
        return

    print("\n📋 Sign Layout:")
    for v, data in optimized.items():
        print(f"------- {v} -------")
        for e in sorted(data["enchantments"]):
            print(f"§b{get_enchantment_index(e, required)}. {strip_roman_numerals(e)}")
        codes = get_non_enchantment_codes(v, villagers, non_enchantments)
        if codes:
            print(f"§e{codes}")


# ==========================================================
# CLI
# ==========================================================

def main():
    parser = argparse.ArgumentParser(description="Villager Enchantment Optimization")
    parser.add_argument("villagers_file", help="Path to named_villagers.json file")
    parser.add_argument("--optimize", action="store_true", help="Run optimization")
    parser.add_argument(
        "--method",
        choices=["min-villagers", "min-cost", "priority-tiered"],
        default="min-villagers",
    )
    parser.add_argument("--p2-threshold", type=int, default=10)
    parser.add_argument("--show-costs", action="store_true", help="Show cost guide")
    parser.add_argument("--show-signs", action="store_true", help="Show sign layout")
    args = parser.parse_args()

    villagers, required, non_enchantments, enchant_priority, enchant_costs = load_data(args.villagers_file)

    if args.show_costs:
        observed = compute_observed_costs(villagers)
        print_cost_guide(enchant_priority, enchant_costs, observed)

    if args.optimize:
        if args.method == "min-villagers":
            optimized = optimize_min_villagers(villagers, required)
            label = "min-villagers (fewest villagers)"
        elif args.method == "min-cost":
            optimized = optimize_min_cost(villagers, required)
            label = "min-cost (cheapest overall)"
        else:
            optimized = optimize_priority_tiered(villagers, required, enchant_priority, args.p2_threshold)
            label = f"priority-tiered (P1 absolute, P2 gap>{args.p2_threshold})"

        emit_optimized_report(label, optimized, villagers, required, non_enchantments, enchant_priority, args.show_signs)
    else:
        villager_enchants = get_villager_enchantments(villagers)
        missing = sorted(required - villager_enchants)
        if missing:
            print("📜 Missing enchantments:")
            for m in missing:
                print(f"- {m}")
        else:
            print("✅ All enchantments are covered!")
        print_all_enchantments(villagers, required)


if __name__ == "__main__":
    main()
