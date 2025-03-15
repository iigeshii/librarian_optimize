import json
import pandas as pd
import argparse
from collections import defaultdict

# Load JSON data from file
def load_data(json_file):
    with open(json_file, "r") as file:
        data = json.load(file)
    return data

# Process data into a structured format
def process_data(data):
    villager_enchantments = defaultdict(list)
    enchantment_costs = {}

    for enchantment, villagers in data.items():
        enchantment_costs[enchantment] = []
        for villager, cost in villagers.items():
            villager_id = int(villager)
            villager_enchantments[villager_id].append((enchantment, cost))
            enchantment_costs[enchantment].append((villager_id, cost))

    return villager_enchantments, enchantment_costs

# Optimize for fewest villagers while covering all enchantments
def optimize_villagers(villager_enchantments, enchantment_costs):
    # Sort villagers by number of enchantments they offer (descending)
    sorted_villagers = sorted(villager_enchantments.items(), key=lambda x: len(x[1]), reverse=True)

    selected_villagers = {}
    optimal_set = {}

    for villager, enchantments in sorted_villagers:
        for enchantment, cost in enchantments:
            if enchantment not in optimal_set:
                optimal_set[enchantment] = (villager, cost)
                selected_villagers[villager] = True
            else:
                # If the cost difference is greater than 5, keep the cheaper villager too
                previous_villager, previous_cost = optimal_set[enchantment]
                if cost < previous_cost and (previous_cost - cost) > 5:
                    optimal_set[enchantment] = (villager, cost)
                    selected_villagers[villager] = True
                    selected_villagers[previous_villager] = True  # Keep the more expensive villager too

    return selected_villagers, optimal_set

# Identify disposable villagers
def find_disposable_villagers(villager_enchantments, selected_villagers):
    all_villagers = set(villager_enchantments.keys())
    used_villagers = set(selected_villagers.keys())
    disposable_villagers = all_villagers - used_villagers
    return sorted(disposable_villagers)

# Identify missing enchantments
def find_missing_enchantments(enchantment_costs, optimal_set):
    all_enchantments = set(enchantment_costs.keys())
    selected_enchantments = set(optimal_set.keys())
    missing_enchantments = all_enchantments - selected_enchantments
    return sorted(missing_enchantments)

# Save results to CSV files
def save_results(optimal_set, disposable_villagers, missing_enchantments):
    optimal_df = pd.DataFrame([(key, value[0], value[1]) for key, value in optimal_set.items()],
                              columns=["Enchantment", "Villager_ID", "Cost"])
    disposable_df = pd.DataFrame(disposable_villagers, columns=["Disposable Villager IDs"])
    missing_df = pd.DataFrame(missing_enchantments, columns=["Missing Enchantments"])

    optimal_df.to_csv("optimized_villagers.csv", index=False)
    disposable_df.to_csv("disposable_villagers.csv", index=False)
    missing_df.to_csv("missing_enchantments.csv", index=False)

    print("Results saved to CSV files: optimized_villagers.csv, disposable_villagers.csv, missing_enchantments.csv")

# Main function
def main():
    parser = argparse.ArgumentParser(description="Optimize Minecraft Villager Enchantment Trading.")
    parser.add_argument("json_file", help="Path to the JSON file containing villager enchantment data")
    args = parser.parse_args()

    data = load_data(args.json_file)
    villager_enchantments, enchantment_costs = process_data(data)
    selected_villagers, optimal_set = optimize_villagers(villager_enchantments, enchantment_costs)
    
    disposable_villagers = find_disposable_villagers(villager_enchantments, selected_villagers)
    missing_enchantments = find_missing_enchantments(enchantment_costs, optimal_set)

    save_results(optimal_set, disposable_villagers, missing_enchantments)

# Run the script
if __name__ == "__main__":
    main()
