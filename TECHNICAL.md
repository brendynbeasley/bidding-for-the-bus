# Technical notes

This is the technical companion to the [README](README.md). It covers the data, the rules fixed before running
the tests, the full set of statistics and how to reproduce everything. Every table is in
[results/FINDINGS.md](results/FINDINGS.md), and every number comes from a CSV in `results/`.

## The original study

Harold Demsetz, "Why Regulate Utilities?" *Journal of Law and Economics* 11(1), April 1968, pp. 55–65. The paper is
a theoretical argument with no estimates. Its claim is that economies of scale explain why one firm produces but not
why that firm charges a monopoly price, because rivals can bid for the exclusive right to serve the market; with
enough independent bidders and costly collusion, the winning price approaches unit cost. Its only figures are
historical, quoted from Behling (1938): 45 electric light companies licensed in Chicago in 1907, and a 1902 report
in which 451 of the 1,002 American cities over 4,000 people with telephone service had duplicated service
(`results/paper_benchmark_1902.csv`). The main critique is Williamson (1976), who argued that incomplete contracts,
renegotiation and incumbent advantage at renewal erode the auction's discipline after the first round.

## Headline results

| Test | Estimate (log points) | Percent | 95% CI (percent) | N | Clusters |
|---|---|---|---|---|---|
| Contracted vs in-house, same agency-mode, 2015–25 | −0.233 (0.029) | −20.8 | −25.2 to −16.2 | 4,676 | 289 agencies |
| Same, weighted by revenue hours | −0.370 (0.054) | −30.9 | −37.8 to −23.2 | 4,676 | 289 |
| 2025, competitively bid vs in-house, same agency-mode | −0.337 (0.071) | −28.6 | −37.9 to −17.9 | 184 | 79 |
| 2025, negotiated vs in-house, same agency-mode | −0.407 (0.264) | −33.5 | −60.3 to +11.6 | 184 | 79 |
| Log contractor groups in state (competitively bid only) | +0.048 (0.032) | +4.9 per log point | −1.4 to +11.6 | 611 | 50 (48 states, DC, PR) |
| Trend in the contracted gap, per year | −0.0003 (0.0043) | | | 4,676 | 289 |
| Outsourced bus, after minus before | +0.002 (0.048) | +0.2 | | 435 | 44 switches |
| Outsourced demand response, after minus before | +0.185 (0.044) | +20.3 | | 403 | 41 switches |

## Data

- `data/raw/ntd_ts21_by_mode_2015_2025.csv`: National Transit Database, 2025 report year, "Service Data and
  Operating Expenses by Mode (Time Series 2.1)", data.transportation.gov dataset `npsm-38gk`, downloaded
  1 November 2026. Five fields (operating expenses, vehicle revenue hours, vehicle revenue miles, unlinked trips,
  vehicles in maximum service) pivoted to one row per agency, mode, type of service and year; 41,009 rows.
- `data/raw/ntd_contracts_2025.csv`: NTD 2025 "Contractual Relationships" (form B-30), dataset `wfxt-cwgv`,
  1,781 contracts with contractor name, contract type and total modal expenses.
- `data/raw/cpi_u_annual.csv`: FRED `CPIAUCSL`, annual averages 2015–2025, for 2025 dollars.

## Method

Rules fixed before the tests were run:

- **Modes and service types.** Fixed-route bus (MB), commuter bus (CB) and demand response (DR); directly operated
  (DO) and purchased transportation (PT). Taxi (TX) and ride-hail (TN) purchased service are excluded so that every
  purchased row is a conventional operating contract.
- **Sample.** Positive operating expense and at least 2,000 vehicle revenue hours; cost per hour trimmed at the
  1st and 99th percentiles within mode. 31,746 agency-mode-service-years remain (`results/sample_counts.csv`).
- **Cost measure.** Operating expense in 2025 dollars divided by vehicle revenue hours, for agency $`a`$, mode $`m`$, type of service $`j`$ (DO or PT) and year $`t`$:

```math
c_{amjt} = \frac{E_{amjt} \cdot CPI_{2025} / CPI_t}{H_{amjt}}
```

- **Within test.** Agency-modes observed both DO and PT at some point in 2015–2025 (371 agency-modes, 289
  agencies). OLS with agency-by-mode and year fixed effects, standard errors clustered by agency:

```math
\ln c_{amjt} = \alpha_{am} + \lambda_t + \beta\, PT_{j} + \varepsilon_{amjt}
```

- **Contract type.** A purchased agency-mode is "competitively bid" if at least half its 2025 contract dollars are
  under contracts the agency reports as competitively bid; otherwise "negotiated or other" (negotiated agreements,
  mostly with other public bodies, and subsidized arrangements). 666 of 755 purchased agency-modes are competitively
  bid.
- **Bidder proxy.** $`F_s`$ is the number of distinct contractor groups holding any 2025 bus, commuter bus or
  demand-response contract in state $`s`$. Names are cleaned and grouped by parent: First Transit into Transdev
  (acquired 6 March 2023); River North Transit into Via (filed as "Via (RiverNorth Transit)" by agencies). Via
  Mobility Services, a Colorado nonprofit, is kept separate.

```math
\ln c_{am} = \gamma_m + \delta \ln F_{s(a)} + \theta_1 \ln H_{am} + \theta_2 \ln \text{Pop}_{u(a)} + \theta_3\, \text{Rural}_a + \theta_4\, \text{Veh}_{am} + u_{am}
```

  clustered by state, where $`\text{Veh}_{am}`$ is the share of contract dollars where the agency supplies vehicles.
- **Cross-section.** All 2025 agency-modes, with mode and state effects, log hours, log urbanized-area population
  and a rural indicator; clustered by state. 202 purchased rows with no buyer contract on form B-30 are dropped.
- **Williamson extension.** (a) The within regression with a separate PT coefficient for each year, and with a
  PT × linear trend term. (b) Switchers: agency-modes whose years are all DO and then all PT (or the reverse), with
  exactly one change and at least two years on each side. Each switcher's log cost is expressed relative to the
  mean for never-switching agency-modes in the same mode and year ($`r_{amt}`$), then

```math
r_{amt} = \alpha_{am} + \sum_{k \neq -1} \theta_k\, \mathbf{1}[t - T_{am} = k] + u_{amt}
```

  with event time binned at −4 and +5 and errors clustered by agency. Reported contrasts are the average of
  $`\theta_0..\theta_5`$ minus the average of $`\theta_{-4}..\theta_{-2}`$; the average of $`\theta_0, \theta_1`$;
  and the average of $`\theta_3..\theta_5`$ minus the average of $`\theta_0, \theta_1`$.

## Full statistics

Within test by mode (`results/cost_tests.csv`): bus −23.7% (CI −29.0 to −18.0, 148 agency-modes); demand response
−18.8% (−24.7 to −12.5, 205); commuter bus −16.2% (−27.6 to −2.9, 18). 2025 cross-section: competitively bid
−10.7% (−17.8 to −2.9, p = 0.008), negotiated −12.2% (−24.6 to +2.2, p = 0.093), N = 2,714, 56 state clusters.
Bidder test without controls: +4.9% per log point (−0.6 to +10.6, p = 0.081).

Gap by year (`results/gap_by_year.csv`), percent: 2015 −19.1, 2016 −18.5, 2017 −20.8, 2018 −21.8, 2019 −21.6,
2020 −25.6, 2021 −19.5, 2022 −22.6, 2023 −21.3, 2024 −21.1, 2025 −17.7. Trend p = 0.94.

Switchers (`results/williamson_tests.csv`): all 91 outsourcers, after minus before +9.7% (p = 0.003), drift +6.7%
(p = 0.018); bus outsourcers +0.2% (p = 0.98), drift +1.1% (p = 0.70); demand-response outsourcers +20.3%
(p < 0.001), first two years +18.0%, drift +14.4% (p = 0.008); 32 insourcers +7.3% (p = 0.38).

Contract market (`results/contractor_shares_2025.csv`): $8.77 billion in 854 competitively bid contracts; Transdev
34.8%, MV Transportation 13.1%, Keolis 8.7%; top three 56.6%; HHI 1,520 across 315 groups.

## Reproducing the results

```bash
pip install -r requirements.txt
python src/fetch_data.py            # optional: refreshes data/raw/ from data.transportation.gov and FRED
python src/franchise_bidding.py     # main tests, tables and the scatter figure
python src/williamson_drift.py      # year-by-year gap and switcher event study
```

The committed `data/raw/` files let the last two commands run offline. The NTD revises past years when agencies
resubmit, so a fresh download can move estimates slightly.

## References

- Behling, B. N. (1938). *Competition and Monopoly in Public Utility Industries*, pp. 19–20, as quoted in Demsetz (1968).
- Chadwick, E. (1859). Results of different principles of legislation and administration in Europe, as cited in Demsetz (1968).
- Demsetz, H. (1968). Why regulate utilities? *Journal of Law and Economics* 11(1), 55–65.
- Stigler, G. J. & Friedland, C. (1962). What can regulators regulate? The case of electricity. *Journal of Law and Economics* 5, 1–16.
- Williamson, O. E. (1976). Franchise bidding for natural monopolies: in general and with respect to CATV. *Bell Journal of Economics* 7(1), 73–104.
