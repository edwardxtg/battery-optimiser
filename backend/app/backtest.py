"""Backtest the optimiser over every complete day in the price store and benchmark it.

    python -m app.backtest [--power 10 --capacity 20 --efficiency 0.88]

For each settlement day with 48 periods, solve the dispatch LP (perfect foresight, SoC
reset each day) and write one row to `runs`. Then run app/sql/benchmark.sql, which joins
those results to the TB_D spread available that day and reports the capture rate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd

from .db import DB_PATH, connect, query
from .optimise import HOURS_PER_YEAR, Battery, optimise_dispatch


def complete_days(con) -> pd.DataFrame:
    """Prices pivoted to one row per complete settlement day, periods in order."""
    return con.execute("""
        SELECT settlement_date, list(price ORDER BY settlement_period) AS prices
        FROM prices
        GROUP BY settlement_date
        HAVING count(*) = 48
        ORDER BY settlement_date
    """).df()


def run_backtest(con, battery: Battery) -> int:
    """Solve each day and upsert into `runs`. Returns the number of days run."""
    days = complete_days(con)
    rows = []
    for day, prices in zip(days["settlement_date"], days["prices"]):
        r = optimise_dispatch(battery, prices)
        rows.append({
            "settlement_date": day,
            "power_mw": battery.power_mw,
            "capacity_mwh": battery.capacity_mwh,
            "efficiency": battery.efficiency,
            "net_profit": r.net_profit,
            "energy_discharged_mwh": r.energy_discharged_mwh,
            "cycles": r.cycles,
            "run_at": datetime.now(timezone.utc),
        })
    if rows:
        df = pd.DataFrame(rows)
        con.execute("INSERT OR REPLACE INTO runs SELECT * FROM df")
    return len(rows)


def benchmark(con, battery: Battery) -> pd.DataFrame:
    return query(
        con, "benchmark",
        power_mw=battery.power_mw, capacity_mwh=battery.capacity_mwh,
        efficiency=battery.efficiency, hours=battery.capacity_mwh / battery.power_mw,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--power", type=float, default=10.0, help="rated power, MW")
    ap.add_argument("--capacity", type=float, default=20.0, help="energy capacity, MWh")
    ap.add_argument("--efficiency", type=float, default=0.88, help="round-trip efficiency")
    ap.add_argument("--db", default=DB_PATH, help="path to the DuckDB file")
    args = ap.parse_args()

    battery = Battery(capacity_mwh=args.capacity, power_mw=args.power, efficiency=args.efficiency)
    con = connect(args.db)
    n = run_backtest(con, battery)
    bench = benchmark(con, battery)
    con.close()

    hours = battery.capacity_mwh / battery.power_mw
    print(f"{battery.power_mw:g} MW / {battery.capacity_mwh:g} MWh ({hours:g}h), "
          f"RTE {battery.efficiency:.0%}, perfect foresight, {n} days\n")
    print(bench.to_string(index=False))
    gbp_per_mw_day = bench["gbp_per_mw"].mean()
    print(f"\nmean TB{hours:g}         £{bench['tb_d'].mean():,.0f}/MW/day")
    print(f"mean realised    £{gbp_per_mw_day:,.0f}/MW/day  (~£{gbp_per_mw_day * HOURS_PER_YEAR / 24:,.0f}/MW/yr)")
    print(f"capture rate     {bench['capture_rate'].mean():.1%}")
    print(f"cycles/day       {bench['cycles'].mean():.2f}")


if __name__ == "__main__":
    main()
