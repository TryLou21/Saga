# SagaScape – Python port

Agent-based simulation of resource exploitation around Sagalassos (SW Turkey),
translated from NetLogo 7 to Python.

## Project structure

```
sagascape/
├── config.py          # All parameters (sliders/switches from NetLogo UI)
├── world.py           # Patch grid – raster state arrays
├── agents.py          # Community agent class
├── setup.py           # Setup procedures (topo, communities, LCA, resources…)
├── procedures.py      # Tick procedures (exploit, burn, regenerate, disaster)
├── visualization.py   # Matplotlib visualisation
├── metrics.py         # Output collection → CSV
├── main.py            # Main loop (entry point)
└── requirements.txt
```

## Installation

```bash
pip install -r requirements.txt
```

> **GDAL note**: `rasterio` and `geopandas` both need GDAL.
> On Windows/macOS it is easiest to install via conda:
> ```bash
> conda install -c conda-forge rasterio geopandas
> ```

## Data

Place the original data files in a `data/` folder next to `sagascape/`:

```
data/
├── Altitude.asc
├── Fertility_K.asc
├── ForestMax.asc
├── ForestA.asc
├── ForestB.asc
├── Tobler_EPSG32636.asc
├── lakesAndRiversRasterized.asc
├── Clay content_kg_per_ha.asc
├── sagascape-sites-EPSG32636.shp
└── 32636.prj
```

## Running

```bash
# Interactive window (same as NetLogo interface)
python main.py

# Headless (batch runs, saves PNG snapshots every 50 ticks)
python main.py --headless --snap-every 50

# Headless (batch runs, saves PNG snapshots every x ticks, x can be changed in the main file)
python main.py --headless

# Override time limit
python main.py --ticks 200

# No visualisation at all (fastest)
python main.py --no-viz
```

Output is written to `output/metrics.csv`.

## NetLogo ↔ Python mapping

| NetLogo concept        | Python equivalent                                                                                            |
|------------------------|--------------------------------------------------------------------------------------------------------------|
| `patches`              | 2-D NumPy arrays in `World`                                                                                  |
| `communities` breed    | `Community` dataclass in `agents.py`                                                                         |
| `inactive-communities` | Same class, `active=False`                                                                                   |
| `rangers` + `nw` ext.  | Scipy `dijkstra` on CSR sparse graph                                                                         |
| `gis` extension        | `rasterio` + `geopandas`                                                                                     |
| `palette:scale-gradient`| `LinearSegmentedColormap`                                                                                    |
| BehaviorSpace metrics  | `MetricsCollector` → `output/metrics.csv`                                                                    |
| Sliders / switches     | `Params` dataclass in `config.py` <br/> needs to be manually changed because base python do not have sliders |

## Parameter tuning

Edit `config.py` to change any model parameter.  
For batch experiments with multiple parameter combinations, instantiate
multiple `Params` objects and call `setup(params)` / `main loop` separately.

## Key equations

| Symbol | Equation                              | Location             |
|--------|---------------------------------------|----------------------|
| S(t)   | `A * exp(B * age)`, capped at Smax   | `world.py`           |
| F(t)   | Verhulst logistic growth              | `procedures.py`      |
| r      | `(99*K/reserve - 99)^(-1/regen_time)`| `setup.py`           |
