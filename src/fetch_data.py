"""Download the public inputs into data/raw/. Run once; the analysis scripts read only data/raw/.

Sources (no key needed):
  1. National Transit Database, 2025 report year, "Service Data and Operating Expenses by Mode
     (Time Series 2.1)", data.transportation.gov dataset npsm-38gk. One row per agency, mode, type of
     service (directly operated or purchased), year and field, 2015-2025. Five fields are kept and
     pivoted wide so the committed file stays small.
  2. National Transit Database, 2025 report year, "Contractual Relationships" (form B-30),
     dataset wfxt-cwgv. One row per contract, with the contractor's name and whether the contract
     was competitively bid.
  3. FRED series CPIAUCSL (CPI-U, all items), averaged to calendar years, used only to state
     costs in 2025 dollars.

Usage:
    python src/fetch_data.py
"""

import io
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SOCRATA = "https://data.transportation.gov/resource/{id}.csv"
TS21_ID = "npsm-38gk"        # 2025 NTD Annual Data - Time Series 2.1, by mode
CONTRACTS_ID = "wfxt-cwgv"   # 2025 NTD Annual Data - Contractual Relationships
FIELDS = {                   # NTD field name -> short column name
    "Operating Expenses": "opex",
    "Vehicle Revenue Hours": "vrh",
    "Vehicle Revenue Miles": "vrm",
    "Unlinked Passenger Trips": "upt",
    "Vehicles Operated in Maximum Service": "voms",
}
KEEP = ["ntd_id", "agency_name", "state", "reporter_type", "reporting_module", "uza_population",
        "primary_uza_name", "mode", "type_of_service", "report_year"]
PAGE = 50000


def socrata(dataset, where=None, select=None):
    """Page through a Socrata CSV endpoint and return one DataFrame."""
    frames, offset = [], 0
    while True:
        params = {"$limit": PAGE, "$offset": offset, "$order": ":id"}
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select
        r = requests.get(SOCRATA.format(id=dataset), params=params, timeout=300)
        r.raise_for_status()
        chunk = pd.read_csv(io.StringIO(r.text), dtype=str)
        frames.append(chunk)
        print(f"  {dataset}: rows {offset:,}-{offset + len(chunk):,}")
        if len(chunk) < PAGE:
            break
        offset += PAGE
        time.sleep(0.5)
    return pd.concat(frames, ignore_index=True)


def main():
    RAW.mkdir(parents=True, exist_ok=True)

    print("Time Series 2.1 (service and operating expenses by agency, mode, type of service)")
    names = ", ".join(f"'{f}'" for f in FIELDS)
    long = socrata(TS21_ID, where=f"field in ({names})", select=", ".join(KEEP + ["field", "value"]))
    long["field"] = long.field.map(FIELDS)
    long["value"] = pd.to_numeric(long.value, errors="coerce")
    long[KEEP] = long[KEEP].fillna("")  # rural reporters have no urbanized area; keep them
    wide = long.pivot_table(index=KEEP, columns="field", values="value", aggfunc="sum").reset_index()
    wide.columns.name = None
    wide.to_csv(RAW / "ntd_ts21_by_mode_2015_2025.csv", index=False)
    print(f"  wrote {len(wide):,} agency-mode-service-year rows from {len(long):,} long rows")

    print("Contractual relationships, 2025 report year")
    contracts = socrata(CONTRACTS_ID)
    contracts.to_csv(RAW / "ntd_contracts_2025.csv", index=False)
    print(f"  wrote {len(contracts):,} contracts")

    print("FRED CPIAUCSL")
    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL", timeout=120)
    r.raise_for_status()
    cpi = pd.read_csv(io.StringIO(r.text))
    cpi.columns = ["date", "cpi"]
    cpi["year"] = cpi.date.str[:4].astype(int)
    cpi = cpi[cpi.year.between(2015, 2025)].groupby("year", as_index=False).cpi.mean()
    cpi.to_csv(RAW / "cpi_u_annual.csv", index=False)
    print(f"  wrote {len(cpi)} annual CPI values")


if __name__ == "__main__":
    main()
