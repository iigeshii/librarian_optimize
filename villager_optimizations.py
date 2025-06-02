import json
import argparse
from collections import defaultdict

def load_json_file(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: File not found — {filename}")
        return {}
    except json.JSONDecodeError:
        print(f"❌ Error: Could not parse JSON — {filename}")
        return {}

def find_enchantment_coverage(master_file, villagers_file):
    master_data = load_json_file(master_file)
    villagers = load_json_file(villagers_file)

    master_enchants = set(e.strip() for e in master_data.get("villager_enchantments", []))
    enchantment_map = defaultdict(list)  # exact enchantment -> list of villager names

    # Map enchantment to villager if exact match (e.g., only "Sharpness V", not "Sharpness II")
    for villager_name, data in villagers.items():
        for ench in data.get("enchantments", {}):
            ench_clean = ench.strip()
            if ench_clean in master_enchants:
                enchantment_map[ench_clean].append(villager_name)

    found_enchants = set(enchantment_map.keys())
    missing = sorted(master_enchants - found_enchants)
    covered = sorted(master_enchants & found_enchants)

    # Output missing
    print("📜 Missing enchantments from villagers:")
    if missing:
        for enchantment in missing:
            print(f"- {enchantment}")
    else:
        print("✅ All enchantments are covered by your villagers.")

    # Output exact-match coverage
    print("\n📚 Covered enchantments (max level only):")
    for enchantment in covered:
        villager_list = ", ".join(sorted(enchantment_map[enchantment]))
        print(f"- {enchantment}: {villager_list}")

def main():
    parser = argparse.ArgumentParser(
        description="Villager Optimization: Show missing and covered enchantments (max level only)."
    )
    parser.add_argument(
        "--master", default="enchantments.json", help="Path to enchantments master list JSON"
    )
    parser.add_argument(
        "--villagers", default="named_villagers.json", help="Path to named villagers JSON"
    )

    args = parser.parse_args()
    find_enchantment_coverage(args.master, args.villagers)

if __name__ == "__main__":
    main()
