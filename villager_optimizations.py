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
    villagers_path = Path(villagers_file)
    enchants_path = Path(__file__).parent / "enchantments.json"

    if not villagers_path.exists():
        raise FileNotFoundError(f"Missing file: {villagers_path}")
    if not enchants_path.exists():
        raise FileNotFoundError(f"Missing file: {enchants_path}")

    with open(villagers_path) as f:
        villagers = json.load(f)
    with open(enchants_path) as f:
        master = json.load(f)

    villager_enchants = set(master["villager_enchantments"])
    non_enchants = set(master["non_enchantments"])
    all_master_enchants = villager_enchants | non_enchants

    # ✅ Validation: make sure no villager has invalid enchantments
    invalid_entries = []
    for name, data in villagers.items():
        for enchant in data.get("enchantments", {}):
            if enchant not in all_master_enchants:
                invalid_entries.append((name, enchant))

    if invalid_entries:
        print("❌ Error: Found unrecognized enchantments in villager data:")
        for name, enchant in invalid_entries:
            print(f"   - {name}: '{enchant}' not found in master list")
        print("\n💡 Please fix the villager JSON or update enchantments.json before running again.")
        sys.exit(1)

    return villagers, villager_enchants, non_enchants


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
        return hints.get(item, item[:2].upper() if len(item.split()) == 1 else "".join(word[0] for word in item.split()).upper())

    codes = [
        abbreviation(ench)
        for ench in villagers[name]["enchantments"]
        if ench in non_enchantments
    ]

    return f"({', '.join(codes)})" if codes else ""


def optimize_min_villagers(villagers, required):
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


def print_all_enchantments(villagers, required):
    enchant_map = defaultdict(list)
    for name, data in villagers.items():
        for enchant, price in data["enchantments"].items():
            if enchant in required:
                enchant_map[enchant].append(f"{name} ({price})")

    print("\n📘 Enchantment coverage:")
    max_name_len = max(len(name) for name in sorted(required))
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


def main():
    parser = argparse.ArgumentParser(description="Villager Enchantment Optimization")
    parser.add_argument(
        "villagers_file",
        help="Path to named_villagers.json file"
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Minimize number of villagers"
    )
    args = parser.parse_args()

    # Load data: named_villagers.json from argument, enchantments.json from script dir
    villagers, required, non_enchantments = load_data(args.villagers_file)

    if args.optimize:
        optimized = optimize_min_villagers(villagers, required)
        all_names = set(villagers)
        kept = set(optimized)
        removed = sorted(all_names - kept)

        print("\n🧠 Optimized villager set (minimum number of villagers to cover all enchantments):")
        max_name_len = max(len(name) for name in villagers)
        for i, name in enumerate(sorted(optimized)):
            enchants = optimized[name]["enchantments"]
            ench_str = ", ".join(f"{e} ({c})" for e, c in enchants.items())
            print(f"{i+1:>2}. {name:<{max_name_len}} : {ench_str}")

        print("\n🗑 Removed villagers:")
        for name in removed:
            enchants = villagers[name]["enchantments"]
            ench_str = ", ".join(f"{e} ({c})" for e, c in enchants.items())
            print(f"- {name}: {ench_str}")

        print("\n📐 Layout:")
        villager_sorted_enchants = {
            name: sorted(optimized[name]["enchantments"].items())
            for name in optimized
        }

        sorted_villagers = sorted(
            villager_sorted_enchants.items(),
            key=lambda item: item[1][0][0] if item[1] else ""
        )

        for i, (name, ench_list) in enumerate(sorted_villagers, start=1):
            ench_str = " ".join(
                f"{get_enchantment_index(e, required)}. {strip_roman_numerals(e)}"
                for e, _ in ench_list
            )
            nec = get_non_enchantment_codes(name, villagers, non_enchantments)
            print(f"{i:>2}. {name:{max_name_len}}: {ench_str}{nec}")

        required_dict = {item: "" for item in sorted(required)}

        for villager_name, data in optimized.items():
            sorted_enchants = sorted(data["enchantments"])
            enchant_str = "\n".join(
                f"§b{get_enchantment_index(e, required)}. {strip_roman_numerals(e)}"
                for e in sorted_enchants)
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
                        required_dict[enchant] = f"§b{this_index}. {strip_roman_numerals(enchant)} §7§o(See {see_index}. {strip_roman_numerals(first_enchant)})"
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
