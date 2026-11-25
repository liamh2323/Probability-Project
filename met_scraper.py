#!/usr/bin/env python3
"""
Met Éireann historical data scraper.

Downloads station data and keeps only 1 Dec -> 30 Jun windows
(Dec of year Y through Jun of year Y+1) for seasons starting 2020..2025,
i.e. Dec 2020 - Jun 2026. Seasons with no data are skipped and reported.

Usage:
    pip install pandas requests
    python met_scraper.py                         # Dublin Airport, daily
    python met_scraper.py --stations 532 3904     # Dublin + Cork Airport
    python met_scraper.py --res hly               # hourly
    python met_scraper.py --start-year 2019       # also include Dec 2019 - Jun 2020

Station numbers: https://www.met.ie/climate/available-data/historical-data
(e.g. 532 Dublin Airport, 3904 Cork Airport, 518 Shannon Airport, 1875 Athenry)
"""
import argparse
import io
import sys
from pathlib import Path

import pandas as pd
import requests

HOSTS = [
    "https://clidata.met.ie/cli/climate_data/webdata",
    "https://cli.fusio.net/cli/climate_data/webdata",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (research scraper)"}


def download(station: str, res: str) -> str:
    last_err = None
    for host in HOSTS:
        url = f"{host}/{res}{station}.csv"
        try:
            r = requests.get(url, headers=HEADERS, timeout=120)
            if r.status_code == 200 and "date" in r.text[:20000].lower():
                print(f"  fetched {url}")
                return r.text
            last_err = f"HTTP {r.status_code} from {url}"
        except requests.RequestException as e:
            last_err = f"{url}: {e}"
    raise RuntimeError(f"Could not download station {station} ({res}): {last_err}")


def parse(text: str) -> pd.DataFrame:
    # Files start with a block of metadata lines; the table begins at the 'date,' header.
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip().lower().startswith("date,"))
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])), low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True)
    return df


def seasons(df: pd.DataFrame, start_year: int, end_year: int):
    for y in range(start_year, end_year + 1):
        lo = pd.Timestamp(y, 12, 1)
        hi = pd.Timestamp(y + 1, 7, 1)  # exclusive -> includes all of 30 Jun (hourly too)
        part = df[(df["date"] >= lo) & (df["date"] < hi)].copy()
        part.insert(0, "season", f"{y}-{y + 1}")
        yield y, part


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stations", nargs="+", default=["532"], help="station numbers")
    ap.add_argument("--res", choices=["dly", "hly"], default="dly", help="daily or hourly")
    ap.add_argument("--start-year", type=int, default=2020, help="first December")
    ap.add_argument("--end-year", type=int, default=2025, help="last December")
    ap.add_argument("--out", default="met_data", help="output folder")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    for st in a.stations:
        print(f"Station {st}:")
        try:
            df = parse(download(st, a.res))
        except Exception as e:
            print(f"  ERROR {e}", file=sys.stderr)
            continue

        print(f"  data spans {df['date'].min().date()} to {df['date'].max().date()}")
        kept = []
        for y, part in seasons(df, a.start_year, a.end_year):
            if part.empty:
                print(f"  {y}-{y + 1}: no data, skipped")
                continue
            last = part["date"].max().date()
            note = "" if last >= pd.Timestamp(y + 1, 6, 30).date() else f" (partial, ends {last})"
            print(f"  {y}-{y + 1}: {len(part)} rows{note}")
            part.to_csv(out / f"{a.res}{st}_{y}-{y + 1}.csv", index=False)
            kept.append(part)

        if kept:
            pd.concat(kept).to_csv(out / f"{a.res}{st}_all_seasons.csv", index=False)
            print(f"  combined -> {out / f'{a.res}{st}_all_seasons.csv'}")


if __name__ == "__main__":
    main()
