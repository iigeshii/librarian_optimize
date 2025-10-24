import json
from pathlib import Path
import argparse
from collections import defaultdict
import re
import sys

# ----------------------------------------------------------
# Load villager and enchantment data
# named_villagers.json is provided as the required argument
# enchantments.json is expected in the same directory as the script
# ----------------------------------------------------------
def load_data(villagers_file):
    """
    Load villagers (from `villagers_file`) and the master enchantment catalog
    (from `enchantments.json` in the script directory).

    EXPECTED JSON FORMAT (no legacy support):
    {
      "villager_enchantments": [
        { "name": "Mending", "priority": 1 },
        { "name": "Unbreaking III", "priority": 1 },
        ...
      ],
      "non_enchantments": ["Bookshelf", "Lantern", ...]
    }

    Returns:
      villagers: dict
      villager_enchants: set[str]            # set of enchantment names
      non_enchants: set[str]                 # set of non-enchantment item names
      enchant_priority: dict[str, int]       # name -> priority (int; e.g., 1,2,10)
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

    # --- Parse villager_enchantments (required, list of objects)
    raw = master.get("villager_enchantments")
    if not isinstance(raw, list) or not raw:
        raise ValueError("enchantments.json must have a non-empty 'villager_enchantments' list.")

    enchant_priority = {}
    names_seen = set()
    for i, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"'villager_enchantments[{i}]' must be an object with 'name' and 'priority'.")
        name = entry.get("name")
        prio = entry.get("priority")

        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"'villager_enchantments[{i}].name' must be a non-empty string.")
        if name in names_seen:
            raise ValueError(f"Duplicate enchantment name in 'villager_enchantments': '{name}'.")
        if not isinstance(prio, int) or prio < 1:
            raise ValueError(f"'villager_enchantments[{i}].priority' must be an integer >= 1 (got {prio!r}).")

        names_seen.add(name)
        enchant_priority[name] = prio

    villager_enchants = set(names_seen)

    # --- Parse non_enchantments (required, list of strings)
    non_raw = master.get("non_enchantments")
    if not isinstance(non_raw, list) or not all(isinstance(x, str) for x in non_raw):
        raise ValueError("'non_enchantments' must be a list of strings.")
    non_enchants = set(non_raw)

    # --- Validate villagers' data against master lists
    all_master = villager_enchants | non_enchants
    invalid_entries = []
    for v_name, data in villagers.items():
        ench_dict = data.get("enchantments", {})
        if not isinstance(ench_dict, dict):
            raise ValueError(f"Villager '{v_name}' has invalid 'enchantments' (expected object).")
        for ench_name in ench_dict.keys():
            if ench_name not in all_master:
                invalid_entries.append((v_name, ench_name))

    if invalid_entries:
        print("❌ Error: Found unrecognized enchantments in villager data:")
        for v_name, ench in invalid_entries:
            print(f"   - {v_name}: '{ench}' not found in master list")
        print("\n💡 Please fix the villager JSON or update enchantments.json before running again.")
        sys.exit(1)

    return villagers, villager_enchants, non_enchants, enchant_priority


def get_villager_enchantments(villagers):
    all_enchants = set()
    for data in villagers.values():
        all_enchants.update(data["enchantments"].keys())
    return all_enchants


def get_non_enchantment_codes(name, villagers, non_enchantments):
    hints = {
        "Glass": "Glass",
        "Nametag": "Nametag",
        "Bookshelf": "Bookshelf",
        "Lantern": "Lantern",
        "Compass": "Compass",
        "Clock": "Clock",
    }

    def abbreviation(item):
        return hints.get(
            item,
            item[:2].upper() if len(item.split()) == 1 else "".join(word[0] for word in item.split()).upper()
        )

    codes = [
        abbreviation(ench)
        for ench in villagers[name]["enchantments"]
        if ench in non_enchantments
    ]

    return f"({', '.join(codes)})" if codes else ""


def optimize_min_villagers(villagers, required):
    """
    Greedy set cover: pick the villager that covers the most uncovered required enchantments each step.
    Returns: dict name -> {"enchantments": {enchant: price, ...}}
    """
    remaining = set(required)
    optimized = {}

    while remaining:
        best_villager = None
        best_contribution = set()

        for name, data in villagers.items():
            enchants = set(data["enchantments"].keys())
            contribution = enchants & remaining
            if len(contribution) > len(best_contribution):
                best_villager = name
                best_contribution = contribution

        if not best_villager:
            break

        optimized[best_villager] = {
            "enchantments": {
                e: villagers[best_villager]["enchantments"][e]
                for e in best_contribution
            }
        }
        remaining -= best_contribution

    return optimized


def optimize_min_cost(villagers, required):
    """
    Cheapest-per-enchantment: for each required enchantment, choose the villager offering the lowest price.
    Villager count is not considered—cost wins above all else.
    Returns: dict name -> {"enchantments": {enchant: price, ...}}
    """
    result = {}
    for enchant in sorted(required):
        best_name = None
        best_price = float("inf")

        for name, data in villagers.items():
            price = data["enchantments"].get(enchant)
            if price is not None:
                if price < best_price or (price == best_price and (best_name is None or name < best_name)):
                    best_price = price
                    best_name = name

        if best_name is not None:
            result.setdefault(best_name, {"enchantments": {}})
            result[best_name]["enchantments"][enchant] = villagers[best_name]["enchantments"][enchant]
    return result


def optimize_priority_tiered(villagers, required, enchant_priority, p2_threshold=10):
    """
    Priority-aware optimization with a P2 price-gap rule:
      - Priority 1: must be cheapest per enchantment.
      - Priority 2: take cheapest only if:
            (a) the cheapest is already chosen, OR
            (b) the price gap > p2_threshold compared to the best already-chosen villager's price,
                OR if none chosen offer it, compared to the second-cheapest overall.
        Otherwise, defer P2 to the set-cover phase.
      - Priority >2: minimize additional villager count (price ignored).
    Returns: dict name -> {"enchantments": {enchant: price, ...}}
    """
    # Partition required by priority
    p1 = {e for e in required if enchant_priority.get(e, 10) == 1}
    p2 = {e for e in required if enchant_priority.get(e, 10) == 2}
    p_other = set(required) - p1 - p2

    def cheapest_and_second(enchant):
        """Return (best_name, best_price, second_best_price or None)."""
        best_name, best_price = None, float("inf")
        second_price = None
        for name, data in villagers.items():
            price = data["enchantments"].get(enchant)
            if price is None:
                continue
            if price < best_price or (price == best_price and (best_name is None or name < best_name)):
                second_price = best_price if best_price != float("inf") else second_price
                best_name, best_price = name, price
            else:
                if second_price is None or price < second_price:
                    second_price = price
        return best_name, best_price, second_price

    # ---- Step 1: lock in cheapest for P1 (must-have cheapest)
    chosen = {}  # name -> set(enchants)
    for e in sorted(p1):
        v_best, _, _ = cheapest_and_second(e)
        if v_best is None:
            continue
        chosen.setdefault(v_best, set()).add(e)

    # ---- Step 2: P2 rule with price-gap threshold
    for e in sorted(p2):
        v_best, p_best, p_second = cheapest_and_second(e)
        if v_best is None:
            continue

        # Best price among already-chosen villagers (if any)
        p_chosen_best = None
        v_chosen_best = None
        for v in chosen.keys():
            price = villagers[v]["enchantments"].get(e)
            if price is None:
                continue
            if p_chosen_best is None or price < p_chosen_best or (price == p_chosen_best and v < v_chosen_best):
                p_chosen_best = price
                v_chosen_best = v

        if v_best in chosen:
            # Free to add (no new villager)
            chosen[v_best].add(e)
        elif p_chosen_best is not None:
            # Compare chosen-best vs true-best
            if (p_chosen_best - p_best) > p2_threshold:
                # The cheapest is much cheaper: keep him (add a new villager)
                chosen.setdefault(v_best, set()).add(e)
            else:
                # Use the already-chosen villager to avoid adding new
                chosen[v_chosen_best].add(e)
        else:
            # No chosen villager offers it; compare cheapest vs second-cheapest overall
            # If the gap is big, keep the cheapest villager now; else defer to set-cover step
            if p_second is not None and (p_second - p_best) > p2_threshold:
                chosen.setdefault(v_best, set()).add(e)
            # else: do nothing; leave it for the set-cover phase

    # Build initial optimized dict from 'chosen'
    optimized = {}
    for v, ench_set in chosen.items():
        optimized[v] = {"enchantments": {e: villagers[v]["enchantments"][e] for e in ench_set}}

    # ---- Step 3: Greedy set cover to minimize villager count for the rest
    already_assigned = set()
    for data in optimized.values():
        already_assigned.update(data["enchantments"].keys())

    remaining = (p_other | p2 | p1) - already_assigned

    while remaining:
        best_v = None
        best_cov = set()
        for name, data in villagers.items():
            cov = set(data["enchantments"].keys()) & remaining
            if len(cov) > len(best_cov) or (len(cov) == len(best_cov) and best_v is not None and name < best_v):
                best_v = name
                best_cov = cov
        if not best_v or not best_cov:
            break
        optimized.setdefault(best_v, {"enchantments": {}})
        for e in best_cov:
            optimized[best_v]["enchantments"][e] = villagers[best_v]["enchantments"][e]
        remaining -= best_cov

    return optimized


def print_all_enchantments(villagers, required):
    enchant_map = defaultdict(list)
    for name, data in villagers.items():
        for enchant, price in data["enchantments"].items():
            if enchant in required:
                enchant_map[enchant].append(f"{name} ({price})")

    print("\n📘 Enchantment coverage:")
    max_name_len = max(len(name) for name in sorted(required)) if required else 0
    for i, enchant in enumerate(sorted(required)):
        if enchant in enchant_map:
            holders = ", ".join(sorted(enchant_map[enchant]))
            print(f"{i+1:>2}. {enchant:<{max_name_len}} : {holders}")
        else:
            print(f"{i+1:>2}. {enchant:<{max_name_len}} : ❌ None")


def get_enchantment_index(enchantment, required_list):
    """
    Returns the 1-based index of the enchantment/item in the sorted global list.
    """
    sorted_required = sorted(required_list)
    try:
        return sorted_required.index(enchantment) + 1
    except ValueError:
        return None  # or raise an error if preferred


def strip_roman_numerals(name):
    return re.sub(r" [IVXLCDM]+$", "", name)


def emit_optimized_report(method_label, optimized, villagers, required, non_enchantments, enchant_priority):
    def prio_tag(e):
        # only show a priority tag if it's an enchantment (not in non_enchantments)
        if e in non_enchantments:
            return ""
        return f"P{enchant_priority.get(e, '?')}"


    all_names = set(villagers)
    kept = set(optimized)
    removed = sorted(all_names - kept)

    print(f"\n🧠 Optimized villager set ({method_label}):")
    max_name_len = max(len(name) for name in villagers) if villagers else 0
    total_cost = 0
    for i, name in enumerate(sorted(optimized)):
        enchants = optimized[name]["enchantments"]
        # show priority tags next to each enchantment
        ench_str = ", ".join(f"{e} [{prio_tag(e)}] ({c})" for e, c in sorted(enchants.items()))
        total_cost += sum(enchants.values())
        print(f"{i+1:>2}. {name:<{max_name_len}} : {ench_str}")

    # If the method was min-cost, show the total cost for clarity.
    if method_label.startswith("min-cost"):
        print(f"\n💰 Total cost of chosen trades: {total_cost}")

    print("\n🗑 Removed villagers:")
    for name in removed:
        enchants = villagers[name]["enchantments"]
        ench_str = ", ".join(f"{e} [{prio_tag(e)}] ({c})" for e, c in sorted(enchants.items()))
        print(f"- {name}: {ench_str}")

    print("\n📐 Layout:")
    villager_sorted_enchants = {
        name: sorted(optimized[name]["enchantments"].items())
        for name in optimized
    }

    # sort villagers by their first enchant's name for stable order
    sorted_villagers = sorted(
        villager_sorted_enchants.items(),
        key=lambda item: item[1][0][0] if item[1] else ""
    )

    for i, (name, ench_list) in enumerate(sorted_villagers, start=1):
        ench_str = " ".join(
            f"{get_enchantment_index(e, required)}. {strip_roman_numerals(e)}[{prio_tag(e)}]"
            for e, _ in ench_list
        )
        nec = get_non_enchantment_codes(name, villagers, non_enchantments)
        print(f"{i:>2}. {name:{max_name_len}}: {ench_str}{nec}")

    # Build the per-sign lines (kept your existing structure, now with priorities)
    required_dict = {item: "" for item in sorted(required)}

    for villager_name, data in optimized.items():
        sorted_enchants = sorted(data["enchantments"])
        enchant_str = "\n".join(
            f"§b{get_enchantment_index(e, required)}. {strip_roman_numerals(e)} §7[{prio_tag(e)}]"
            for e in sorted_enchants
        )
        codes = get_non_enchantment_codes(villager_name, villagers, non_enchantments)
        if codes:
            enchant_str += f"\n§e{codes}"

        if sorted_enchants:
            required_dict[sorted_enchants[0]] = enchant_str

    for enchant in required_dict:
        if required_dict[enchant] == "":
            for villager_name, data in optimized.items():
                ench_list = sorted(data["enchantments"])
                if enchant in ench_list:
                    first_enchant = ench_list[0]
                    see_index = get_enchantment_index(first_enchant, required)
                    this_index = get_enchantment_index(enchant, required)
                    required_dict[enchant] = (
                        f"§b{this_index}. {strip_roman_numerals(enchant)} §7[{prio_tag(enchant)}] "
                        f"§7§o(See {see_index}. {strip_roman_numerals(first_enchant)})"
                    )
                    break

    print("\n📋 Sign Layout:")
    for enchant, line in required_dict.items():
        villager_name = next(
            (name for name, data in optimized.items() if enchant in data["enchantments"]),
            None
        )
        print(f"------- {villager_name} -------")
        for segment in line.split("\n"):
            print(segment)


def main():
    parser = argparse.ArgumentParser(description="Villager Enchantment Optimization")
    parser.add_argument(
        "villagers_file",
        help="Path to named_villagers.json file"
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Run optimization instead of simple coverage listing"
    )
    parser.add_argument(
        "--method",
        choices=["min-villagers", "min-cost", "priority-tiered"],
        default="priority-tiered",
        help=(
            "Optimization method: 'min-villagers' (fewest villagers), "
            "'min-cost' (cheapest overall), or "
            "'priority-tiered' (P1 cheapest required • P2 cheapest if free • others min villagers)."
        )
    )
    parser.add_argument(
        "--p2-threshold",
        type=int,
        default=10,
        help="Emerald price gap required to justify adding a new villager for Priority-2 enchants (default: 10)."
    )

    args = parser.parse_args()

    # Load data: named_villagers.json from argument, enchantments.json from script dir
    villagers, required, non_enchantments, enchant_priority = load_data(args.villagers_file)

    if args.optimize:
        if args.method == "min-villagers":
            optimized = optimize_min_villagers(villagers, required)
            label = "minimum number of villagers to cover all enchantments"
        elif args.method == "min-cost":
            optimized = optimize_min_cost(villagers, required)
            label = "min-cost (cheapest price per enchantment overall)"
        elif args.method == "priority-tiered":
            optimized = optimize_priority_tiered(villagers, required, enchant_priority, p2_threshold=args.p2_threshold)
            label = (
                f"priority-tiered (P1 cheapest required • "
                f"P2 cheapest if free or gap>{args.p2_threshold} • others min villagers)"
            )

        emit_optimized_report(label, optimized, villagers, required, non_enchantments, enchant_priority)

    else:
        villager_enchants = get_villager_enchantments(villagers)
        missing = sorted(required - villager_enchants)
        if missing:
            print("📜 Missing enchantments from villagers:")
            for m in missing:
                print(f"- {m}")
        else:
            print("✅ All enchantments are covered by the villagers!")

        print_all_enchantments(villagers, required)


if __name__ == "__main__":
    main()
