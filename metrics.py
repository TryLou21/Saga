"""
SagaScape – Metrics & output

Genereert een CSV in exact hetzelfde formaat als NetLogo's BehaviorSpace output,
zodat het R-script (SAGAscape_Output_analysis.R) er direct mee werkt.

NetLogo BehaviorSpace CSV structuur

Rij 1:  "BehaviorSpace results (NetLogo ...)"
Rij 2:  leeg
Rij 3:  experimentnaam
Rij 4:  leeg
Rij 5:  leeg
Rij 6:  leeg  (skip=6 in R)
Rij 7:  kolomhoofden (parameters + "[step]" + metrics)
Rij 8+: data, één rij per tijdstap per run

Metrics per rij (gecomprimeerd NetLogo-formaat):
  - saved.food.workdays  → "[who pop waarde] [who pop waarde] …"   (3 getallen per community)
  - alle andere metrics  → "[who waarde] [who waarde] …"           (2 getallen per community)
  - forest.patches       → enkelvoudig getal
  - agricultural.patches → enkelvoudig getal
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from world import World
from agents import Community
from config import PARAMS


# Helpers

def _fmt_community_metric(communities: List[Community],
                           getter,
                           include_pop: bool = False) -> str:
    """
    Bouw de gecomprimeerde NetLogo-string voor één metric.

    include_pop=False  →  "[who waarde] [who waarde] …"
    include_pop=True   →  "[who pop waarde] [who pop waarde] …"
                           (alleen voor saved.food.workdays)
    """
    parts = []
    for c in communities:
        if include_pop:
            parts.append(f"[{c.who} {c.population} {round(getter(c), 2)}]")
        else:
            parts.append(f"[{c.who} {round(getter(c), 2)}]")
    return " ".join(parts)


# Collector

class MetricsCollector:
    """
    Verzamelt metrics elke tick en schrijft ze naar een NetLogo-compatibele CSV.
    """

    def __init__(self, params=PARAMS) -> None:
        self.params  = params
        self.records: list[dict] = []

    def collect(self, tick: int,
                world: World,
                communities: List[Community]) -> None:

        active = [c for c in communities if c.active]

        # Gecomprimeerde strings per metric (NetLogo-formaat)
        saved_food_wd  = _fmt_community_metric(active,
                                               lambda c: c.saved_food_workdays,
                                               include_pop=True)
        saved_wood_wd  = _fmt_community_metric(active, lambda c: c.saved_wood_workdays)
        saved_clay_wd  = _fmt_community_metric(active, lambda c: c.saved_clay_workdays)
        cum_food_stock = _fmt_community_metric(active, lambda c: c.cumulative_food_stock)
        cum_wood_stock = _fmt_community_metric(active, lambda c: c.cumulative_wood_stock)
        cum_clay_stock = _fmt_community_metric(active, lambda c: c.cumulative_clay_stock)
        tot_food_eff   = _fmt_community_metric(active, lambda c: c.total_food_effort)
        tot_wood_eff   = _fmt_community_metric(active, lambda c: c.total_wood_effort)
        tot_clay_eff   = _fmt_community_metric(active, lambda c: c.total_clay_effort)

        forest_patches = int((world.land & (world.wood_age > 0)).sum())
        agri_patches   = int((world.land & world.food_flag & ~world.wood_flag).sum())

        self.records.append({
            "step":                    tick,
            "saved.food.workdays":     saved_food_wd,
            "saved.wood.workdays":     saved_wood_wd,
            "saved.clay.workdays":     saved_clay_wd,
            "cumulative.food.stock":   cum_food_stock,
            "cumulative.wood.stock":   cum_wood_stock,
            "cumulative.clay.stock":   cum_clay_stock,
            "total.food.effort":       tot_food_eff,
            "total.wood.effort":       tot_wood_eff,
            "total.clay.effort":       tot_clay_eff,
            "forest.patches":          forest_patches,
            "agricultural.patches":    agri_patches,
        })

    def save_csv(self, path: str | Path, run: int = 1) -> None:
        """
        Schrijf een CSV in het exacte NetLogo BehaviorSpace formaat.

        Parameters
        ----------
        path : bestandspad voor de CSV
        run  : runnummer (staat in de eerste kolom, net als NetLogo)
        """
        path = Path(path)
        p    = self.params

        # ---- Kolomhoofden (parameters + stap + metrics) ----
        # De eerste 13 kolommen zijn de BehaviorSpace-parameters.
        # R-code verwijdert 'landuse.visualization' en 'time.limit' (kolommen 14-15 origineel),
        # dan hernoemt het de resterende kolommen vanaf positie 14 naar "step", metrics...
        # We schrijven alle parameters mee zodat het R-script ze kan filteren.
        param_headers = [
            "[run number]",
            "agricultural-days",
            "regeneration-time",
            "territory",
            "forest-regrowth-lag",
            "clay-demand-pc",
            "kgs-wood-per-kg-clay",
            "grain-per-grain-yield",
            "clay-threshold",
            "food-demand-pc",
            "active-percentage",
            "wood-demand-pc",
            "bad-harvest-interval",
            "landuse-visualization",   # wordt verwijderd door R
            "time-limit",              # wordt verwijderd door R
        ]

        metric_headers = [
            "[step]",
            "[(list who population precision saved-food-workdays 2)] of communities",
            "[(list who precision saved-wood-workdays 2)] of communities",
            "[(list who precision saved-clay-workdays 2)] of communities",
            "[(list who precision cumulative-food-stock 2)] of communities",
            "[(list who precision cumulative-wood-stock 2)] of communities",
            "[(list who precision cumulative-clay-stock 2)] of communities",
            "[(list who precision total-food-effort 2)] of communities",
            "[(list who precision total-wood-effort 2)] of communities",
            "[(list who precision total-clay-effort 2)] of communities",
            "count patches with [land? = true and wood-age > 0]",
            "count patches with [land? = true and food? = true and wood? = false]",
        ]

        all_headers = param_headers + metric_headers

        # ---- Parameterwaarden (constant voor alle rijen) ----
        param_values = [
            run,
            p.agricultural_days,
            p.regeneration_time,
            p.territory,
            p.forest_regrowth_lag,
            p.clay_demand_pc,
            p.kgs_wood_per_kg_clay,
            p.grain_per_grain_yield,
            p.clay_threshold,
            p.food_demand_pc,
            p.active_percentage,
            p.wood_demand_pc,
            p.bad_harvest_interval,
            str(p.landuse_visualization).lower(),  # "true" / "false"
            p.time_limit,
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)

            # ---- 6 metadata-rijen (skip=6 in R) ----
            writer.writerow([f"BehaviorSpace results (NetLogo Python port)"])
            writer.writerow([])
            writer.writerow(["CAA runs"])
            writer.writerow([])
            writer.writerow([])
            writer.writerow([])

            # ---- Kolomhoofden ----
            writer.writerow(all_headers)

            # ---- Data ----
            for rec in self.records:
                row = param_values + [
                    rec["step"],
                    rec["saved.food.workdays"],
                    rec["saved.wood.workdays"],
                    rec["saved.clay.workdays"],
                    rec["cumulative.food.stock"],
                    rec["cumulative.wood.stock"],
                    rec["cumulative.clay.stock"],
                    rec["total.food.effort"],
                    rec["total.wood.effort"],
                    rec["total.clay.effort"],
                    rec["forest.patches"],
                    rec["agricultural.patches"],
                ]
                writer.writerow(row)

        print(f"Metrics opgeslagen → {path}  ({len(self.records)} ticks, run {run})")