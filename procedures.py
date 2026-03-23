"""
SagaScape – Tick procedures

Equivalent to NetLogo's ``go`` sub-procedures:
  - exploit_resources
  - burn_resources
  - regenerate
  - disaster
  - add_sites_ACH / add_sites_HELL
"""

# Afkortingen
# r, c    → row, col            : absolute positie in het raster
# nr, nc  → neighbour row/col   : buurpatch (bij brandspreiding)
# br, bc  → burned row/col      : reeds verbrande patch (bij brandspreiding)
# rc      → (row, col) tuple    : een patch als tupel
# idx     → lineaire index      : r * ncols + c
# ! hangt af van welke c (nog aan te passen voor duidelijkheid
# c       → community           : een Community object (NIET col!)
# k       → carrying capacity   : maximale vruchtbaarheid (original_food_value)
# gr      → growth rate         : Verhulst groeisnelheid van een patch
# fert    → food_fertility       : huidige vruchtbaarheid van een patch
# wd      → workdays            : arbeidsdagen
# frr     → fire_return_rate    : gemiddelde tijd tussen branden

from __future__ import annotations

import numpy as np
from configuration import PARAMS
from world import World
from communities import Community


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cost_for_community(world: World,
                         community: Community,
                         row: int, col: int) -> float:
    """Return the least-cost distance from community to patch (r,c)."""
    idx = world.idx(row, col)
    try:
        pos = world.in_range_of[idx].index(community)
        return world.claimed_cost[idx][pos]
    except (KeyError, ValueError):
        return np.inf


def _candidate_list(world: World,
                    community: Community) -> list[tuple[int, int]]:
    """Return community's candidate patches that still exist (no community on them)."""
    return [rc for rc in community.candidate_patches if world.land[rc[0], rc[1]]]



# 1. Exploit resources


def exploit_resources(world: World,
                      communities: list[Community],
                      bad_harvest_modifier: float,
                      params=PARAMS) -> None:
    """
    Three-pass exploitation: food → wood → clay.
    Equivalent to NetLogo's ``exploit-resources``.
    """
    rng = np.random.default_rng()

    active = [c for c in communities if c.active]

    # FOOD
    for community in active:
        candidates = _candidate_list(world, community)
        security_factor = 1.0 + rng.random()

        # Sort: best food_fertility / cost ratio first
        def food_score(rc):
            r, c = rc
            cost = _cost_for_community(world, community, r, c)
            if cost == 0 or cost == np.inf:
                return -np.inf
            return world.food_fertility[r, c] / cost

        sorted_patches = sorted(
            candidates,
            key=food_score,
            reverse=True
        )

        target_food = (community.food_requirement
                       * security_factor
                       * community.grain_per_grain_factor)

        idx_ptr = 0
        while (community.food_stock < target_food
               and idx_ptr < len(sorted_patches)
               and community.food_workdays > 0):

            r, c = sorted_patches[idx_ptr]
            idx_ptr += 1

            if world.food_fertility[r, c] <= 0:
                continue

            cost          = _cost_for_community(world, community, r, c)
            food_exploited = world.food_fertility[r, c]
            wood_from_field= world.wood_standing_stock[r, c]

            # Exploit patch
            world.food_fertility[r, c]      = 0.0
            world.wood_standing_stock[r, c] = 0.0
            world.wood_age[r, c]            = 0.0
            world.wood_flag[r, c]           = False
            world.food_flag[r, c]           = True
            world.time_since_abandonment[r, c] = 0

            # Workdays: 42 person-days/ha + travel
            travel_workdays = 42 + 42 * 2 * cost / 10
            community.food_workdays -= travel_workdays
            community.workdays      -= travel_workdays
            community.saved_food_workdays += travel_workdays

            community.food_stock           += food_exploited
            community.cumulative_food_stock += food_exploited
            community.total_food_effort    += cost

            # Incidental wood from clearing the field
            if wood_from_field > 0:
                head_load = max(rng.normal(29.21, 14.14), 4.5) / 695
                hl_time   = 49.0
                trips     = wood_from_field / head_load - 2
                wd_defor  = trips * (2 * cost + head_load * hl_time) / 10
                community.wood_stock           += wood_from_field
                community.cumulative_wood_stock += wood_from_field
                community.total_wood_effort    += cost
                community.workdays             -= wd_defor
                community.saved_wood_workdays  += wd_defor

        # Apply bad harvest
        community.food_stock *= bad_harvest_modifier

    # WOOD
    for community in active:
        candidates = _candidate_list(world, community)
        head_load  = max(rng.normal(29.21, 14.14), 4.5) / 695
        hl_time    = 49.0

        def wood_score(rc):
            r, c = rc
            cost = _cost_for_community(world, community, r, c)
            if cost == 0 or cost == np.inf:
                return -np.inf
            return world.wood_standing_stock[r, c] / cost

        sorted_patches = sorted(candidates, key=wood_score, reverse=True)
        idx_ptr = 0

        while (community.wood_stock < community.wood_requirement
               and idx_ptr < len(sorted_patches)
               and community.workdays > 0):

            r, c = sorted_patches[idx_ptr]
            idx_ptr += 1

            if world.wood_standing_stock[r, c] <= 0:
                continue

            cost          = _cost_for_community(world, community, r, c)
            wood_exploited = world.wood_standing_stock[r, c]

            world.wood_standing_stock[r, c] = 0.0
            world.wood_age[r, c]            = 0.0

            trips   = wood_exploited / head_load
            wd_defor= trips * (2 * cost + head_load * hl_time) / 10
            community.workdays             -= wd_defor
            community.saved_wood_workdays  += wd_defor

            community.wood_stock           += wood_exploited
            community.cumulative_wood_stock += wood_exploited
            community.total_wood_effort    += cost

    #CLAY
    for community in active:
        community.wood_for_clay = 0.0
        candidates = [rc for rc in _candidate_list(world, community)
                      if world.clay_flag[rc[0], rc[1]]]

        def clay_score(rc):
            r, c = rc
            cost = _cost_for_community(world, community, r, c)
            if cost == 0 or cost == np.inf:
                return -np.inf
            return world.clay_quantity[r, c] / cost

        sorted_patches = sorted(candidates, key=clay_score, reverse=True)
        idx_ptr = 0

        while (community.clay_stock < community.clay_requirement
               and idx_ptr < len(sorted_patches)
               and community.workdays > 0):

            r, c = sorted_patches[idx_ptr]
            idx_ptr += 1

            if not world.clay_flag[r, c]:
                continue

            cost = _cost_for_community(world, community, r, c)
            clay_exploited = 19.0   # 10 m³ × 1.9 t/m³

            world.clay_quantity[r, c] -= clay_exploited
            thresh = params.clay_threshold * 10000 * 2
            if world.clay_quantity[r, c] < thresh:
                world.clay_flag[r, c] = False

            wood_from_field = world.wood_standing_stock[r, c]
            world.food_fertility[r, c]      = 0.0
            world.wood_standing_stock[r, c] = 0.0
            world.wood_age[r, c]            = 0.0
            world.wood_flag[r, c]           = False
            world.food_flag[r, c]           = False

            # Workdays for quarrying
            wd_quarried = 0.193 * clay_exploited / 1.9
            baskets = clay_exploited / 0.05
            wd_hauling = baskets * cost * 2 * 6.5 / 10
            wd_fired = 4.5 / 0.980 * clay_exploited
            total_clay_wd = wd_quarried + wd_hauling + wd_fired

            community.workdays -= total_clay_wd
            community.saved_clay_workdays += total_clay_wd
            community.clay_stock += clay_exploited
            community.cumulative_clay_stock += clay_exploited
            community.total_clay_effort += cost
            community.wood_for_clay += (clay_exploited
                                           * params.kgs_wood_per_kg_clay
                                           * 1000 / 695)

            # Incidental wood from clay patch
            if wood_from_field > 0:
                head_load = max(rng.normal(29.21, 14.14), 4.5) / 695
                hl_time = 49.0
                trips = wood_from_field / head_load - 2
                wd_defor = trips * (2 * cost + head_load * hl_time) / 10
                community.wood_stock += wood_from_field
                community.cumulative_wood_stock += wood_from_field
                community.total_wood_effort += cost
                community.workdays -= wd_defor
                community.saved_wood_workdays += wd_defor



# 2. Burn resources (community consumption)

def burn_resources(communities: list[Community]) -> None:
    """
    Deduct annual consumption from stocks.
    Equivalent to NetLogo's ``burn-resources``.
    """
    for c in [c for c in communities if c.active]:
        c.food_stock = c.food_stock / c.grain_per_grain_factor - c.food_requirement
        c.wood_stock = c.wood_stock - c.wood_requirement - c.wood_for_clay
        c.clay_stock = c.clay_stock - c.clay_requirement


# 3. Regenerate

def regenerate(world: World, params=PARAMS) -> None:
    """
    Regrow food fertility (Verhulst) and forest standing stock.
    Equivalent to NetLogo's ``regenerate``.
    """
    #  Food fertility (Verhulst growth)
    food_mask = world.food_flag & ~world.wood_flag & world.land
    rows, cols = np.where(food_mask)
    for r, c in zip(rows, cols):
        world.time_since_abandonment[r, c] += 1
        fert  = world.food_fertility[r, c]
        k     = world.original_food_value[r, c]
        gr    = world.growth_rate[r, c]

        if fert < k:
            if fert > 0:
                regen = ((1 - fert / k)
                         / (1 / k + gr / (fert * (1 - gr))))
                world.food_fertility[r, c] += regen
            else:
                world.food_fertility[r, c] = 0.1  # regeneration_reserve

    #   Wood standing stock
    world.wood_update_standing_stock()

    #  Reset community workdays
    # (done in main loop after regenerate to keep function pure)


def reset_community_workdays(communities: list[Community],
                              params=PARAMS) -> None:
    """
    Reset annual workday budgets.
    Called at end of each tick in the main loop.
    """
    for c in [c for c in communities if c.active]:
        debt_wd  = min(c.workdays, 0)
        debt_fwd = min(c.food_workdays, 0)
        c.workdays      = (c.population * params.active_percentage / 100 * 365
                           + debt_wd)
        c.food_workdays = (c.population * params.active_percentage / 100
                           * params.agricultural_days + debt_fwd)


# 4. Disaster (fire + bad harvest)

def disaster(world: World, params=PARAMS) -> float:
    """
    Forest fires and occasional bad harvests.
    Equivalent to NetLogo's ``disaster``.
    Returns bad_harvest_modifier for this tick (1.0 normally, 0.5 if bad year).
    """
    rng = np.random.default_rng()
    drought = rng.random()

    #  Ignition
    fire_starts = []
    rows, cols = np.where(world.wood_standing_stock > 0.72)

    for r, c in zip(rows, cols):
        frr   = world.fire_return_rate[r, c]
        p_base = 1.0 / (frr * 4) if frr > 0 else 0
        odds  = p_base / (1 - p_base) * drought if p_base < 1 else drought
        p_ign = odds / (1 + odds)
        if p_ign > rng.random():
            world.wood_standing_stock[r, c] = 0.0
            world.wood_age[r, c]            = 0.0
            world.time_since_fire[r, c]     = 0.0
            fire_starts.append((r, c))

    #  Spread
    for start in fire_starts:
        # max-fire-size: exponential with mean 4 ha
        u = rng.random()
        u = max(u, 1e-10)
        max_size = -4 * np.log10(1 - u) if u < 1 else 4

        if max_size <= 1:
            world.burn_size.append(1)
            continue

        burned = {start}
        while (len(burned) <= max_size
               and rng.random() > 0.1):
            # Find peripheral wooded patches (4-neighbours of burned set)
            peripheral = set()
            for br, bc in burned:
                for nr, nc in world.neighbors4(br, bc):
                    if (nr, nc) not in burned and world.wood_standing_stock[nr, nc] > 0.72:
                        peripheral.add((nr, nc))
            if not peripheral:
                break
            new_patch = list(peripheral)[rng.integers(len(peripheral))]
            nr, nc = new_patch
            world.wood_standing_stock[nr, nc] = 0.0
            world.wood_age[nr, nc]            = 0.0
            world.time_since_fire[nr, nc]     = 0.0
            burned.add(new_patch)

        world.burn_size.append(len(burned))

    #  Bad harvest
    bad_harvest_modifier = 1.0
    if rng.poisson(1 / (1 + params.bad_harvest_interval)) > 0:
        bad_harvest_modifier = 0.5

    return bad_harvest_modifier


# 5. Periodisation events

def add_sites(communities: list[Community],
              world: World,
              period: str) -> None:
    """
    Activate communities that belong to a given period.
    Equivalent to ``add-sites-ACH`` and ``add-sites-HELL``.
    """
    for c in communities:
        if not c.active and c.start_period == period:
            c.active = True
            r, col = c.patch_row_col()
            if world.valid(r, col):
                world.wood_max_stock[r, col] = 0.0
                world.food_fertility[r, col] = 0.0
                world.wood_flag[r, col]      = False
                world.food_flag[r, col]      = False
                world.clay_flag[r, col]      = False
    n = sum(1 for c in communities if c.active and c.start_period == period)
    print(f"  Added {n} {period} communities.")
