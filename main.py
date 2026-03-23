"""
SagaScape – Main simulation loop

Equivalent to NetLogo's ``go`` procedure.

Usage

    python main.py                        # interactive, uses configuration.py defaults
    python main.py --headless             # no window, saves PNG snapshots
    python main.py --ticks 200            # override time_limit
    python main.py --no-viz               # skip visualisation entirely

Output (during of after the run fase)

    output/metrics.csv    – BehaviorSpace-style per-tick × per-community data
    output/snap_NNNN.png  – optional snapshots (--headless)
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from configuration import PARAMS
from setup_env import setup
from procedures import (exploit_resources, burn_resources, regenerate,
                        reset_community_workdays, disaster, add_sites)
from metrics import MetricsCollector

OUTPUT_DIR = Path("output")


def parse_args():
    p = argparse.ArgumentParser(description="SagaScape Python simulation")
    p.add_argument("--ticks",    type=int,  default=None,
                   help="Override time_limit from config")
    p.add_argument("--headless", action="store_true",
                   help="Run without interactive window; save PNG snapshots")
    p.add_argument("--no-viz",   action="store_true",
                   help="Skip all visualisation")
    p.add_argument("--snap-every", type=int, default=50,
                   help="Save a snapshot every N ticks (headless mode)")
    return p.parse_args()


def main():
    args = parse_args()
    params = PARAMS

    if args.ticks is not None:
        params.time_limit = args.ticks

    OUTPUT_DIR.mkdir(exist_ok=True)

    #  setup
    world, communities = setup(params)

    #  visualisation
    viz = None
    if not args.no_viz:
        if args.headless:
            from visualization import save_snapshot
            snap_fn = save_snapshot
        else:
            from visualization import Visualizer
            viz = Visualizer(world, communities)

    #  collector
    collector = MetricsCollector()

    bad_harvest_modifier = 1.0
    t0 = time.perf_counter()

    #  main loop
    print(f"Running simulation for {params.time_limit} ticks…")

    for tick in range(1, params.time_limit + 1):

        #  1. exploit
        exploit_resources(world, communities, bad_harvest_modifier, params)

        #  2. visualise
        if not args.no_viz:
            if args.headless:
                if tick % args.snap_every == 0:
                    snap_fn(world, communities, tick,
                            str(OUTPUT_DIR / f"snap_{tick:04d}.png"),
                            params.landuse_visualization)
            elif viz is not None:
                viz.update(tick, params.landuse_visualization)

        #  3. burn (consumption)
        burn_resources(communities)

        #  4. regenerate
        regenerate(world, params)
        reset_community_workdays(communities, params)
        bad_harvest_modifier = 1.0  # reset; disaster sets it

        #  5. disaster
        bad_harvest_modifier = disaster(world, params)

        #  6. periodisation events
        if tick == 450:
            print(f"  Tick {tick}: activating Achaemenid sites…")
            add_sites(communities, world, "ACH")

        if tick == 650:
            print(f"  Tick {tick}: activating Hellenistic sites…")
            add_sites(communities, world, "HELL")

        #  7. collect metrics
        collector.collect(tick, world, communities)

        #  8. progress (print in terminal (voor vooruitgang te zien))
        # %n n-> hoeveel ticks voordat je info krijg op de terminal
        if tick % 10 == 0:
            elapsed = time.perf_counter() - t0
            print(f"  Tick {tick:>4d} / {params.time_limit}  "
                  f"({elapsed:.1f}s elapsed)  "
                  f"forested={collector.records[-1]['forest.patches']}  "
                  f"agricultural={collector.records[-1]['agricultural.patches']}")

    #  output
    collector.save_csv(OUTPUT_DIR / "metrics.csv")

    if viz is not None:
        # Final view stays open until user closes it
        import matplotlib.pyplot as plt
        viz.update(tick, params.landuse_visualization)
        print("Close the plot window to exit.")
        plt.ioff()
        plt.show()

    elapsed_total = time.perf_counter() - t0
    print(f"\nSimulation complete in {elapsed_total:.1f} s")
    if world.burn_size:
        import numpy as np
        print(f"  Mean fire size: {np.mean(world.burn_size):.1f} ha  "
              f"(max {max(world.burn_size)} ha)")


if __name__ == "__main__":
    main()
