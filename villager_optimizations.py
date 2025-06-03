
import json
from pathlib import Path
import argparse
from collections import defaultdict

def load_data():
    with open("named_villagers.json") as f:
        villagers = json.load(f)
    with open("enchantments.json") as f:
        master = json.load(f)
    return villagers, set(master["villager_enchantments"])

def get_villager_enchantments(villagers):
    all_enchants = set()
    for data in villagers.values():
        all_enchants.update(data["enchantments"].keys())
    return all_enchants

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

def main():
    parser = argparse.ArgumentParser(description="Villager Enchantment Optimization")
    parser.add_argument("--optimize", action="store_true", help="Minimize number of villagers")
    args = parser.parse_args()

    villagers, required = load_data()

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
        for i, name in enumerate(removed):
            enchants = villagers[name]["enchantments"]
            ench_str = ", ".join(f"{e} ({c})" for e, c in enchants.items())
            print(f"{i+1:>2}. {name:<{max_name_len}} : {ench_str}")
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
