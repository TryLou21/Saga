"""
SagaScape (Agents/communities)
Community and InactiveCommunity agents (eq to NetLogo breeds)
"""

# Afkortingen
# c         → community  : een Community object (in loops en metrics)
# col       → x-positie  : kolomindex in het raster (= NetLogo xcor)
# row       → y-positie  : rijindex in het raster   (= NetLogo ycor)
# mu, sigma → gemiddelde / standaardafwijking voor populatiegeneratie

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Community:
    """
    Equivalent to the ``communities`` breed in NetLogo.
    All numeric attributes mirror the NetLogo ``communities-own`` block.
    """
    # Identity
    who: int                      # unique agent ID
    site_name: str = ""
    settlement_type: str = ""     # "hamlet" | "village" | "town"
    start_period: str = "IA"      # "IA" | "ACH" | "HELL"
    active: bool = True

    # Spatial position (col = x, row = y in raster coords)
    col: float = 0.0
    row: float = 0.0

    # Population & labour
    population: int   = 0
    workdays: float = 0.0
    food_workdays: float = 0.0

    # Requirements (per year)
    food_requirement: float = 0.0
    wood_requirement: float = 0.0
    clay_requirement: float = 0.0
    wood_for_clay: float = 0.0

    # Stocks (reset every tick, except cumulative)
    food_stock: float = 0.0
    wood_stock: float = 0.0
    clay_stock: float = 0.0

    # Cumulative totals (never reset)
    cumulative_food_stock: float = 0.0
    cumulative_wood_stock: float = 0.0
    cumulative_clay_stock: float = 0.0

    # Effort (total walking-time cost)
    total_food_effort: float = 0.0
    total_wood_effort: float = 0.0
    total_clay_effort: float = 0.0

    # Saved workdays (cumulative)
    saved_food_workdays: float = 0.0
    saved_wood_workdays: float = 0.0
    saved_clay_workdays: float = 0.0

    # Grain-for-resowing factor
    grain_per_grain_factor: float = 0.0

    # Patches in territory: list of (row, col) tuples
    candidate_patches: List[tuple] = field(default_factory=list)

    def patch_row_col(self) -> tuple[int, int]:
        return int(round(self.row)), int(round(self.col))

    def __repr__(self) -> str:
        return (f"Community(who={self.who}, name={self.site_name!r}, "
                f"type={self.settlement_type}, pop={self.population})")


def make_community(who: int,
                   site_name: str,
                   settlement_type: str,
                   start_period: str,
                   col: float,
                   row: float,
                   params) -> Community:
    """
    Factory matching NetLogo's ``create-communities`` block in
    ``setup-communities``.
    """
    rng = np.random.default_rng()

    # Stochastic population
    pop_map = {"hamlet": (50, 10), "village": (500, 100), "town": (1000, 200)}
    mu, sigma = pop_map.get(settlement_type, (100, 20))
    population = max(1, int(round(rng.normal(mu, sigma))))

    # Elevation of the settlement patch (row/col already in raster coords)
    # it will be set externally after world is constructed.
    elev = 0.0  # placeholder tijdelijk; wordt geupdated in setup_communities()

    food_req = population * 365 * params.food_demand_pc / 1000
    wood_req = population * (365 * params.wood_demand_pc + 0.0661 * elev) / 695
    clay_req = population * params.clay_demand_pc / 1000

    workdays = population * params.active_percentage / 100 * 365
    food_workdays = population * params.active_percentage / 100 * params.agricultural_days

    grain_factor = params.grain_per_grain_yield / (params.grain_per_grain_yield - 1)

    return Community(
        who=who,
        site_name=site_name,
        settlement_type=settlement_type,
        start_period=start_period,
        col=col,
        row=row,
        population=population,
        workdays=workdays,
        food_workdays=food_workdays,
        food_requirement=food_req,
        wood_requirement=wood_req,
        clay_requirement=clay_req,
        grain_per_grain_factor=grain_factor,
    )
