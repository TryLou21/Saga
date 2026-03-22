"""
SagaScape – World (patches)

Holds all raster-based patch data as 2-D NumPy arrays.
Row 0 = NetLogo's max-pycor (north), matching GIS convention.
"""
# Afkortingen
# r, c       → row, col       : absolute positie in het raster (0-gebaseerd)
# row, col   → zelfde als r, c maar als functie-parameter
# gr, gc     → global row/col : absolute rij/kolom in het volledige raster
# lr, lc     → local row/col  : rij/kolom binnen het subgrid van een community
# nr, nc     → neighbour row/col : rij/kolom van een buurpatch
# idx        → lineaire index : r * ncols + c  (voor in_range_of / claimed_cost dicts)
# nrows, ncols → aantal rijen / kolommen van het volledige raster
# sub_nrows, sub_ncols → aantal rijen / kolommen van het subgrid

from __future__ import annotations

import numpy as np
import rasterio
import geopandas as gpd
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from config import RASTER_FILES, PARAMS


# Helper

def _load_asc(path: Path) -> np.ndarray:
    """Load an ASC raster and return a float64 array (nodata → NaN)."""
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float64)
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
    return data


# World

class World:
    """
    Container for all patch-level state arrays.

    Coordinate convention
    ---------------------
    world[row, col] where row=0 is the NORTHERNMOST row
    (same as rasterio / standard GIS; NetLogo's y-axis is flipped, but
    during raster loading NetLogo does ``(max-pycor - pycor)`` so the
    result is the same layout).
    """

    def __init__(self) -> None:
        self._load_rasters()
        self._init_patch_state()

    # Loading

    def _load_rasters(self) -> None:
        print("Loading rasters…")

        self.elevation = _load_asc(RASTER_FILES["elevation"])
        self.fertility_k = _load_asc(RASTER_FILES["fertility"])
        self.wood_max_stock = _load_asc(RASTER_FILES["forest_max"])
        self.wood_rico = _load_asc(RASTER_FILES["forest_a"])   # A param
        self.wood_power = _load_asc(RASTER_FILES["forest_b"])   # B param
        self.walking_time_raw = _load_asc(RASTER_FILES["walking_time"])
        self.water_bodies_raw = _load_asc(RASTER_FILES["water_bodies"])
        self.clay_raw = _load_asc(RASTER_FILES["clay"])

        self.nrows, self.ncols = self.elevation.shape
        #size of the grid (396*799 = 316404 patches in totaal)
        print(f"Grid: {self.nrows} rows * {self.ncols} cols")

    def _init_patch_state(self) -> None:
        """Allocate all mutable patch arrays (equivalent to patches-own)."""
        shape = (self.nrows, self.ncols)

        #  topology / land
        self.land = np.zeros(shape, dtype=bool)
        self.walking_time = self.walking_time_raw.copy()

        # clay
        # Convert from kg/ha to tonnes/ha in top 2 m
        self.clay_quantity = self.clay_raw / 1000.0
        self.clay_flag = np.zeros(shape, dtype=bool)   # clay?

        # wood
        self.wood_age = np.zeros(shape, dtype=np.float64)
        self.wood_standing_stock= np.zeros(shape, dtype=np.float64)
        self.wood_flag = np.zeros(shape, dtype=bool)   # wood?
        self.time_since_fire = np.zeros(shape, dtype=np.float64)
        self.fire_return_rate = np.zeros(shape, dtype=np.float64)

        #  food / agriculture
        self.food_fertility = np.zeros(shape, dtype=np.float64)
        self.original_food_value = np.zeros(shape, dtype=np.float64)
        self.food_flag = np.zeros(shape, dtype=bool)   # food?
        self.growth_rate = np.zeros(shape, dtype=np.float64)
        self.time_since_abandonment = np.zeros(shape, dtype=np.float64)

        # least-cost / territory
        # These are dicts: patch_idx → list, populated by setup_least_cost_distances
        # patch_idx = row * ncols + col
        self.in_range_of: dict[int, list] = {}   # patch → [community, …]
        self.claimed_cost: dict[int, list] = {}   # patch → [cost, …]

        # fire tracking
        self.burn_size: list[int] = []

    # Indexing helper functies

    def idx(self, row: int, col: int) -> int:
        return row * self.ncols + col

    def rc(self, idx: int):
        return divmod(idx, self.ncols)

    def valid(self, row: int, col: int) -> bool:
        return 0 <= row < self.nrows and 0 <= col < self.ncols

    def neighbors4(self, row: int, col: int) -> list[tuple[int, int]]:
        """Von Neumann neighbourhood."""
        return [(r, c) for r, c in
                [(row-1, col), (row+1, col), (row, col-1), (row, col+1)]
                if self.valid(r, c)]

    def neighbors8(self, row: int, col: int) -> list[tuple[int, int]]:
        """Moore neighbourhood."""
        return [(r, c) for r in range(row-1, row+2)
                        for c in range(col-1, col+2)
                        if (r != row or c != col) and self.valid(r, c)]

    # Wood standing stock equation (Equation 6 in Suppl. Mat.)
    # S(t) = A * exp(B * age)  capped at Smax

    def wood_update_standing_stock(self, rows=None, cols=None) -> None:
        """
        Update wood standing stock for the given patch indices.
        If rows/cols are None, update ALL patches.
        Equivalent to NetLogo's ``wood-updateStandingStock``.
        """
        if rows is None:
            rows, cols = np.where(self.land)

        for r, c in zip(rows, cols):
            # After forest-regrowth-lag years of abandonment, re-enable wood
            if self.time_since_abandonment[r, c] > PARAMS.forest_regrowth_lag:
                self.wood_flag[r, c] = True

            if self.wood_flag[r, c]:
                age = self.wood_age[r, c]
                smax = self.wood_max_stock[r, c]
                a    = self.wood_rico[r, c]
                b    = self.wood_power[r, c]

                if self.wood_standing_stock[r, c] < smax:
                    self.wood_standing_stock[r, c] = a * np.exp(b * age)
                else:
                    self.wood_standing_stock[r, c] = smax

                self.wood_age[r, c]        += 1
                self.time_since_fire[r, c] += 1
