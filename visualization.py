"""
SagaScape – Visualisation

Matplotlib equivalent of NetLogo's ``viz-exploitation`` procedure.
Supports:
  - Landuse view  (forest / agriculture / clay)
  - Elevation view (default background)
  - Live updating during simulation
"""

# Afkortingen
# r, c      → row, col  : absolute positie in het raster / img array
# img       → (nrows, ncols, 4) float32 array : RGBA canvas
# t         → waarde tussen 0.0 en 1.0 voor kleurinterpolatie in colormap
# w_min/max → min/max wood_standing_stock (voor normalisatie)
# f_min/max → min/max food_fertility (voor normalisatie)
# c_min/max → min/max clay_quantity  (voor normalisatie)
# e_min/max → min/max elevation      (voor normalisatie)

from __future__ import annotations

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from world import World
from agents import Community


# Colour helpers (matching NetLogo palette:scale-gradient calls)

def _make_cmap(colors_rgb: list[tuple], name: str) -> LinearSegmentedColormap:
    colors_01 = [(r/255, g/255, b/255) for r, g, b in colors_rgb]
    return LinearSegmentedColormap.from_list(name, colors_01)


ELEV_CMAP   = _make_cmap([(255, 0, 0), (255, 255, 191), (0, 104, 55)], "elevation")
FOREST_CMAP = _make_cmap([(0, 109, 44), (186, 228, 179)],              "forest")
AGRI_CMAP   = _make_cmap([(153, 52, 4), (254, 217, 142)],              "agriculture")
CLAY_CMAP   = _make_cmap([(0, 0, 0), (255, 255, 255)],                 "clay")


# Main visualiser class

class Visualizer:
    def __init__(self, world: World,
                 communities: list[Community],
                 figsize: tuple = (14, 8)) -> None:
        self.world       = world
        self.communities = communities

        matplotlib.use("TkAgg")
        self.fig, self.ax = plt.subplots(figsize=figsize)
        self.im = None
        self._scatter = None
        plt.ion()
        plt.tight_layout()

    def update(self, tick: int, landuse_visualization: bool = True) -> None:
        world = self.world
        nrows, ncols = world.nrows, world.ncols

        img = np.zeros((nrows, ncols, 4), dtype=np.float32)
        img[:, :, 3] = 1.0

        if landuse_visualization:
            self._draw_landuse(img, world)
        else:
            self._draw_elevation(img, world)

        water_mask = ~world.land
        img[water_mask] = [0.0, 0.0, 0.7, 1.0]

        if self.im is None:
            self.im = self.ax.imshow(img, origin="upper", interpolation="nearest")
        else:
            self.im.set_data(img)

        # Community markers
        if self._scatter is not None:
            self._scatter.remove()

        active_comms = [c for c in self.communities if c.active]
        if active_comms:
            xs = [c.col for c in active_comms]
            ys = [c.row for c in active_comms]
            self._scatter = self.ax.scatter(xs, ys, c="red",
                                            s=[c.population / 10 for c in active_comms],
                                            zorder=5, edgecolors="white", linewidths=0.5)

        self.ax.set_title(f"SagaScape  –  tick {tick}", fontsize=13)
        self.ax.set_xlabel("col (west → east)")
        self.ax.set_ylabel("row (north → south)")
        self.fig.canvas.draw_idle()
        plt.pause(0.001)

    def _draw_landuse(self, img: np.ndarray, world: World) -> None:
        # Forest
        forest_mask = world.land & world.wood_flag
        if forest_mask.any():
            w_max = world.wood_standing_stock[forest_mask].max()
            w_min = world.wood_standing_stock[forest_mask].min()
            w_range = (w_max - w_min) or 1.0
            for r, c in zip(*np.where(forest_mask)):
                t = (world.wood_standing_stock[r, c] - w_min) / w_range
                img[r, c, :3] = FOREST_CMAP(t)[:3]

        # Agriculture (food but not wood)
        agri_mask = world.land & world.food_flag & ~world.wood_flag
        if agri_mask.any():
            f_max = world.food_fertility[agri_mask].max()
            f_min = world.food_fertility[agri_mask].min()
            f_range = (f_max - f_min) or 1.0
            for r, c in zip(*np.where(agri_mask)):
                t = (world.food_fertility[r, c] - f_min) / f_range
                img[r, c, :3] = AGRI_CMAP(t)[:3]

        # Clay (no food, no wood)
        clay_mask = world.land & world.clay_flag & ~world.wood_flag & ~world.food_flag
        if clay_mask.any():
            c_max = world.clay_quantity[clay_mask].max()
            c_min = world.clay_quantity[clay_mask].min()
            c_range = (c_max - c_min) or 1.0
            for r, c in zip(*np.where(clay_mask)):
                t = (world.clay_quantity[r, c] - c_min) / c_range
                img[r, c, :3] = CLAY_CMAP(t)[:3]

    def _draw_elevation(self, img: np.ndarray, world: World) -> None:
        elev = world.elevation
        land = world.land
        if not land.any():
            return
        e_max = np.nanmax(elev[land])
        e_min = np.nanmin(elev[land])
        e_range = (e_max - e_min) or 1.0
        for r, c in zip(*np.where(land)):
            t = (elev[r, c] - e_min) / e_range
            img[r, c, :3] = ELEV_CMAP(t)[:3]

    def save(self, path: str) -> None:
        self.fig.savefig(path, dpi=150, bbox_inches="tight")
        print(f" Figure saved → {path}")

    def close(self) -> None:
        plt.close(self.fig)


# Headless snapshot (for batch runs)

def save_snapshot(world: World,
                  communities: list[Community],
                  tick: int,
                  path: str,
                  landuse_visualization: bool = True) -> None:
    old_backend = matplotlib.get_backend()
    matplotlib.use("Agg")

    fig, ax = plt.subplots(figsize=(14, 8))
    nrows, ncols = world.nrows, world.ncols
    img = np.zeros((nrows, ncols, 4), dtype=np.float32)
    img[:, :, 3] = 1.0

    viz = Visualizer.__new__(Visualizer)
    viz.world       = world
    viz.communities = communities
    viz.fig, viz.ax, viz.im, viz._scatter = fig, ax, None, None

    if landuse_visualization:
        viz._draw_landuse(img, world)
    else:
        viz._draw_elevation(img, world)
    img[~world.land] = [0.0, 0.0, 0.7, 1.0]

    ax.imshow(img, origin="upper", interpolation="nearest")

    active = [c for c in communities if c.active]
    if active:
        ax.scatter([c.col for c in active],
                   [c.row for c in active],
                   c="red",
                   s=[c.population / 10 for c in active],
                   zorder=5, edgecolors="white", linewidths=0.5)

    ax.set_title(f"SagaScape  –  tick {tick}")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    matplotlib.use(old_backend)