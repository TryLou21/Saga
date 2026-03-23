"""
SagaScape – Setup procedures

Equivalent to NetLogo's `setup`, `import-map`, `setup-topo`,
`setup-communities`, `setup-least-cost-distances`,
`initial-periodization`, `setup-resources`, `setup-regeneration`.
"""

# Afkortingen
# r, c          → row, col       : absolute positie in het raster
# r_int, c_int  → afgeronde integer versie van row/col (voor array-indexering)
# r_min, r_max  → begin/einde van het subgrid (rijen)
# c_min, c_max  → begin/einde van het subgrid (kolommen)
# gr, gc        → global row/col : absolute rij/kolom in het volledige raster
# lr, lc        → local row/col  : rij/kolom binnen het subgrid
# nr, nc        → neighbour row/col : aangrenzende patch bij linkopbouw
# lnr, lnc      → local neighbour row/col : buur in lokale subgrid coördinaten
# node_i, node_j → lineaire index van twee verbonden knopen in de graaf
# home_local    → lineaire index van de community-patch binnen het subgrid
# lcd           → least-cost distance : goedkoopste looptijd naar deze patch
# lon, lat      → longitude / latitude : geografische coördinaten (GIS)
# col_px, row_px → pixel-coördinaten na omzetting van lon/lat via rasterio

from __future__ import annotations

import numpy as np
import geopandas as gpd
from scipy.sparse.csgraph import dijkstra
from scipy.sparse import csr_matrix

from configuration import PARAMS, SITES_SHAPEFILE
from world import World
from communities import Community, make_community


# 1.  Topology setup

def setup_topo(world: World) -> None:
    print("Setting up topology…")

    water = world.water_bodies_raw
    land_mask = (water == 0) | np.isnan(water)
    world.land[:] = land_mask

    water_mask = ~land_mask
    world.wood_flag[water_mask]      = False
    world.food_flag[water_mask]      = False
    world.clay_flag[water_mask]      = False
    world.clay_quantity[water_mask]  = 0.0
    world.wood_max_stock[water_mask] = 0.0

    rows, cols = np.where(world.land)
    for r, c in zip(rows, cols):
        elev = world.elevation[r, c]
        if np.isnan(elev):
            continue
        if elev < 1100:
            base = 3 + np.random.randint(0, 26)
        else:
            base = int(round((elev - 1100) * 171 / 300)) + 3 + np.random.randint(0, 26)
        world.fire_return_rate[r, c] = base
        world.time_since_fire[r, c]  = np.random.randint(0, base + 1)

    world.burn_size = []


# 2.  Communities

def setup_communities(world: World, params=PARAMS) -> list[Community]:
    print("Setting up communities…")

    gdf = gpd.read_file(SITES_SHAPEFILE)

    communities = []
    who_counter = 0

    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom.geom_type == "Point":
            lon, lat = geom.x, geom.y
        else:
            lon, lat = geom.exterior.coords[0][:2]

        site = str(row.get("Site", row.get("SITE", "")))
        s_type = str(row.get("Type", row.get("TYPE", "hamlet")))
        s_period = str(row.get("Start", row.get("START", "IA")))

        col_px, row_px = _geo_to_pixel(world, lon, lat)

        c = make_community(
            who=who_counter,
            site_name=site,
            settlement_type=s_type.lower(),
            start_period=s_period,
            col=col_px,
            row=row_px,
            params=params,
        )

        r_int, c_int = int(round(row_px)), int(round(col_px))
        if world.valid(r_int, c_int):
            elev = world.elevation[r_int, c_int]
            if not np.isnan(elev):
                c.wood_requirement = (
                    c.population
                    * (365 * params.wood_demand_pc + 0.0661 * elev)
                    / 695
                )

        communities.append(c)
        who_counter += 1

        if world.valid(r_int, c_int):
            world.wood_max_stock[r_int, c_int] = 0.0
            world.food_fertility[r_int, c_int]  = 0.0
            world.wood_flag[r_int, c_int]        = False
            world.food_flag[r_int, c_int]        = False
            world.clay_flag[r_int, c_int]        = False

    print(f"  {len(communities)} communities loaded.")
    return communities


def _geo_to_pixel(world: World, lon: float, lat: float) -> tuple[float, float]:
    import rasterio
    from configuration import RASTER_FILES
    with rasterio.open(RASTER_FILES["elevation"]) as src:
        transform = src.transform
    col, row = ~transform * (lon, lat)
    return col, row


# 3.  Least-cost distances

def setup_least_cost_distances(world: World,
                                communities: list[Community],
                                params=PARAMS) -> None:
    print("Computing least-cost distances… (this may take a while)")

    nrows, ncols = world.nrows, world.ncols
    territory    = params.territory

    for community in communities:
        c_row, c_col = community.patch_row_col()
        if not world.valid(c_row, c_col):
            continue

        r_min = max(0, c_row - territory)
        r_max = min(nrows, c_row + territory + 1)
        c_min = max(0, c_col - territory)
        c_max = min(ncols, c_col + territory + 1)

        sub_nrows = r_max - r_min
        sub_ncols = c_max - c_min
        n_nodes = sub_nrows * sub_ncols

        home_local = (c_row - r_min) * sub_ncols + (c_col - c_min)

        rows_idx = []
        cols_idx = []
        data = []

        wt = world.walking_time

        for lr in range(sub_nrows):
            for lc in range(sub_ncols):
                gr = lr + r_min
                gc = lc + c_min
                node_i = lr * sub_ncols + lc

                wt_i = wt[gr, gc]
                if np.isnan(wt_i):
                    wt_i = 1e9 #heel grootte waarde

                for nr, nc in [(gr-1, gc), (gr, gc-1)]:
                    if world.valid(nr, nc) and r_min <= nr < r_max and c_min <= nc < c_max:
                        wt_j = wt[nr, nc]
                        if np.isnan(wt_j):
                            wt_j = 1e9 #heel grootte waarde
                        weight = 0.5 * (wt_i + wt_j)
                        lnr = nr - r_min
                        lnc = nc - c_min
                        node_j = lnr * sub_ncols + lnc
                        #gerichte graaf, bogen tussen de nodes (niet gewoon pijlen)
                        rows_idx.append(node_i)
                        cols_idx.append(node_j)
                        data.append(weight)
                        rows_idx.append(node_j)
                        cols_idx.append(node_i)
                        data.append(weight)

        graph = csr_matrix((data, (rows_idx, cols_idx)),
                           shape=(n_nodes, n_nodes))

        dist = dijkstra(graph, indices=home_local, directed=False)

        for lr in range(sub_nrows):
            for lc in range(sub_ncols):
                gr = lr + r_min
                gc = lc + c_min
                #(x-a)^2+ (y-b)^2= r^2 (formule)
                if (gr - c_row)**2 + (gc - c_col)**2 > territory**2:
                    continue

                if not world.land[gr, gc]:
                    continue

                if gr == c_row and gc == c_col:
                    continue

                lcd = dist[lr * sub_ncols + lc]
                if np.isinf(lcd):
                    continue

                idx = world.idx(gr, gc)
                if idx not in world.in_range_of:
                    world.in_range_of[idx]  = []
                    world.claimed_cost[idx] = []
                world.in_range_of[idx].append(community)
                world.claimed_cost[idx].append(lcd)

        community.candidate_patches = [
            world.rc(idx)
            for idx, comm_list in world.in_range_of.items()
            if community in comm_list
        ]

    print(f"  Done. {len(world.in_range_of)} reachable patches indexed.")


# 4.  Periodisation

def initial_periodization(communities: list[Community]) -> None:
    for c in communities:
        if c.start_period != "IA":
            c.active = False
    n_active = sum(1 for c in communities if c.active)
    print(f"  Periodisation: {n_active} active (IA) communities.")


# 5.  Resources

def setup_resources(world: World,
                    communities: list[Community],
                    params=PARAMS) -> None:
    import rasterio
    from configuration import RASTER_FILES

    print("Setting up resources…")

    with rasterio.open(RASTER_FILES["fertility"]) as src:
        fertility_raw = src.read(1).astype(np.float64)
        nd = src.nodata
        if nd is not None:
            fertility_raw[fertility_raw == nd] = np.nan

    rows, cols = np.where(world.land)

    for r, c in zip(rows, cols):
        if _any_community_here(r, c, communities):
            world.wood_max_stock[r, c] = 0.0
            world.food_fertility[r, c] = 0.0
            world.clay_flag[r, c]      = False
        else:
            world.wood_flag[r, c] = True
            world.food_flag[r, c] = True
            world.wood_age[r, c]  = 200 + np.random.randint(0, 200)

            raw_f = fertility_raw[r, c] if not np.isnan(fertility_raw[r, c]) else 0.0
            world.food_fertility[r, c] = _adapted_fertility(raw_f)
            world.time_since_abandonment[r, c] = 0

            cq = world.clay_quantity[r, c]
            thresh = params.clay_threshold * 10000 * 2
            world.clay_flag[r, c] = (not np.isnan(cq)) and (cq > thresh)

        world.wood_update_standing_stock(rows=[r], cols=[c])
        smax = world.wood_max_stock[r, c]
        if not np.isnan(smax):
            world.wood_standing_stock[r, c] = min(
                world.wood_standing_stock[r, c], smax)

    world.original_food_value[:] = world.food_fertility

    #  Spin-up: clear land proportional to population
    total_land   = int(np.sum(world.land))
    active_comms = [c for c in communities if c.active]
    total_pop    = sum(c.population for c in active_comms) or 1

    for community in active_comms:
        n_open = int(round(0.60 * total_land * community.population / total_pop))
        c_row, c_col = community.patch_row_col()

        # Sort candidate patches by Euclidean distance to community
        land_patches = list(zip(*np.where(world.land & (world.wood_standing_stock > 0))))
        land_patches.sort(key=lambda rc: (rc[0]-c_row)**2 + (rc[1]-c_col)**2)

        for r, c in land_patches[:n_open]:
            world.wood_standing_stock[r, c] = 0.0
            world.wood_age[r, c]            = 0.0


def _any_community_here(row: int, col: int,
                        communities: list[Community]) -> bool:
    for c in communities:
        if int(round(c.row)) == row and int(round(c.col)) == col:
            return True
    return False


def _adapted_fertility(fertility: float) -> float:
    if fertility == 0 or np.isnan(fertility):
        return 0.0
    if fertility > 3.5:
        return 3.5
    return fertility * 2.8 / 3.5


# 6.  Regeneration initialisation

def setup_regeneration(world: World, params=PARAMS) -> None:
    regeneration_reserve = 0.1

    rows, cols = np.where(world.original_food_value > 0)
    for r, c in zip(rows, cols):
        k = world.original_food_value[r, c]
        if k > regeneration_reserve:
            world.growth_rate[r, c] = (
                99 * k / regeneration_reserve - 99
            ) ** (-1.0 / params.regeneration_time)
        else:
            world.growth_rate[r, c]         = 0.0
            world.original_food_value[r, c] = 0.0

    print("  Regeneration rates computed.")


# Top-level setup

def setup(params=PARAMS) -> tuple[World, list[Community]]:
    print("=== SagaScape setup ===")
    world = World()
    setup_topo(world)
    communities = setup_communities(world, params)
    setup_least_cost_distances(world, communities, params)
    initial_periodization(communities)
    setup_resources(world, communities, params)
    setup_regeneration(world, params)
    print("=== Setup complete ===\n")
    return world, communities