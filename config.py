"""
SagaScape – Configuration

All slider / switch values from the NetLogo interface live here.
Change them before running a simulation.
"""

from dataclasses import dataclass, field
from pathlib import Path

# Paths
DATA_DIR = Path("data")

RASTER_FILES = {
    "elevation":         DATA_DIR / "Altitude.asc",
    "fertility":         DATA_DIR / "Fertility_K.asc",
    "forest_max":        DATA_DIR / "ForestMax.asc",
    "forest_a":          DATA_DIR / "ForestA.asc",
    "forest_b":          DATA_DIR / "ForestB.asc",
    "walking_time":      DATA_DIR / "Tobler_EPSG32636.asc",
    "water_bodies":      DATA_DIR / "lakesAndRiversRasterized.asc",
    "clay":              DATA_DIR / "Clay content_kg_per_ha.asc",
}

SITES_SHAPEFILE = DATA_DIR / "sagascape-sites-EPSG32636.shp"

# Simulation sliders (NetLogo interface defaults)
@dataclass
class Params:
    # Demand per capita
    food_demand_pc: float = 1.50        # kg/day #variable
    wood_demand_pc: float = 1.0        # kg/day #variable
    clay_demand_pc: float = 1.0         # kg/year #variable

    # Labour
    active_percentage: float = 25.0     # % of population that works #variable
    agricultural_days: int   = 250      # days/year dedicated to farming

    # Agriculture
    grain_per_grain_yield: float = 6.0  # kg seed → kg grain
    regeneration_time:     int   = 2    # years for fertility recovery #variable

    # Forestry / clay
    kgs_wood_per_kg_clay: float = 0.29
    clay_threshold:       float = 0.25   # tonnes/m³ #variable

    # Disaster
    bad_harvest_interval: int = 5       # mean years between bad harvests
    forest_regrowth_lag:  int = 6       # years before abandoned field becomes forest

    # Territory (search radius in map units = ha patches = ~100 m)
    territory: int = 50

    # Simulation length
    time_limit: int = 1000

    # Visualisation
    landuse_visualization: bool = True

    # Derived / convenience
    @property
    def grain_per_grain_factor(self) -> float:
        return self.grain_per_grain_yield / (self.grain_per_grain_yield - 1)


# Singleton used throughout the simulation
PARAMS = Params()
