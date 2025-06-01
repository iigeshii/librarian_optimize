import json
import argparse

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

def extract_base_enchant_name(enchant_name):
    # Removes the Roman numeral or level suffix (e.g., "Efficiency V" → "Efficiency")
    return enchant_name.rsplit(" ", 1)[0].strip()

def find_missing_enchantments(master_file, villagers_file):
    master_data = load_json_file(master_file)
    villagers = load_json_file(villagers_file)

    # Collect enchantments from villagers (use full names, e.g. "Sharpness V")
    villager_enchants = set()
    for data in villagers.values():
        for ench in data.get("enchantments", {}):
            villager_enchants.add(ench.strip())

    # Compare to master list (also full names like "Sharpness V")
    master_enchants = set(e.strip() for e in master_data.get("villager_enchantments", []))
    missing = sorted(master_enchants - villager_enchants)

    print("📜 Missing enchantments from villagers:")
    if missing:
        for enchantment in missing:
            print(f"- {enchantment}")
    else:
        print("✅ All enchantments are covered by your villagers.")



def main():
    parser = argparse.ArgumentParser(
        description="Villager Optimization: Find missing enchantments and optimize librarian coverage."
    )
    parser.add_argument(
        "--master", default="enchantments.json", help="Path to enchantments master list JSON"
    )
    parser.add_argument(
        "--villagers", default="named_villagers.json", help="Path to named villagers JSON"
    )

    args = parser.parse_args()
    find_missing_enchantments(args.master, args.villagers)

if __name__ == "__main__":
    main()
