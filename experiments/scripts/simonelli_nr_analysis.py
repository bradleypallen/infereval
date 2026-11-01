"""Analysis for the simonelli-nr sweep: paper tables 1-3 + 3-section diff.

Notation (2026-10-31 revision): no expression-function notation — bearers
are referred to directly and the non-reflectivity bearer is written
$\\neg r$ (code-level ids stay ``nr``).

Emits:
1. ``table1_simonelli_nr.tex`` — benchmark items: $\\Gamma_i$, the verbatim
   premise context $\\mathrm{ctx}_\\Gamma(\\Gamma_i)$ read from the run
   logs, role, analyst verdict.
2. ``table2_simonelli_nr.tex`` — the four conclusion wordings
   $\\mathrm{ctx}_\\Delta(\\{ra\\})$, verbatim from the run logs, with
   reading glosses.
3. ``table3_simonelli_nr.tex`` — model x four-wording table, conventions
   as superscript LETTERS: a = degenerate model column, b = abstain with
   perfect substantive agreement, c = non-unanimous vote (splits listed
   in the caption as good/bad/abstain out of 5).
4. ``diff_summary.md`` in the sweep dir, three sections: (1) 28 Oct
   (retroreflective nr) vs 31 Oct (Simonelli nr) for the three shared
   wordings, majority-verdict differences flagged; (2) physical vs
   physical-indicative within 31 Oct, with the two pre-registered
   predictions scored; (3) thin addendum, four wordings, vs 28 Oct
   counterparts where they exist.

Tables 1-2 are built from ``item.started`` prompts in the gpt-4.1 run
logs and cross-checked against ``sweep_manifest.json``; premise contexts
are asserted identical across all four wordings before anything is
written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from infereval.evaluation import Evaluation  # noqa: E402
from infereval.metrics import MetricsReport  # noqa: E402

MODEL_ORDER = [
    "claude-opus-4.7", "claude-haiku-4.5",
    "deepseek-v4-flash", "deepseek-v4-pro",
    "gemini-2.5-flash", "gemini-2.5-pro",
    "gpt-4.1", "gpt-5.4", "gpt-5.4-mini",
    "mistral-small", "qwen3.8-max", "qwen3.6-flash",
]
WORDINGS = ["original", "physical", "physical-indicative", "perceptual"]
SHARED = ["original", "physical", "perceptual"]  # exist in the 28 Oct sweep
ROWS = ["row-0", "row-1", "row-2", "row-3"]
ANALYST = ["good", "good", "good", "bad"]
LETTER = {"good": "G", "bad": "B", "abstain": "A"}

DEFAULT_SWEEP = REPO_ROOT / "experiments/results/stop_sign/simonelli_nr_2026-10-31"
DEFAULT_OLD = REPO_ROOT / "experiments/results/stop_sign/physical_wording_2026-10-28"
PAPER_REPO = Path("/Users/bradleyallen/Documents/GitHub/stop-sign-note")
DEFAULT_TABLE1_OUT = PAPER_REPO / "table1_simonelli_nr.tex"
DEFAULT_TABLE2_OUT = PAPER_REPO / "table2_simonelli_nr.tex"
DEFAULT_TABLE_OUT = PAPER_REPO / "table3_simonelli_nr.tex"

#: Presentation of each item's premise set (display order follows the
#: paper's base-plus-additions narrative; sets are unordered) and the
#: analyst's role gloss. The non-reflectivity bearer renders as \neg r.
GAMMA = {
    "row-0": r"\{sa\}",
    "row-1": r"\{sa, n\}",
    "row-2": r"\{sa, \neg r, n\}",
    "row-3": r"\{sa, ba\}",
}
ROLE = {
    "row-0": "base inference",
    "row-1": "irrelevant addition",
    "row-2": "irrelevant addition",
    "row-3": "defeater",
}
GLOSS = {
    "original": "Simonelli's wording; ambiguous between readings --- "
                "the analyst row fixes the intrinsic one",
    "physical": "subjunctive dispositional reflectance; leaves a "
                "kind-property reading available",
    "physical-indicative": r"drops the subjunctive mood and the "
                           r"illumination rider from \texttt{physical}",
    "perceptual": "episodic visible appearance; rows 1--2's additions "
                  "become defeaters",
}


def latexify(s: str) -> str:
    """Typeset a verbatim prompt string: math-mode the object variable
    ``a`` (only where it is the variable, i.e. before is/has/visibly/'s —
    the article ``a`` is never followed by these), en dash, thin-space nm."""
    s = s.replace("–", "--")
    s = re.sub(r"(\d) nm\b", r"\1\\,nm", s)
    s = re.sub(r"\ba('s| is| has| visibly)", r"$a$\1", s)
    return s


def read_prompts(sweep: Path, model: str = "gpt-4.1"):
    """Verbatim premise/conclusion strings from the run logs, with
    identity assertions across wordings and against the manifest."""
    per_wording = {}
    for w in WORDINGS:
        prem, conc = {}, set()
        for line in (sweep / f"{model}-{w}.jsonl").read_text().splitlines():
            ev = json.loads(line)
            if ev.get("event") == "item.started":
                p = ev["prompt"]
                prem[ev["item_id"]] = p.split("Premises: ")[1].split("\n")[0]
                conc.add(p.split("Conclusion: ")[1].split("\n")[0])
        assert len(conc) == 1, f"{w}: conclusion varies across items"
        assert set(prem) == set(ROWS), f"{w}: items missing from log"
        per_wording[w] = (prem, conc.pop())
    contexts = per_wording[WORDINGS[0]][0]
    for w in WORDINGS[1:]:
        assert per_wording[w][0] == contexts, \
            f"premise contexts differ under {w}"
    manifest = json.loads((sweep / "sweep_manifest.json").read_text())
    conclusions = {w: per_wording[w][1] for w in WORDINGS}
    for w in WORDINGS:
        assert conclusions[w] == manifest["variants"][w].replace("$", ""), \
            f"{w}: logged conclusion differs from manifest variant"
    assert manifest["nr_expression"] in contexts["row-2"], \
        "manifest nr_expression not in the row-2 context"
    print(f"read_prompts: contexts identical across {len(WORDINGS)} "
          f"wordings; conclusions match manifest; nr clause verified "
          f"in row-2 (model={model})")
    return contexts, conclusions


def write_table1(out: Path, contexts: dict[str, str]) -> None:
    lines = [
        "% Table 1 (benchmark items, simonelli-nr capture of 2026-10-31),",
        "% generated by experiments/scripts/simonelli_nr_analysis.py.",
        "% Premise contexts are verbatim from the run logs (item.started",
        "% prompts), asserted identical across all four conclusion",
        "% wordings. Notation: no expression-function notation; the",
        "% non-reflectivity bearer is \\neg r (code id 'nr').",
        r"\begin{table}[ht]",
        r"\centering",
        r"\small",
        r"\begin{tabular}{c l p{6.6cm} l c}",
        r"\toprule",
        r"$i$ & $\Gamma_i$ & $\mathrm{ctx}_\Gamma(\Gamma_i)$ & Role & "
        r"Analyst \\",
        r"\midrule",
    ]
    for i, rid in enumerate(ROWS):
        verdict = ANALYST[i]
        lines.append(
            f"{i} & ${GAMMA[rid]}$ & ``{latexify(contexts[rid])}'' & "
            f"{ROLE[rid]} & \\textit{{{verdict}}} \\\\")
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Benchmark items of the 31 October 2026 capture. "
        r"Premise contexts $\mathrm{ctx}_\Gamma(\Gamma_i)$ are the strings "
        r"sent to the models, verbatim from the run logs (the object "
        r"variable $a$ is typeset in math mode; conjunct order follows the "
        r"benchmark's stored premise order). The $\neg r$ premise is "
        r"Simonelli's clause verbatim. The conclusion is $ra$ under each "
        r"of the four wordings of "
        r"Table~\ref{tab:wordings-simonelli-nr}; roles are the analyst's "
        r"reading, and the analyst row (\textit{good}, \textit{good}, "
        r"\textit{good}, \textit{bad}) is held fixed under every wording.}",
        r"\label{tab:items-simonelli-nr}",
        r"\end{table}",
        "",
    ]
    out.write_text("\n".join(lines))
    print(f"wrote {out}")


def write_table2(out: Path, conclusions: dict[str, str]) -> None:
    lines = [
        "% Table 2 (conclusion wordings, simonelli-nr capture of",
        "% 2026-10-31), generated by",
        "% experiments/scripts/simonelli_nr_analysis.py. Wordings are",
        "% verbatim from the run logs (item.started prompts), asserted",
        "% equal to sweep_manifest.json variants.",
        r"\begin{table}[ht]",
        r"\centering",
        r"\small",
        r"\begin{tabular}{l p{6.2cm} p{5.2cm}}",
        r"\toprule",
        r"Variant & $\mathrm{ctx}_\Delta(\{ra\})$ & Reading it selects \\",
        r"\midrule",
    ]
    for w in WORDINGS:
        lines.append(
            rf"\texttt{{{w}}} & ``{latexify(conclusions[w])}'' & "
            f"{GLOSS[w]} \\\\")
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Conclusion wordings of the 31 October 2026 capture: "
        r"$\mathrm{ctx}_\Delta(\{ra\})$ per variant, verbatim as sent to "
        r"the models (the object variable $a$ is typeset in math mode). "
        r"The premises of Table~\ref{tab:items-simonelli-nr}, including "
        r"the $\neg r$ clause, are identical across all four variants; "
        r"the analyst row is G\,G\,G\,B for every variant.}",
        r"\label{tab:wordings-simonelli-nr}",
        r"\end{table}",
        "",
    ]
    out.write_text("\n".join(lines))
    print(f"wrote {out}")


def verdict_row(p: Path) -> list[str]:
    d = json.loads(p.read_text())
    v = {it["id"]: it["model_verdict"] for it in d["items"]}
    return [v[r] for r in ROWS]


def vote_splits(p: Path) -> dict[str, tuple[int, int, int]]:
    d = json.loads(p.read_text())
    out = {}
    for it in d["items"]:
        mv = it["majority_vote"]
        g, b, a = mv["good"], mv["bad"], mv["abstain"]
        if max(g, b, a) < g + b + a:
            out[it["id"]] = (g, b, a)
    return out


def kappa_of(p: Path) -> float | None:
    return MetricsReport(eta=Evaluation.load(p)).cohens_kappa()


def letters(row: list[str]) -> str:
    cells = []
    for v, ref in zip(row, ANALYST):
        ch = LETTER[v]
        cells.append(rf"\textbf{{{ch}}}" if v != ref and v != "abstain" else ch)
    return r"\,".join(cells)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sweep-dir", type=Path, default=DEFAULT_SWEEP)
    ap.add_argument("--old-dir", type=Path, default=DEFAULT_OLD)
    ap.add_argument("--table1-out", type=Path, default=DEFAULT_TABLE1_OUT)
    ap.add_argument("--table2-out", type=Path, default=DEFAULT_TABLE2_OUT)
    ap.add_argument("--table-out", type=Path, default=DEFAULT_TABLE_OUT)
    args = ap.parse_args(argv)
    sweep, old_dir = args.sweep_dir, args.old_dir

    contexts, conclusions = read_prompts(sweep)
    write_table1(args.table1_out, contexts)
    write_table2(args.table2_out, conclusions)

    rows_, kappas, splits = {}, {}, {}
    for m in MODEL_ORDER:
        for w in WORDINGS:
            p = sweep / f"{m}-{w}.json"
            rows_[(m, w)] = verdict_row(p)
            kappas[(m, w)] = kappa_of(p)
            sp = vote_splits(p)
            if sp:
                splits[(m, w)] = sp

    # ---- Table -------------------------------------------------------------
    marks: set[str] = set()

    def kcell(k: float | None, row: list[str], m: str, w: str) -> tuple[str, str]:
        note = ""
        if len(set(row)) == 1:
            note += "a"
            marks.add("a")
        elif "abstain" in row and k == 1.0:
            note += "b"
            marks.add("b")
        if (m, w) in splits:
            note += "c"
            marks.add("c")
        ktxt = "und." if k is None else f"${k:+.3f}$"
        if note:
            ktxt += rf"$^{{\mathrm{{{note}}}}}$"
        return ktxt, note

    lines = [
        "% Table 3 (four-wording results, Simonelli nr clause), generated by",
        "% experiments/scripts/simonelli_nr_analysis.py on branch",
        "% physical-wording. Sweep: simonelli_nr_2026-10-31; the \\neg r",
        "% premise (code id 'nr') = 'a is not made with a reflective",
        "% material or coating to reflect car headlights' (Simonelli p. 15,",
        "% verbatim) in all conditions; analyst row G G G B for every",
        "% wording; v0.17.8 parser; n=5.",
        r"\begin{table}[ht]",
        r"\centering",
        r"\footnotesize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{l cc cc cc cc}",
        r"\toprule",
        r"& \multicolumn{2}{c}{\texttt{original}}"
        r" & \multicolumn{2}{c}{\texttt{physical}}"
        r" & \multicolumn{2}{c}{\texttt{phys.-indicative}}"
        r" & \multicolumn{2}{c}{\texttt{perceptual}} \\",
        r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}"
        r"\cmidrule(lr){8-9}",
        r"Model & rows 0--3 & $\kappa_C$ & rows 0--3 & $\kappa_C$ & "
        r"rows 0--3 & $\kappa_C$ & rows 0--3 & $\kappa_C$ \\",
        r"\midrule",
        r"Analyst (reference) & G\,G\,G\,B & --- & G\,G\,G\,B & --- & "
        r"G\,G\,G\,B & --- & G\,G\,G\,B & --- \\",
        r"\midrule",
    ]
    for m in MODEL_ORDER:
        cells = [m]
        for w in WORDINGS:
            ktxt, _ = kcell(kappas[(m, w)], rows_[(m, w)], m, w)
            cells.append(letters(rows_[(m, w)]))
            cells.append(ktxt)
        lines.append(" & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    cap = [
        r"\caption{Verdict rows ($E_M$ on items row-0\,\ldots\,row-3; "
        r"G = \textit{good}, B = \textit{bad}, A = \textit{abstain}) and "
        r"Cohen's $\kappa_C$ against the analyst row, per $ra$ "
        r"wording, with the $\neg r$ premise worded ``$a$ is not made with "
        r"a reflective material or coating to reflect car headlights'' "
        r"(Simonelli's clause verbatim) in all conditions. "
        r"Capture of 31 October 2026, "
        r"framework v0.17.8, $n_{\text{samples}}=5$, majority 3-of-5. Bold "
        r"marks departures from the analyst row. Twelve models were run; "
        r"mistral-large was excluded for persistent upstream rate-limiting.",
    ]
    if "a" in marks:
        cap.append(r"$^{\mathrm{a}}$Degenerate substantive subset: the "
                   r"model's column is constant, so $\kappa_C$ carries no "
                   r"agreement signal beyond the raw row shown.")
    if "b" in marks:
        cap.append(r"$^{\mathrm{b}}$Abstain present; substantive agreement "
                   r"is perfect on the remaining items.")
    if "c" in marks:
        parts = []
        for (m, w), sp in sorted(splits.items()):
            inner = ", ".join(f"{iid} {g}/{b}/{a}"
                              for iid, (g, b, a) in sorted(sp.items()))
            parts.append(f"{m} {w}: {inner}")
        cap.append(r"$^{\mathrm{c}}$Non-unanimous vote; splits as "
                   r"good/bad/abstain out of 5 --- " + "; ".join(parts) + ".")
    lines.append(" ".join(cap) + "}")
    lines += [r"\label{tab:models-simonelli-nr}", r"\end{table}", ""]
    args.table_out.write_text("\n".join(lines))
    print(f"wrote {args.table_out}")

    # ---- Diff summary --------------------------------------------------------
    def fmt(row: list[str]) -> str:
        return " ".join(LETTER[v] for v in row)

    d = [
        "# Simonelli-nr sweep (2026-10-31): diff summary",
        "",
        "New: `simonelli_nr_2026-10-31` (delta(nr) = Simonelli's clause "
        "verbatim). Old: `physical_wording_2026-10-28` merged n=5 etas "
        "(delta(nr) = 'retroreflective sheeting'). Same frame, parser, "
        "budgets, roster.",
        "",
        "## 1. nr wording effect: 28 Oct vs 31 Oct (shared wordings)",
        "",
        "| Model | wording | retroreflective (28 Oct) | Simonelli (31 Oct) "
        "| changed items | majority differs? |",
        "|---|---|---|---|---|---|",
    ]
    n_flagged = 0
    for m in MODEL_ORDER:
        for w in SHARED:
            old = verdict_row(old_dir / f"{m}-{w}.n5.json")
            new = rows_[(m, w)]
            changed = [ROWS[i] for i in range(4) if old[i] != new[i]]
            flag = "**YES**" if changed else "no"
            n_flagged += bool(changed)
            d.append(f"| {m} | {w} | {fmt(old)} | {fmt(new)} | "
                     f"{', '.join(changed) if changed else '—'} | {flag} |")
    d += [
        "",
        "## 2. physical vs physical-indicative (31 Oct)",
        "",
        "| Model | physical | physical-indicative | changed items |",
        "|---|---|---|---|",
    ]
    pred_i_flips = 0
    pred_ii = {}
    for m in MODEL_ORDER:
        p_, pi = rows_[(m, "physical")], rows_[(m, "physical-indicative")]
        changed = [ROWS[i] for i in range(4) if p_[i] != pi[i]]
        d.append(f"| {m} | {fmt(p_)} | {fmt(pi)} | "
                 f"{', '.join(changed) if changed else '—'} |")
        if pi[1] == "bad":
            pred_i_flips += 1
        if m in ("gpt-5.4", "mistral-small"):
            pred_ii[m] = (fmt(p_), fmt(pi))
    d += [
        "",
        "### Pre-registered predictions (sweep_manifest.json)",
        "",
        f"- (i) physical-indicative row-1 = bad for most models: "
        f"**{pred_i_flips}/12** models have row-1 bad under "
        f"physical-indicative.",
    ]
    for m, (a, b) in pred_ii.items():
        d.append(f"- (ii) {m}: physical {a} -> physical-indicative {b}.")
    d += [
        "",
        "## 3. Thin default-frame addendum (gpt-4.1, July config)",
        "",
        "| wording | 28 Oct (retroreflective) | 31 Oct (Simonelli) | note |",
        "|---|---|---|---|",
    ]
    for w in WORDINGS:
        new = verdict_row(sweep / f"thin-gpt-4.1-{w}.json")
        old_p = old_dir / f"thin-gpt-4.1-{w}.json"
        if old_p.is_file():
            old = verdict_row(old_p)
            changed = [ROWS[i] for i in range(4) if old[i] != new[i]]
            note = ", ".join(changed) if changed else "no change"
            olds = fmt(old)
        else:
            olds, note = "—", "new condition (no 28 Oct counterpart)"
        d.append(f"| {w} | {olds} | {fmt(new)} | {note} |")
    diff_path = sweep / "diff_summary.md"
    diff_path.write_text("\n".join(d) + "\n")
    print(f"wrote {diff_path} ({n_flagged} shared cells with nr-driven changes)")
    print("\n".join(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
