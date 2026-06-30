# Item ladders v0.5 — oxygenation set (now unblocked)

Built against `bearers_v0.5.txt`. the clinician's Q2 answer removed the blocker: there are no
implausible (P/F, support) cells, so every couple is a real patient and the grid can be
saturated freely. These join the buildable-now set (Ladders A/C/F/D, unchanged) to
complete the ~30-item benchmark.

Every item here honours `@copresent pf & rs`: it carries exactly one P/F tier **and** one
support tier. Verdicts are **placeholders** for the panel to overwrite. Mutex respected
within each family.

---

## Ladder B — target `ards` (now buildable)

Base X = {ad, bi_diffuse, pf_mod, rs_imvlow} — acute dyspnoea + diffuse bilateral
opacities + P/F 100–200 on invasive ventilation at low PEEP. Meets the oxygenation +
imaging criteria; deliberately missing a risk factor and any cardiac/fluid exclusion, so
the ladder supplies both. Reproduces the deck's central contested items as RSR rungs.

| # | change to Γ | type | placeholder | rationale (panel overwrites) |
|---|---|---|---|---|
| B0 | — (base) | — | abstain | oxygenation+imaging met; no risk factor, cardiac/fluid not addressed |
| B1 | +asp | strengthen | good | aspiration is a recognised ARDS risk factor |
| B2 | +sep | strengthen | good | sepsis is the leading ARDS risk factor |
| B3 | +cd_pneumotox | strengthen | good | pneumotoxic agent supplies the insult |
| B4 | pf_mod → pf_severe | strengthen | good | worse hypoxaemia at same support → severe ARDS (mutex swap) |
| B5 | +asp +ef_reduced | contested | contested | **deck item "aspiration + low LVEF → ARDS"**; Berlin "not fully explained by cardiac" vs coexistence |
| B6 | +bnp_vhi | contested | bad(strict)/contested | thousands-level BNP points cardiac |
| B7 | +cd_cardiotox | defeat | bad | **deck worked example**; cardiotoxic agent → cardiogenic pathway, not ARDS |
| B8 | +fluid_verypos | contested | contested | very positive balance → hydrostatic contribution; the Global Definition's fluid-overload exclusion now bites |

B5–B8 are where the panel rationales are non-optional — they're the strict-Global-
Definition-vs-bedside splits.

## Ladder G — cross-family monotonicity: support at fixed oxygenation  [new in v0.5]

This is the ladder the clinician's regularity hands us. He said more support generally raises P/F —
so a P/F held *fixed* while support *climbs* describes a lung that needs escalating support
to achieve the same oxygenation, i.e. progressively sicker. The test: does the model treat
"same P/F, more support" as at least as severe?

Base X = {ad, bi_diffuse, asp, pf_mild} (risk factor present; P/F 200–300 held fixed),
walk the support family. Endorsement of `ards` should be **non-decreasing** as support
climbs; a *decrease* (treating the high-support patient as less likely ARDS because the P/F
"only" sits at mild) is the diagnostic error this ladder catches.

| # | rs tier (pf_mild fixed) | placeholder | expected |
|---|---|---|---|
| G1 | rs_hfnc | contested | borderline — mild P/F on minimal support |
| G2 | rs_niv | good | ↑ |
| G3 | rs_imvlow | good | ↑ |
| G4 | rs_imvmiddle | good | = / ↑ |
| G5 | rs_imvhigh | good | = (max support for only-mild P/F → clearly sick) |

(Five separate items, one support tier each.) This is the inferential content of the
coupling — evaluated, per the vocabulary note, not enforced. Note the regularity is
*defeasible*: a stiff lung can sit at a low P/F on modest support, which is exactly why
this is a test of mastery rather than an analytic truth.

## Saturation note

Ladders B and G fix one slice of the pf × rs grid each (B walks risk factors at a fixed
couple then swaps the P/F tier; G walks support at fixed P/F). The full grid is 4 × 5 = 20
couples; we are **not** enumerating it — that would blow the item budget on cells that test
nothing new. The ladders sample the grid where the inference is interesting: B at the
cardiac/fluid-exclusion boundary, G along the support axis where the clinician's coupling lives.

---

## Benchmark now complete

| set | items |
|---|---|
| A (cpe RSR) | 10 |
| C (BNP monotonicity) | 5 |
| F (fluid monotonicity) | 3 |
| D (abstain anchors) | 3 |
| B (ards RSR) | 9 |
| G (support-vs-P/F monotonicity) | 5 |
| **total** | **35** |

Slightly over the 30 ceiling — trim candidates are the easy strengthener rungs (A4/A5,
B2/B3) before the contested ones, since the contested rungs are where the signal is.

## Before any human sees it

Run the model panel over all 35 first (the dry run gate): confirms coherent rendering of
the (pf, rs) couples and flags the split items worth a clinician's minute. Only then the
pilot.
