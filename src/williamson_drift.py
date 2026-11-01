"""Williamson's (1976) objection to Demsetz: does the saving from bidding last once the contract is let?

Oliver Williamson argued that franchise bidding works at the first auction but decays afterward: the
winner learns the job, contracts cannot foresee everything, renegotiation follows, and at renewal the
incumbent faces little real competition. If he is right, the cost advantage of contracted service should
shrink over the life of contracts and after an agency switches to a contractor. Two tests on the NTD
panel built by src/franchise_bidding.py:

  1. Year by year, 2015-2025, the contracted-vs-in-house gap inside the same agency and mode.
     A linear trend in the gap tests whether it is closing.
  2. An event study of agency-modes that switched entirely from in-house to contracted operation
     (outsourcers) and the reverse (insourcers). Each switcher's cost is measured against agencies in
     the same mode and year that never switched, with agency-mode fixed effects.

Run src/franchise_bidding.py first; this reads results/panel_cost_per_hour.csv.

Usage:
    python src/williamson_drift.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results"
EVENT_BINS = (-4, 5)   # event time is binned at -4 or earlier and +5 or later; judgment, few switchers see more
REF = -1               # the year before the switch is the reference year
MIN_PRE, MIN_POST = 2, 2  # a switcher needs at least two years observed on each side of the switch; judgment
MODES = {"MB": "Bus", "CB": "Commuter bus", "DR": "Demand response"}


def fit(formula, data, weights=None):
    model = smf.wls(formula, data=data, weights=weights) if weights is not None else smf.ols(formula, data=data)
    return model.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(data.ntd_id)[0]})


def gap_by_year(p):
    """Contracted minus in-house log cost per hour, by year, inside agency-modes that run both."""
    both = p.groupby("am").pt.agg(["min", "max"])
    w = p[p.am.isin(both[(both["min"] == 0) & (both["max"] == 1)].index)].copy()
    years = sorted(w.year.unique())
    for y in years:
        w[f"pt_{y}"] = ((w.pt == 1) & (w.year == y)).astype(int)
    res = fit("lcph ~ " + " + ".join(f"pt_{y}" for y in years) + " + C(am) + C(year)", w)
    rows = []
    for y in years:
        t = f"pt_{y}"
        lo, hi = res.conf_int().loc[t]
        rows.append({"year": y, "coef_log": res.params[t], "se": res.bse[t], "pct_gap": 100 * (np.exp(res.params[t]) - 1),
                     "pct_ci_low": 100 * (np.exp(lo) - 1), "pct_ci_high": 100 * (np.exp(hi) - 1),
                     "contracted_rows": int(w[t].sum())})
    w["trend"] = w.year - years[0]
    tr = fit("lcph ~ pt + pt:trend + C(am) + C(year)", w)
    lo, hi = tr.conf_int().loc["pt:trend"]
    trend = {"test": "Change in contracted-vs-in-house gap per year, 2015-2025", "coef_log": tr.params["pt:trend"],
             "se": tr.bse["pt:trend"], "ci_low": lo, "ci_high": hi, "p": tr.pvalues["pt:trend"],
             "gap_2015_log": tr.params["pt"], "n_obs": int(tr.nobs), "n_clusters": w.ntd_id.nunique()}
    print(f"Gap by year: {w.am.nunique()} agency-modes; trend {trend['coef_log']:+.4f} log points a year "
          f"(p = {trend['p']:.3f})")
    return pd.DataFrame(rows), trend


def find_switchers(p):
    """Agency-modes with exactly one switch between all-in-house and all-contracted years."""
    tos = p.groupby(["am", "year"]).tos.agg(lambda s: "+".join(sorted(set(s)))).unstack("year")
    rows = []
    for am, seq in tos.iterrows():
        s = seq.dropna()
        if s.isin(["DO+PT"]).any() or s.nunique() != 2:
            continue
        changes = (s != s.shift()).iloc[1:]
        if changes.sum() != 1:
            continue
        year = int(changes[changes].index[0])
        pre, post = (s.index < year).sum(), (s.index >= year).sum()
        if pre >= MIN_PRE and post >= MIN_POST:
            rows.append({"am": am, "switch_year": year, "direction": "outsourced" if s.iloc[0] == "DO" else "insourced",
                         "years_before": int(pre), "years_after": int(post)})
    sw = pd.DataFrame(rows)
    print(f"Switchers with >= {MIN_PRE} years on each side: {(sw.direction == 'outsourced').sum()} outsourced, "
          f"{(sw.direction == 'insourced').sum()} insourced")
    return sw


def event_study(p, sw, direction, group, mode=None):
    """Event-time coefficients for one direction of switch, measured against agencies that never switched.

    Each switcher's log cost per hour is first expressed relative to the mean for agency-modes in the same
    mode and year that never changed how they operate (the mode-by-year baseline), then regressed on
    event-time dummies with agency-mode fixed effects.
    """
    mixed = p.groupby("am").tos.nunique()
    stayers = p[p.am.isin(mixed[mixed == 1].index)]
    base = stayers.groupby(["mode", "year"]).lcph.mean().rename("base")
    sw = sw[sw.direction == direction]
    if mode:
        sw = sw[sw.am.str.endswith("_" + mode)]
    s = sw.set_index("am").switch_year
    d = p[p.am.isin(s.index)].join(base, on=["mode", "year"])
    d["rel"] = d.lcph - d.base
    d["et"] = (d.year - d.am.map(s)).clip(*EVENT_BINS)
    terms = []
    for k in range(EVENT_BINS[0], EVENT_BINS[1] + 1):
        if k == REF:
            continue
        name = f"e_m{abs(k)}" if k < 0 else f"e_p{k}"
        d[name] = (d.et == k).astype(int)
        terms.append((k, name))
    res = fit("rel ~ " + " + ".join(n for _, n in terms) + " + C(am)", d)
    rows = []
    for k, n in terms:
        lo, hi = res.conf_int().loc[n]
        rows.append({"group": group, "event_time": k, "coef_log": res.params[n], "se": res.bse[n],
                     "p": res.pvalues[n], "pct": 100 * (np.exp(res.params[n]) - 1),
                     "pct_ci_low": 100 * (np.exp(lo) - 1), "pct_ci_high": 100 * (np.exp(hi) - 1),
                     "switcher_rows": int(d[n].sum())})
    rows.append({"group": group, "event_time": REF, "coef_log": 0.0, "se": 0.0, "p": np.nan, "pct": 0.0,
                 "pct_ci_low": 0.0, "pct_ci_high": 0.0, "switcher_rows": int((d.et == REF).sum())})
    # pooled before/after: average of years 0..+5 against average of years -4..-2, relative to year -1
    post = [n for k, n in terms if k >= 0]
    pre = [n for k, n in terms if k < REF]
    pooled = res.t_test(f"({' + '.join(post)}) / {len(post)} - ({' + '.join(pre)}) / {len(pre)} = 0")
    early = res.t_test("(e_p0 + e_p1) / 2 = 0")
    late = res.t_test("(e_p3 + e_p4 + e_p5) / 3 - (e_p0 + e_p1) / 2 = 0")
    summary = []
    for label, t in [("after minus before (years 0..+5 vs -4..-2)", pooled), ("first two years after vs year -1", early),
                     ("years +3..+5 minus years 0..+1 (drift)", late)]:
        b, se = float(np.squeeze(t.effect)), float(np.squeeze(t.sd))
        summary.append({"group": group, "contrast": label, "coef_log": b, "se": se,
                        "p": float(np.squeeze(t.pvalue)), "pct": 100 * (np.exp(b) - 1),
                        "switchers": len(s), "n_obs": int(res.nobs), "n_clusters": d.ntd_id.nunique(),
                        "stayer_agency_modes": stayers.am.nunique()})
    return pd.DataFrame(rows).sort_values("event_time"), pd.DataFrame(summary)


def switcher_names(p, sw):
    """Before/after cost per hour (2025 dollars) for the largest switchers."""
    out = []
    for _, r in sw.iterrows():
        s = p[p.am == r.am]
        before = s[s.year.between(r.switch_year - 2, r.switch_year - 1)]
        after = s[s.year.between(r.switch_year, r.switch_year + 1)]
        if before.empty or after.empty:
            continue
        out.append({"agency_name": s.agency_name.iloc[0], "state": s.state.iloc[0], "mode": MODES[s["mode"].iloc[0]],
                    "direction": r.direction, "switch_year": r.switch_year,
                    "cost_per_hour_before": before.opex_real.sum() / before.vrh.sum(),
                    "cost_per_hour_after": after.opex_real.sum() / after.vrh.sum(),
                    "hours_after": after.vrh.mean()})
    t = pd.DataFrame(out)
    t["change_pct"] = 100 * (t.cost_per_hour_after / t.cost_per_hour_before - 1)
    return t.sort_values("hours_after", ascending=False)


def plot(gap, events):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.fill_between(gap.year, gap.pct_ci_low, gap.pct_ci_high, color="#1f5a96", alpha=0.15)
    ax.plot(gap.year, gap.pct_gap, marker="o", color="#1f5a96")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_title("Contracted vs in-house cost per hour,\nsame agency and mode", fontsize=10)
    ax.set_ylabel("Percent difference (95% CI)")
    ax.set_xticks(gap.year[::2])
    ax = axes[1]
    for i, (group, color) in enumerate([("Outsourced, bus", "#1f5a96"), ("Outsourced, demand response", "#d07b2a")]):
        e = events[events.group == group]
        ax.errorbar(e.event_time + (0.1 if i else -0.1), e.pct, yerr=[e.pct - e.pct_ci_low, e.pct_ci_high - e.pct],
                    fmt="o-", color=color, capsize=2, label=group)
    ax.axhline(0, color="black", lw=0.8)
    ax.axvline(-0.5, color="grey", lw=0.8, ls="--")
    ax.set_title("Cost per hour after moving to a contractor,\nrelative to the year before", fontsize=10)
    ax.set_xlabel("Years since switch (ends binned)")
    ax.set_ylabel("Percent vs non-switchers (95% CI)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "williamson_drift.png", dpi=150)
    plt.close(fig)


def main():
    p = pd.read_csv(OUT / "panel_cost_per_hour.csv", dtype={"ntd_id": str})
    print(f"Loaded panel: {len(p):,} agency-mode-service-year rows")
    p["lcph"] = np.log(p.cph)
    p["pt"] = (p.tos == "PT").astype(int)
    p["am"] = p.ntd_id + "_" + p["mode"]

    gap, trend = gap_by_year(p)
    gap.to_csv(OUT / "gap_by_year.csv", index=False, float_format="%.4f")
    sw = find_switchers(p)
    sw.to_csv(OUT / "switchers.csv", index=False)
    ev, summ = [], []
    for group, direction, mode in [("Outsourced, all modes", "outsourced", None), ("Outsourced, bus", "outsourced", "MB"),
                                   ("Outsourced, demand response", "outsourced", "DR"),
                                   ("Insourced, all modes", "insourced", None)]:
        e, s = event_study(p, sw, direction, group, mode)
        ev.append(e), summ.append(s)
    events, summary = pd.concat(ev), pd.concat(summ)
    events.to_csv(OUT / "event_study.csv", index=False, float_format="%.4f")
    trend_row = pd.DataFrame([trend])
    summary.to_csv(OUT / "williamson_tests.csv", index=False, float_format="%.4f")
    trend_row.to_csv(OUT / "gap_trend.csv", index=False, float_format="%.4f")
    switcher_names(p, sw).to_csv(OUT / "switcher_names.csv", index=False, float_format="%.2f")
    plot(gap, events)
    print(gap[["year", "pct_gap", "pct_ci_low", "pct_ci_high"]].round(1).to_string(index=False))
    print(summary[["group", "contrast", "pct", "p", "switchers"]].round(3).to_string(index=False))
    print(f"Wrote results to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
