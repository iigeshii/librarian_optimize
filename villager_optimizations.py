#!/usr/bin/env python3
"""
villager_optimizations.py

Goal (Gesh rules):
- ONLY trades with cost == 1 are considered usable.
- Find the SMALLEST set of librarians that covers everything that is currently obtainable at cost==1.
- Also report which goal enchantments are currently missing (no cost==1 source exists).
- Also list which villagers are extraneous (not needed for the best cost==1 coverage set).

Input files:
1) named_villagers.json (you pass this path)
   {
     "Alden": {
       "cured": true|false (optional),
       "enchantments": {
          "Mending": 1,
          "Silk Touch I": 1,
          "Unbreaking III": {"pre": 9, "post": 1},
          "Lantern": 1,
          ...
       }
     },
     ...
   }

2) enchantments.json (default: same folder as this script, or pass --enchantments)
   {
     "villager_enchantments": [
       {"name":"Aqua Affinity", "active": true},
       {"name":"Curse of Binding", "active": true},
       ...
     ],
     "non_enchantments": ["Bookshelf","Lantern","Glass","Compass","Clock"]
   }

Notes:
- Unknown keys in named_villagers.json are ignored (never fatal).
- We DO NOT "strip roman numerals" globally because that can corrupt levels (Sharpness II vs Sharpness V).
- We DO apply safe aliases for single-level enchants + common “I” formatting (Mending I -> Mending, etc.).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any, List, Tuple, Set, Optional


# -----------------------------
# Safe key normalization
# -----------------------------

ALIASES = {
    # Single-level enchants (often stored with trailing " I")
    "Aqua Affinity I": "Aqua Affinity",
    "Channeling I": "Channeling",
    "Curse of Binding I": "Curse of Binding",
    "Curse of Vanishing I": "Curse of Vanishing",
    "Flame I": "Flame",
    "Infinity I": "Infinity",
    "Mending I": "Mending",
    "Multishot I": "Multishot",
    "Silk Touch I": "Silk Touch",
}


def normalize_key(key: str) -> str:
    key = key.strip()
    return ALIASES.get(key, key)


# -----------------------------
# Price handling
# -----------------------------

def current_price_for(villagers: Dict[str, Any], villager_name: str, enchantment: str) -> Optional[int]:
    """
    Returns the effective price for a villager's enchantment entry.

    Supports:
      - int
      - {"pre": int|'X'|None, "post": int|'X'|None}

    If villager has "cured": true, uses "post", else "pre".
    Returns None if no usable price exists.
    """
    ench_dict = villagers[villager_name].get("enchantments", {})
    raw = ench_dict.get(enchantment)

    # Try alias lookup if not found
    if raw is None:
        # if stored as e.g. "Mending I" but requested as "Mending" etc.
        for k, v in ench_dict.items():
            if normalize_key(k) == enchantment:
                raw = v
                break

    if raw is None:
        return None

    if isinstance(raw, int):
        return raw

    if isinstance(raw, dict):
        cured = bool(villagers[villager_name].get("cured"))
        val = raw.get("post" if cured else "pre")
        if val in (None, "X"):
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    return None


# -----------------------------
# Loading
# -----------------------------

def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_master_enchantments(enchantments_path: Path) -> Tuple[List[str], List[str]]:
    """
    Returns:
      required_enchantments (active only)
      non_enchantments (as-is list, optional)
    """
    master = load_json(enchantments_path)

    raw = master.get("villager_enchantments")
    if not isinstance(raw, list) or not raw:
        raise ValueError("enchantments.json must include a non-empty 'villager_enchantments' list.")

    required: List[str] = []
    seen: Set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Each entry in 'villager_enchantments' must be an object.")
        if not entry.get("active", True):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each enchantment entry must have a non-empty string 'name'.")
        name = name.strip()
        if name in seen:
            raise ValueError(f"Duplicate enchantment in master list: '{name}'")
        seen.add(name)
        required.append(name)

    non_raw = master.get("non_enchantments", [])
    if non_raw is None:
        non_raw = []
    if not isinstance(non_raw, list) or not all(isinstance(x, str) for x in non_raw):
        raise ValueError("'non_enchantments' must be a list of strings if present.")
    non_enchants = [x.strip() for x in non_raw if x.strip()]

    return required, non_enchants


def load_villagers(villagers_path: Path) -> Dict[str, Any]:
    villagers = load_json(villagers_path)
    if not isinstance(villagers, dict):
        raise ValueError("Villagers file must be a JSON object keyed by villager name.")
    # light validation
    for v_name, data in villagers.items():
        if not isinstance(data, dict):
            raise ValueError(f"Villager '{v_name}' must be an object.")
        ench = data.get("enchantments", {})
        if not isinstance(ench, dict):
            raise ValueError(f"Villager '{v_name}': 'enchantments' must be an object.")
    return villagers


def warn_unknown_keys(villagers: Dict[str, Any], required_set: Set[str], non_set: Set[str], warn_limit: int = 40) -> None:
    allowed = required_set | non_set
    unknown: List[Tuple[str, str]] = []
    for v_name, data in villagers.items():
        for k in data.get("enchantments", {}).keys():
            kk = normalize_key(k)
            if kk not in allowed:
                unknown.append((v_name, k))
    if unknown:
        print("ℹ️ Ignoring non-master entries found in villagers file (not used for optimization):")
        for v, k in unknown[:warn_limit]:
            print(f"  - {v}: '{k}'")
        if len(unknown) > warn_limit:
            print(f"  ... and {len(unknown) - warn_limit} more")


# -----------------------------
# Cost==1 masks
# -----------------------------

def build_cost1_masks(villagers: Dict[str, Any], required: List[str]) -> Tuple[List[str], Dict[str, int], List[Tuple[str, int]], int]:
    """
    Returns:
      req_list: sorted required enchantments
      req_index: mapping enchant -> bit index
      villager_masks: list of (villager_name, mask) where mask is for cost==1 covered enchants
      full_mask: all required bits set
    """
    req_list = sorted(required, key=str.lower)
    req_index = {e: i for i, e in enumerate(req_list)}
    full_mask = (1 << len(req_list)) - 1

    villager_masks: List[Tuple[str, int]] = []
    for v_name in sorted(villagers.keys(), key=str.lower):
        mask = 0
        for e in req_list:
            if current_price_for(villagers, v_name, e) == 1:
                mask |= (1 << req_index[e])
        if mask:
            villager_masks.append((v_name, mask))

    return req_list, req_index, villager_masks, full_mask


# -----------------------------
# Exact minimum set cover (branch & bound)
# -----------------------------

def solve_min_set_cover_exact(villager_masks: List[Tuple[str, int]], target_mask: int) -> Optional[List[str]]:
    """
    Exact minimum set cover on bitmasks.

    Returns list of villager names that covers target_mask with minimum size.
    Returns [] if target_mask == 0.
    Returns None if impossible (shouldn't happen if target_mask derived from OR of masks).
    """
    if target_mask == 0:
        return []

    items = sorted(villager_masks, key=lambda t: t[1].bit_count(), reverse=True)

    # Greedy upper bound for pruning
    def greedy_upper_bound() -> Optional[List[int]]:
        remaining = target_mask
        chosen: List[int] = []
        while remaining:
            best_i = None
            best_gain = 0
            for i, (_, m) in enumerate(items):
                gain = (m & remaining).bit_count()
                if gain > best_gain:
                    best_gain = gain
                    best_i = i
            if best_i is None or best_gain == 0:
                return None
            chosen.append(best_i)
            remaining &= ~items[best_i][1]
        return chosen

    best_idx = greedy_upper_bound()
    best_len = len(best_idx) if best_idx else float("inf")
    best_solution: Optional[List[int]] = best_idx[:] if best_idx else None

    max_cover = max((m.bit_count() for _, m in items), default=0)
    if max_cover == 0:
        return None

    bit_to_items: Dict[int, List[int]] = defaultdict(list)
    for i, (_, m) in enumerate(items):
        mm = m
        while mm:
            lsb = mm & -mm
            b = lsb.bit_length() - 1
            bit_to_items[b].append(i)
            mm -= lsb

    def pick_mrv_bit(remaining: int) -> Optional[int]:
        mm = remaining
        best_b = None
        best_c = 10**9
        while mm:
            lsb = mm & -mm
            b = lsb.bit_length() - 1
            c = len(bit_to_items.get(b, []))
            if c < best_c:
                best_b, best_c = b, c
                if c <= 1:
                    break
            mm -= lsb
        return best_b

    def dfs(chosen: List[int], covered: int) -> None:
        nonlocal best_solution, best_len

        if covered == target_mask:
            if len(chosen) < best_len:
                best_len = len(chosen)
                best_solution = chosen[:]
            return

        if len(chosen) >= best_len:
            return

        remaining = target_mask & ~covered
        rem_bits = remaining.bit_count()

        # optimistic lower bound
        lower = (rem_bits + max_cover - 1) // max_cover
        if len(chosen) + lower >= best_len:
            return

        b = pick_mrv_bit(remaining)
        if b is None:
            return

        candidates = bit_to_items.get(b, [])
        if not candidates:
            return

        # try best gain first
        candidates = sorted(
            candidates,
            key=lambda i: (items[i][1] & remaining).bit_count(),
            reverse=True
        )

        for i in candidates:
            new_cov = covered | items[i][1]
            if new_cov == covered:
                continue
            dfs(chosen + [i], new_cov)

    dfs([], 0)

    if best_solution is None:
        return None
    return [items[i][0] for i in best_solution]


# -----------------------------
# Best-possible under cost==1
# -----------------------------

def optimize_cost1_best_possible(villagers: Dict[str, Any], required: List[str]) -> Tuple[List[str], Set[str], Set[str]]:
    """
    Returns:
      solution_names: minimum villagers covering ALL obtainable-at-cost==1 enchants
      obtainable: enchants that exist at cost==1 on at least one villager
      missing: required enchants with no cost==1 source
    """
    req_list, req_index, villager_masks, full_mask = build_cost1_masks(villagers, required)

    obtainable_mask = 0
    for _, m in villager_masks:
        obtainable_mask |= m

    obtainable = {e for e in req_list if (obtainable_mask >> req_index[e]) & 1}
    missing = set(req_list) - obtainable

    solution = solve_min_set_cover_exact(villager_masks, obtainable_mask)
    if solution is None:
        solution = []

    return solution, obtainable, missing


# -----------------------------
# Reporting
# -----------------------------

def report_cost1_best_possible(
    villagers: Dict[str, Any],
    required: List[str],
    non_enchants: List[str],
    solution: List[str],
    obtainable: Set[str],
    missing: Set[str]
) -> None:
    required_sorted = sorted(required, key=str.lower)

    print("\n📌 Rule: ONLY cost == 1 trades count.\n")

    if missing:
        print("❌ Missing (no villager currently offers cost==1 for these goal enchantments):")
        for e in sorted(missing, key=str.lower):
            print(f" - {e}")
    else:
        print("✅ Nothing missing under cost==1 (full coverage achievable right now).")

    print("\n✅ Current best set (minimum villagers covering ALL cost==1 obtainable goal enchantments):")
    if not solution:
        print("  (none) — you currently have zero goal enchantments available at cost==1.")
    else:
        for i, v in enumerate(solution, 1):
            covered = [e for e in required_sorted if current_price_for(villagers, v, e) == 1]
            print(f"{i:>2}. {v}: {', '.join(covered)}")

    # Extraneous villagers
    sol_set = set(solution)
    extras = sorted(set(villagers.keys()) - sol_set, key=str.lower)

    print("\n🗑 Extraneous villagers (not needed for best cost==1 coverage):")
    if not extras:
        print("  (none)")
    else:
        for v in extras:
            cost1_goals = [e for e in required_sorted if current_price_for(villagers, v, e) == 1]
            if cost1_goals:
                # This shouldn't happen if solver is truly minimal, but it can if there are multiple equally-minimal solutions.
                print(f" - {v}: (has cost==1 goals too) {', '.join(cost1_goals)}")
            else:
                print(f" - {v}")

    # Optional: non-enchantment trades of interest, just echoed for convenience
    if non_enchants:
        print("\n🧾 Librarian non-enchantments of interest (ignored for optimization):")
        print(" - " + "\n - ".join(non_enchants))


# -----------------------------
# CLI
# -----------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find the minimum number of librarians needed under 'cost==1 only'. Reports missing and extraneous."
    )
    parser.add_argument("villagers_file", help="Path to named_villagers.json")
    parser.add_argument(
        "--enchantments",
        default=None,
        help="Path to enchantments.json (default: enchantments.json next to this script)",
    )
    parser.add_argument(
        "--no-warn-unknown",
        action="store_true",
        help="Do not print warnings about unknown keys in villagers file.",
    )
    args = parser.parse_args()

    villagers_path = Path(args.villagers_file)
    if args.enchantments:
        ench_path = Path(args.enchantments)
    else:
        ench_path = Path(__file__).resolve().parent / "enchantments.json"

    if not villagers_path.exists():
        print(f"❌ Missing villagers file: {villagers_path}")
        sys.exit(1)
    if not ench_path.exists():
        print(f"❌ Missing enchantments file: {ench_path}")
        sys.exit(1)

    villagers = load_villagers(villagers_path)
    required, non_enchants = load_master_enchantments(ench_path)

    required_set = set(required)
    non_set = set(non_enchants)

    if not args.no_warn_unknown:
        warn_unknown_keys(villagers, required_set, non_set)

    solution, obtainable, missing = optimize_cost1_best_possible(villagers, required)

    report_cost1_best_possible(villagers, required, non_enchants, solution, obtainable, missing)


if __name__ == "__main__":
    main()
