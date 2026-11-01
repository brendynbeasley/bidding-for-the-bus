"""Demsetz (1968) on American transit: does bidding for the route bring the price down to cost?

Demsetz argued that a service with large economies of scale need not be priced as a monopoly if the
right to supply it is put out to bid: rivalry among bidders, not the number of firms that end up
producing, sets the price. US transit agencies run exactly this experiment. Many operate some bus or
paratransit service with their own employees and hand the rest to a private operator under a contract
that is usually competitively bid. This script

  1. builds a panel of operating cost per vehicle revenue hour, 2015-2025, for every agency, mode and
     type of service (directly operated vs purchased) in the National Transit Database;
  2. compares contracted with in-house cost inside the same agency and mode (agency-by-mode fixed
     effects, year effects, standard errors clustered by agency);
  3. splits 2025 contracted service by whether the contract was competitively bid or negotiated;
  4. relates the cost of competitively bid service to the number of contractor firms active in the
     state, the closest public stand-in for Demsetz's "number of bidders";
  5. tabulates who wins the contracts (national shares and concentration) and the agencies that run
     both kinds of service.

Run src/fetch_data.py first (or use the committed data/raw/ files), then:
    python src/franchise_bidding.py
"""

import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "results"

MODES = {"MB": "Bus", "CB": "Commuter bus", "DR": "Demand response"}  # road modes that agencies both run and contract
MIN_VRH = 2000          # drop agency-mode-service-years with under 2,000 revenue hours (about one vehicle); judgment
TRIM = (0.01, 0.99)     # trim cost per hour at the 1st/99th percentile within mode; judgment, guards against unit errors
BASE_YEAR = 2025        # dollars are 2025 dollars (CPI-U); 2025 is the latest NTD report year
COMPETITIVE_SHARE = 0.5 # a purchased agency-mode counts as competitively bid if at least half its contract dollars are
# Contractor parent groups. First Transit was bought by Transdev on 6 March 2023 (Transdev press release),
# so it is folded into Transdev. Agencies file Via's operating subsidiary as "Via (RiverNorth Transit)",
# so River North is folded into Via; Via Mobility Services (Colorado) is a separate nonprofit. Other names
# are grouped by the brand they file under.
GROUPS = [
    (r"\bTRANSDEV\b|\bFIRST TRANSIT\b|\bFIRST TRANSPORTATION\b", "Transdev (incl. First Transit)"),
    (r"^MV\b|\bMV TRANSPORT|\bMV PUBLIC|\bMV CONTRACT|\bMV TRANSIT", "MV Transportation"),
    (r"\bKEOLIS\b", "Keolis"),
    (r"\bRATP\s?DEV\b|\bMCDONALD TRANSIT\b", "RATP Dev"),
    (r"\bMTM\b|MEDICAL TRANSPORTATION MANAGEMENT", "MTM Transit"),
    (r"\bNATIONAL EXPRESS\b|\bDURHAM SCHOOL\b|\bTRANSPORTATION CONCEPTS\b", "National Express"),
    (r"^(?!.*VIA MOBILITY).*(\bVIA\b|\bRIVER ?NORTH\b)", "Via (incl. River North Transit)"),
    (r"\bUBER\b", "Uber"),
    (r"\bLYFT\b", "Lyft"),
    (r"\bZTRIP\b", "zTrip"),
    (r"\bA\s?BAR\s?A\b", "A-Bar-A"),
    (r"\bSOUTHLAND TRANSIT\b", "Southland Transit"),
    (r"\bEASTON COACH\b", "Easton Coach"),
]
COUNTS = []            # sample funnel, written to results/sample_counts.csv


def note(step, n):
    COUNTS.append({"step": step, "rows": int(n)})


SUFFIX = re.compile(r"\b(INC|INCORPORATED|LLC|L L C|CORP|CORPORATION|CO|COMPANY|LTD|LP|DBA.*|USA)\b")


def contractor_group(name):
    """Map a contractor name as filed to a parent group (or a cleaned version of the name)."""
    n = re.sub(r"['\u2019]", "", str(name).upper())
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    for pattern, group in GROUPS:
        if re.search(pattern, n):
            return group
    return re.sub(r"\s+", " ", SUFFIX.sub("", n)).strip().title()


def load_panel():
    """Agency x mode x type-of-service x year panel of cost per vehicle revenue hour, 2025 dollars."""
    d = pd.read_csv(RAW / "ntd_ts21_by_mode_2015_2025.csv", dtype={"ntd_id": str})
    print(f"Loaded Time Series 2.1: {len(d):,} agency-mode-service-year rows, {d.report_year.min()}-{d.report_year.max()}")
    note("Time Series 2.1 agency-mode-service-years, 2015-2025", len(d))
    d = d.rename(columns={"type_of_service": "tos", "report_year": "year"})
    n0 = len(d)
    d = d[d["mode"].isin(MODES) & d.tos.isin(["DO", "PT"])]
    print(f"  kept {len(d):,} bus, commuter-bus and demand-response rows that are directly operated or purchased "
          f"(dropped {n0 - len(d):,}: rail, ferry, vanpool and other modes, and taxi or ride-hail purchased service)")
    note("bus, commuter bus, demand response; directly operated or purchased", len(d))
    n1 = len(d)
    d = d[(d.opex > 0) & (d.vrh >= MIN_VRH)]
    print(f"  kept {len(d):,} with positive operating expense and at least {MIN_VRH:,} revenue hours (dropped {n1 - len(d):,})")
    note(f"positive expense and at least {MIN_VRH} revenue hours", len(d))
    cpi = pd.read_csv(RAW / "cpi_u_annual.csv").set_index("year").cpi
    d["opex_real"] = d.opex * cpi[BASE_YEAR] / d.year.map(cpi)
    d["cph"] = d.opex_real / d.vrh
    lo = d.groupby("mode").cph.transform(lambda s: s.quantile(TRIM[0]))
    hi = d.groupby("mode").cph.transform(lambda s: s.quantile(TRIM[1]))
    n2 = len(d)
    d = d[d.cph.between(lo, hi)].copy()
    print(f"  kept {len(d):,} after trimming cost per hour at the 1st/99th percentile by mode (dropped {n2 - len(d):,})")
    note("after trimming cost per hour at 1st/99th percentile by mode", len(d))
    d["lcph"] = np.log(d.cph)
    d["pt"] = (d.tos == "PT").astype(int)
    d["am"] = d.ntd_id + "_" + d["mode"]
    d["rural"] = (d.reporting_module.fillna("") != "Urban").astype(int)
    d["luza"] = np.log(d.uza_population.where(d.uza_population > 0, 1))
    d["lvrh"] = np.log(d.vrh)
    return d


def load_contracts():
    """2025 purchased-transportation contracts where the reporting agency is the buyer."""
    c = pd.read_csv(RAW / "ntd_contracts_2025.csv", dtype={"ntd_id": str})
    print(f"Loaded 2025 contractual relationships: {len(c):,} contracts")
    n0 = len(c)
    c = c[c.reporter_contractual_position.eq("The Reporter is the Buyer") & c["mode"].isin(MODES) & c.tos.eq("PT")]
    print(f"  kept {len(c):,} bus, commuter-bus and demand-response contracts bought by the reporting agency "
          f"(dropped {n0 - len(c):,})")
    note("2025 contracts, all modes and positions", n0)
    note("2025 bus, commuter bus, demand response contracts bought by the reporter", len(c))
    c["group"] = c.contractee_operator_name.map(contractor_group)
    c["competitive"] = c.type_of_contract.eq("Competitively-Bid Contract").astype(int)
    c["dollars"] = pd.to_numeric(c.total_modal_expenses, errors="coerce").fillna(0)
    c["vehicles"] = c.buyer_supplies_vehicles_to.astype(str).str.lower().eq("true").astype(int)
    c["am"] = c.ntd_id + "_" + c["mode"]
    return c


def agency_mode_contracts(c):
    """One row per purchased agency-mode: competitive share of contract dollars, largest contractor."""
    c = c.assign(comp_dollars=c.dollars * c.competitive, veh_dollars=c.dollars * c.vehicles)
    g = c.groupby("am").agg(dollars=("dollars", "sum"), comp_dollars=("comp_dollars", "sum"),
                            veh_dollars=("veh_dollars", "sum"), n_contracts=("dollars", "size"),
                            any_comp=("competitive", "max"))
    g["comp_share"] = np.where(g.dollars > 0, g.comp_dollars / g.dollars.where(g.dollars > 0, 1), g.any_comp)
    g["buyer_vehicles"] = np.where(g.dollars > 0, g.veh_dollars / g.dollars.where(g.dollars > 0, 1), 0)
    top = c.sort_values("dollars", ascending=False).drop_duplicates("am").set_index("am")
    g["contractor"] = top.group
    g["contract_type"] = np.where(g.comp_share >= COMPETITIVE_SHARE, "Competitively bid", "Negotiated or other")
    return g


def fit(formula, data, cluster, weights=None):
    model = smf.wls(formula, data=data, weights=weights) if weights is not None else smf.ols(formula, data=data)
    groups = pd.factorize(data[cluster])[0]
    return model.fit(cov_type="cluster", cov_kwds={"groups": groups})


def row(label, res, term, data, cluster, note=""):
    b, se = res.params[term], res.bse[term]
    lo, hi = res.conf_int().loc[term]
    return {"test": label, "term": term, "coef_log": b, "se": se, "ci_low": lo, "ci_high": hi, "p": res.pvalues[term],
            "pct_effect": 100 * (np.exp(b) - 1), "pct_ci_low": 100 * (np.exp(lo) - 1),
            "pct_ci_high": 100 * (np.exp(hi) - 1), "n_obs": int(res.nobs), "n_clusters": data[cluster].nunique(),
            "n_agency_modes": data.am.nunique(),
            "note": note}


def within_tests(panel, am):
    """Contracted vs in-house cost per hour inside the same agency and mode."""
    both = panel.groupby("am").pt.agg(["min", "max"])
    both = both[(both["min"] == 0) & (both["max"] == 1)].index
    w = panel[panel.am.isin(both)].copy()
    print(f"Within test: {w.am.nunique()} agency-modes ({w.ntd_id.nunique()} agencies) observed both in-house and "
          f"contracted at some point in 2015-2025; {len(w):,} rows")
    rows = []
    f = "lcph ~ pt + C(am) + C(year)"
    rows.append(row("Panel 2015-25, all three modes", fit(f, w, "ntd_id"), "pt", w, "ntd_id",
                    "agency-by-mode and year fixed effects; clustered by agency"))
    rows.append(row("Panel 2015-25, weighted by revenue hours", fit(f, w, "ntd_id", w.vrh), "pt", w, "ntd_id",
                    "same, each row weighted by its vehicle revenue hours"))
    for m, label in MODES.items():
        s = w[w["mode"] == m]
        if s.am.nunique() >= 5:
            rows.append(row(f"Panel 2015-25, {label.lower()} only", fit(f, s, "ntd_id"), "pt", s, "ntd_id",
                            "agency and year fixed effects"))
    # 2025, contracted service split by how the contract was let
    y = w[w.year == BASE_YEAR].join(am[["contract_type"]], on="am")
    y = y[(y.pt == 0) | y.contract_type.notna()].copy()
    y["pt_comp"] = ((y.pt == 1) & (y.contract_type == "Competitively bid")).astype(int)
    y["pt_neg"] = ((y.pt == 1) & (y.contract_type == "Negotiated or other")).astype(int)
    keep = y.groupby("am").pt.transform(lambda s: s.nunique() == 2)
    y = y[keep]
    res = fit("lcph ~ pt_comp + pt_neg + C(am)", y, "ntd_id")
    rows.append(row("2025, competitively bid contract", res, "pt_comp", y, "ntd_id",
                    "agency-by-mode fixed effects; 2025 only"))
    rows.append(row("2025, negotiated or other contract", res, "pt_neg", y, "ntd_id",
                    f"{int(y.pt_neg.sum())} negotiated agency-modes"))
    return pd.DataFrame(rows), w


def cross_section(panel, am):
    """All 2025 agency-modes, with controls, including agencies that only do one or the other."""
    y = panel[panel.year == BASE_YEAR].join(am[["contract_type", "buyer_vehicles", "contractor"]], on="am")
    n0 = len(y)
    y = y[(y.pt == 0) | y.contract_type.notna()].copy()
    print(f"2025 cross-section: {len(y):,} agency-modes (dropped {n0 - len(y):,} purchased rows with no matching "
          f"buyer contract on form B-30)")
    y["pt_comp"] = ((y.pt == 1) & (y.contract_type == "Competitively bid")).astype(int)
    y["pt_neg"] = ((y.pt == 1) & (y.contract_type == "Negotiated or other")).astype(int)
    res = fit("lcph ~ pt_comp + pt_neg + C(mode) + lvrh + luza + rural + C(state)", y, "state")
    rows = [row("2025 cross-section, competitively bid", res, "pt_comp", y, "state",
                "mode and state effects, log hours, log urbanized-area population, rural; clustered by state"),
            row("2025 cross-section, negotiated or other", res, "pt_neg", y, "state", "same regression")]
    means = y.assign(service=np.where(y.pt == 0, "In-house", y.contract_type)).groupby(["mode", "service"]).agg(
        agency_modes=("cph", "size"), median_cost_per_hour=("cph", "median"),
        hours=("vrh", "sum"), dollars=("opex_real", "sum")).reset_index()
    means["pooled_cost_per_hour"] = means.dollars / means.hours
    means["mode"] = means["mode"].map(MODES)
    return pd.DataFrame(rows), means, y


def bidder_test(y, c):
    """Cost of competitively bid service against the number of contractor groups active in the state."""
    states = y[["ntd_id", "state"]].drop_duplicates("ntd_id").set_index("ntd_id").state
    c = c.assign(state=c.ntd_id.map(states)).dropna(subset=["state"])
    firms = c.groupby("state").group.nunique().rename("firms_in_state")
    s = y[y.pt_comp == 1].join(firms, on="state")
    s = s[s.firms_in_state.notna()].copy()
    s["lfirms"] = np.log(s.firms_in_state)
    print(f"Bidder test: {len(s)} competitively bid agency-modes in {s.state.nunique()} states; "
          f"contractor groups per state range {int(s.firms_in_state.min())}-{int(s.firms_in_state.max())}")
    res = fit("lcph ~ lfirms + C(mode) + lvrh + luza + rural + buyer_vehicles", s, "state")
    rows = [row("Competitively bid cost on log contractor groups in state", res, "lfirms", s, "state",
                "mode effects, log hours, log urbanized-area population, rural, buyer-supplied vehicles; "
                "clustered by state")]
    res2 = fit("lcph ~ lfirms + C(mode)", s, "state")
    rows.append(row("Same, mode effects only", res2, "lfirms", s, "state", "no other controls"))
    s["firm_bin"] = pd.cut(s.firms_in_state, [0, 3, 8, 20, 1000], labels=["1-3", "4-8", "9-20", "21+"])
    s["resid"] = smf.ols("lcph ~ C(mode)", data=s).fit().resid
    bins = s.groupby("firm_bin", observed=True).agg(agency_modes=("cph", "size"), states=("state", "nunique"),
                                                    median_cost_per_hour=("cph", "median"),
                                                    mean_log_cost_vs_mode=("resid", "mean")).reset_index()
    return pd.DataFrame(rows), bins, s


def market_shares(c):
    """Who wins the competitively bid contracts: shares of contract dollars and agency counts."""
    k = c[c.competitive == 1]
    g = k.groupby("group").agg(contract_dollars=("dollars", "sum"), contracts=("dollars", "size"),
                               agencies=("ntd_id", "nunique"))
    g["share_pct"] = 100 * g.contract_dollars / g.contract_dollars.sum()
    g = g.sort_values("contract_dollars", ascending=False).reset_index()
    hhi = float((g.share_pct ** 2).sum())
    print(f"Competitively bid contracts: {len(k):,}, ${k.dollars.sum() / 1e9:.2f} billion, {g.shape[0]} contractor "
          f"groups; national HHI {hhi:,.0f}")
    return g, hhi


def both_agencies(panel, am):
    """2025 agencies that run the same mode both in-house and by contract, with each cost per hour."""
    y = panel[panel.year == BASE_YEAR]
    p = y.pivot_table(index=["am", "agency_name", "state", "mode"], columns="tos", values=["cph", "vrh"]).dropna()
    p.columns = [f"{a}_{b}" for a, b in p.columns]
    p = p.reset_index().join(am[["contractor", "contract_type"]], on="am")
    p["contract_vs_inhouse_pct"] = 100 * (p.cph_PT / p.cph_DO - 1)
    p["opex_DO"], p["opex_PT"] = p.cph_DO * p.vrh_DO, p.cph_PT * p.vrh_PT
    p["contract_hours_at_inhouse_cost_minus_actual"] = (p.cph_DO - p.cph_PT) * p.vrh_PT
    p["mode"] = p["mode"].map(MODES)
    return p.sort_values("vrh_DO", ascending=False)


def plot_scatter(p):
    fig, ax = plt.subplots(figsize=(7, 6))
    colors = {"Bus": "#1f5a96", "Commuter bus": "#8a8a8a", "Demand response": "#d07b2a"}
    for m, s in p.groupby("mode"):
        ax.scatter(s.cph_DO, s.cph_PT, s=12 + 60 * np.sqrt(s.vrh_PT / p.vrh_PT.max()), alpha=0.75,
                   color=colors[m], label=f"{m} ({len(s)})", edgecolor="white", linewidth=0.5)
    lim = [20, max(p.cph_DO.max(), p.cph_PT.max()) * 1.1]
    ax.plot(lim, lim, color="black", lw=0.8)
    ax.text(lim[1] * 0.62, lim[1] * 0.66, "same cost", rotation=45, fontsize=8)
    ax.set_xscale("log"), ax.set_yscale("log")
    ax.set_xlim(lim), ax.set_ylim(lim)
    ticks = [25, 50, 100, 200, 300]
    ax.set_xticks(ticks, [f"${v}" for v in ticks]), ax.set_yticks(ticks, [f"${v}" for v in ticks])
    ax.minorticks_off()
    ax.set_xlabel("In-house operating cost per revenue hour, 2025 ($, log scale)")
    ax.set_ylabel("Contracted operating cost per revenue hour, 2025 ($, log scale)")
    ax.set_title("Same agency, same mode, 2025: points below the line are cheaper by contract", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "inhouse_vs_contract_2025.png", dpi=150)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    panel = load_panel()
    c = load_contracts()
    am = agency_mode_contracts(c)
    print(f"  {len(am):,} purchased agency-modes; {int((am.contract_type == 'Competitively bid').sum())} "
          f"competitively bid, {int((am.contract_type != 'Competitively bid').sum())} negotiated or other")
    panel.to_csv(OUT / "panel_cost_per_hour.csv", index=False,
                 columns=["ntd_id", "agency_name", "state", "mode", "tos", "year", "opex_real", "vrh", "cph"])

    within, _ = within_tests(panel, am)
    cross, means, y = cross_section(panel, am)
    bidders, bins, _ = bidder_test(y, c)
    tests = pd.concat([within, cross, bidders], ignore_index=True)
    tests.to_csv(OUT / "cost_tests.csv", index=False, float_format="%.4f")
    means.to_csv(OUT / "cost_by_service_2025.csv", index=False, float_format="%.2f")
    bins.to_csv(OUT / "bidders_bins.csv", index=False, float_format="%.4f")

    shares, hhi = market_shares(c)
    shares.to_csv(OUT / "contractor_shares_2025.csv", index=False, float_format="%.2f")
    pd.DataFrame([{"national_hhi_competitive_dollars": hhi, "contractor_groups": len(shares),
                   "competitive_contracts": int(c.competitive.sum()),
                   "competitive_dollars": float(c.loc[c.competitive == 1, "dollars"].sum()),
                   "all_contracts": len(c), "negotiated_or_other_contracts": int((1 - c.competitive).sum()),
                   "top3_share_pct": shares.share_pct.head(3).sum(),
                   "agency_modes_purchased": len(am),
                   "agency_modes_competitive": int((am.contract_type == "Competitively bid").sum()),
                   "agency_modes_negotiated": int((am.contract_type != "Competitively bid").sum())}]
                 ).to_csv(OUT / "contract_market_summary.csv", index=False, float_format="%.2f")

    p = both_agencies(panel, am)
    p.to_csv(OUT / "agencies_both_2025.csv", index=False, float_format="%.2f")
    summ = p.groupby("mode").agg(agency_modes=("am", "size"),
                                 contract_cheaper=("contract_vs_inhouse_pct", lambda s: int((s < 0).sum())),
                                 median_gap_pct=("contract_vs_inhouse_pct", "median")).reset_index()
    tot = pd.DataFrame([{"mode": "All", "agency_modes": len(p), "contract_cheaper": int((p.contract_vs_inhouse_pct < 0).sum()),
                         "median_gap_pct": p.contract_vs_inhouse_pct.median()}])
    pd.concat([summ, tot]).to_csv(OUT / "agencies_both_summary.csv", index=False, float_format="%.2f")
    pd.DataFrame(COUNTS).to_csv(OUT / "sample_counts.csv", index=False)
    plot_scatter(p)

    # The paper's own evidence, as quoted by Demsetz from Behling (1938): telephone service in 1902
    pd.DataFrame([{"cities_over_4000": 1051, "cities_with_telephone": 1002, "independent_monopoly": 137,
                   "bell_monopoly": 414, "duplicated_service": 451,
                   "duplicated_share_pct": 100 * 451 / 1002}]).to_csv(OUT / "paper_benchmark_1902.csv",
                                                                      index=False, float_format="%.1f")
    # Demsetz's mechanism in its simplest auction form: with N bidders whose unit costs are independent draws
    # from a uniform range [c_L, c_H], the winning price is the second-lowest cost, which sits on average
    # 2/(N+1) of the way up the range from the best cost.
    pd.DataFrame({"bidders": [1, 2, 3, 5, 10, 20]}).assign(
        expected_price_above_best_cost_share_of_range=lambda f: np.where(f.bidders > 1, 2 / (f.bidders + 1), np.nan)
    ).to_csv(OUT / "bidding_formula.csv", index=False, float_format="%.3f")
    print(tests[["test", "term", "pct_effect", "pct_ci_low", "pct_ci_high", "p", "n_obs", "n_clusters"]]
          .round(3).to_string(index=False))
    print(f"Wrote results to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
