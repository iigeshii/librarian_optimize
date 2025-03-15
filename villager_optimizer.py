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
def optimize_villagers(villager_enchantments, enchantment_costs, cost_threshold):
    sorted_villagers = sorted(villager_enchantments.items(), key=lambda x: len(x[1]), reverse=True)

    selected_villagers = {}
    optimal_set = {}

    for villager, enchantments in sorted_villagers:
        for enchantment, cost in enchantments:
            if enchantment not in optimal_set:
                optimal_set[enchantment] = (villager, cost)
                selected_villagers[villager] = True
            else:
                previous_villager, previous_cost = optimal_set[enchantment]
                if cost < previous_cost and (previous_cost - cost) > cost_threshold:
                    optimal_set[enchantment] = (villager, cost)
                    selected_villagers[villager] = True
                    selected_villagers[previous_villager] = True

    return selected_villagers, optimal_set

# Get the absolute best possible cost per enchantment
def get_best_costs(enchantment_costs):
    best_costs = {}
    for enchantment, costs in enchantment_costs.items():
        best_costs[enchantment] = min(cost for _, cost in costs) if costs else None
    return best_costs

# Identify disposable villagers
def find_disposable_villagers(villager_enchantments, selected_villagers):
    all_villagers = set(villager_enchantments.keys())
    used_villagers = set(selected_villagers.keys())
    return sorted(all_villagers - used_villagers)

# Identify missing enchantments
def find_missing_enchantments(enchantment_costs, optimal_set):
    all_enchantments = set(enchantment_costs.keys())
    selected_enchantments = set(optimal_set.keys())
    return sorted(all_enchantments - selected_enchantments)

# Save results to CSV files and print results to console
def save_and_display_results(optimal_set, disposable_villagers, missing_enchantments, best_costs):
    optimal_data = []
    
    for enchantment, (villager, cost) in optimal_set.items():
        best_cost = best_costs[enchantment]
        best_cost_display = f"*{best_cost}" if best_cost != cost else f"{best_cost}"
        optimal_data.append((enchantment, villager, cost, best_cost_display))
    
    optimal_df = pd.DataFrame(optimal_data, columns=["Enchantment", "Villager_ID", "Cost", "Best Cost"])
    optimal_df.to_csv("optimized_villagers.csv", index=False)

    print("\n" + "="*60)
    print("   OPTIMIZED VILLAGER SELECTION (WITH BEST COST)")
    print("="*60)
    print(optimal_df.to_string(index=False))

    print("\n" + "="*40)
    print("   DISPOSABLE VILLAGERS")
    print("="*40)
    if disposable_villagers:
        print("\n".join(map(str, disposable_villagers)))
    else:
        print("No villagers can be removed.")

    print("\n" + "="*40)
    print("   MISSING ENCHANTMENTS")
    print("="*40)
    if missing_enchantments:
        print("\n".join(missing_enchantments))
    else:
        print("All enchantments are covered.")

    print("\nResults saved to: optimized_villagers.csv")

# Main function
def main():
    parser = argparse.ArgumentParser(description="Optimize Minecraft Villager Enchantment Trading.")
    parser.add_argument("json_file", help="Path to the JSON file containing villager enchantment data")
    parser.add_argument("--cost-threshold", type=int, default=5, help="Threshold for cost savings before keeping a second villager")
    args = parser.parse_args()

    data = load_data(args.json_file)
    villager_enchantments, enchantment_costs = process_data(data)
    best_costs = get_best_costs(enchantment_costs)
    
    selected_villagers, optimal_set = optimize_villagers(villager_enchantments, enchantment_costs, args.cost_threshold)

    disposable_villagers = find_disposable_villagers(villager_enchantments, selected_villagers)
    missing_enchantments = find_missing_enchantments(enchantment_costs, optimal_set)

    save_and_display_results(optimal_set, disposable_villagers, missing_enchantments, best_costs)

# Run the script
if __name__ == "__main__":
    main()
