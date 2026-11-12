# Formal specification

This page states the definitions `infereval` implements: how a model's verdicts become an implication frame, and how that frame is scored against analyst-labeled benchmarks. After each definition comes **In code**, the authoritative implementation site. Where the implementation goes beyond the basic definition, an **Implementation** note follows.

The basic definitions are stated for single-succedent implications $\langle \Gamma, \{\psi\} \rangle$, the case the stop-sign example uses. The code also handles arbitrary conclusion sets; the notes say how. For the intuitions behind the definitions, see [Concepts](concepts.md). For a symbol-to-code lookup, see the [Glossary](glossary.md).

## 1. Preliminaries

Let $V$ be a finite vocabulary of tokens and $L = V^{*}$ the set of finite token sequences. Following Hlobil and Brandom (2025), let $B$ be a non-empty set of **bearers**: the items that play implicational roles.

An **implication frame** is a pair $\langle B, I \rangle$ with $I \subseteq \wp(B) \times \wp(B)$, such that $\langle \emptyset, \emptyset \rangle \notin I$ and $\langle B, B \rangle \in I$. An element $\langle \Gamma, \Delta \rangle \in I$ is a good implication from premise set $\Gamma$ to conclusion set $\Delta$.

A frame satisfies **Containment** when any premise set and conclusion set that share a bearer form a good implication:

$$
\Gamma \cap \Delta \neq \emptyset \;\Rightarrow\; \langle \Gamma, \Delta \rangle \in I .
$$

The **range of subjunctive robustness** of an implication is the set of side-premise and side-conclusion additions under which it stays good:

$$
\mathrm{RSR}(\langle \Gamma, \Delta \rangle) = \{\, \langle X, Y \rangle : \langle \Gamma \cup X,\; \Delta \cup Y \rangle \in I \,\} .
$$

Querying a model follows the method of Allen et al. (2025, NeSy proceedings): a verification prompt, repeated sampling, and a majority vote.

## 2. Construction

The construction has three steps. First, fix how bearers, premise sets and conclusion sets are put into words. Second, ask the model for a verdict on each candidate implication. Third, read those verdicts as frame membership.

**Definition 1 (Expression of bearers and contexts).** Let $M$ be a language model. An **expression function** $\delta : B \to L$ assigns each bearer $\varphi$ a natural-language statement expressing it. **Context-construction functions** $\mathrm{ctx}_\Gamma : \wp(B) \to L$ and $\mathrm{ctx}_\Delta : \wp(B) \to L$ package a premise set as a conjunction of its bearers, and a conclusion set $\{\psi\}$ as an expression of $\psi$. All three functions are supplied by the analyst. The simplest choices are

$$
\mathrm{ctx}_\Gamma(\{\varphi_1, \ldots, \varphi_n\}) = \delta(\varphi_1) \frown \text{“ and ”} \frown \cdots \frown \text{“ and ”} \frown \delta(\varphi_n),
\qquad
\mathrm{ctx}_\Delta(\{\psi\}) = \delta(\psi),
$$

where $\frown$ is concatenation.

*In code:* `Bearer.expression` (δ); the benchmark's `context_builders` (template builders with a `joiner`, or plugin builders); `infereval.context.resolve_context_builders`.

!!! note "Implementation"
    The default premise builder joins with `" and "`. The default conclusion builder joins with `" or "`, which reduces to $\delta(\psi)$ for a single conclusion. `$…$` TeX in expressions is stripped at prompt time unless `--no-strip-tex` is given. Each bearer may also carry `paraphrases`, alternative values of δ, selected with `--paraphrase-variant k`; this is the paraphrase axis in [Concepts](concepts.md).

**Definition 2 (Endorsement).** The **endorsement verdict** of $M$ on a candidate implication is a value

$$
E_M(\langle \Gamma, \{\psi\} \rangle) \in \{\mathit{good}, \mathit{bad}, \mathit{abstain}\},
$$

computed by majority vote over repeated samples of $M$'s responses to a verification prompt presenting $\mathrm{ctx}_\Gamma(\Gamma)$ and $\mathrm{ctx}_\Delta(\{\psi\})$. Unparseable responses are mapped to *abstain*.

*In code:* `infereval.endorsement.endorse`, `majority_vote`; `EndorsementConfig` (`n_samples`, `tie_break`); `infereval.prompts.parse_verdict`; the verification prompt is a `VerificationPrompt` (default `default-v1`, or a benchmark override).

!!! note "Implementation"
    - **Samples:** `n_samples` defaults to 5.
    - **Vote:** the verdict with the most samples wins, with *abstain* counted as a category. A tie involving *abstain* gives *abstain*. A pure *good*/*bad* tie is settled by `tie_break`: `abstain` (default), `good`, `bad` or `first`.
    - **Parsing:** a response's verdict is its *committed* answer: the last `Verdict:`-marked token or a token alone on the final line, else the first GOOD/BAD/ABSTAIN token.
    - **Failures:** a sample whose provider call failed (`parse_status = "sample_failed"`) is left out of the vote. If every sample failed, the verdict is *abstain*. A response cut off by the token limit is recorded as `budget_clipped` and parses as *abstain*.
    - **Question form:** under `question_form="support"` (the default) the prompt asks whether the conclusion follows. Under `question_form="coherence"` it asks whether the position committing to Γ and denying Δ can be held without conflict. *Incoherent* is read as *good*, *coherent* as *bad*, *unclear* as *abstain*. This is the bilateral reading of $\langle \Gamma, \Delta \rangle \in I$, and it is defined for every arity of Δ.

**Definition 3 (Derived implication frame).** Given $M$, δ, $\mathrm{ctx}_\Gamma$, $\mathrm{ctx}_\Delta$ and $E_M$, the **derived implication frame** for $M$ is $\langle B, I_M \rangle$, where $\langle \Gamma, \{\psi\} \rangle \in I_M$ iff

1. $\psi \in \Gamma$, or
2. $E_M(\langle \Gamma, \{\psi\} \rangle) = \mathit{good}$.

By stipulation, $\langle \emptyset, \emptyset \rangle \notin I_M$.

*In code:* `infereval.frame.DerivedFrame.contains`; `Implication.intersects` (clause 1), `Implication.is_empty_empty`.

!!! note "Implementation"
    Clause 1 is implemented as $\Gamma \cap \Delta \neq \emptyset$, which is $\psi \in \Gamma$ when $\Delta = \{\psi\}$ and generalizes it to any conclusion set. An implication with no recorded endorsement fails clause 2 (there is no evidence of endorsement), so it is in $I_M$ only by clause 1. The frame is lazy: membership is decided per query.

**Remark 1 (Containment by construction).** By clause 1 of Definition 3, $\langle B, I_M \rangle$ satisfies Containment. *In code:* `DerivedFrame.satisfies_containment`.

**Example (Stop signs).** Let $B = \{sa, ra, n, nr, ba\}$ with δ(sa) = "a is a stop sign", δ(ra) = "a is red", δ(n) = "it is nighttime", δ(nr) = "a is not made with reflective material" and δ(ba) = "a has been painted blue". Simonelli's dialogue with GPT-4.1 gives:

| $i$ | $\Gamma_i$ | $E_M(\langle \Gamma_i, \{ra\} \rangle)$ | analyst verdict |
|---|---|---|---|
| 0 | {sa} | good | good |
| 1 | {sa, n} | good | good |
| 2 | {sa, nr, n} | good | good |
| 3 | {sa, ba} | bad | bad |

Row 3 is the defeated case: {sa, ba} ∩ {ra} = ∅, so clause 1 fails, and the model says *bad*, so clause 2 fails. By Definition 3 and the definition of RSR:

$$
\langle \{n\}, \emptyset \rangle \in \mathrm{RSR}(\langle \{sa\}, \{ra\} \rangle), \quad
\langle \{nr, n\}, \emptyset \rangle \in \mathrm{RSR}(\langle \{sa\}, \{ra\} \rangle), \quad
\langle \{ba\}, \emptyset \rangle \notin \mathrm{RSR}(\langle \{sa\}, \{ra\} \rangle).
$$

The benchmark is bundled as [`examples/stop_sign/benchmark.json`](https://github.com/bradleypallen/infereval/blob/main/examples/stop_sign/benchmark.json).

## 3. Evaluation methodology

The construction also gives a procedure for gathering evidence bearing on $M$'s inferential mastery, modeled on binary classification with abstention, against a labeled benchmark.

**Definition 4 (Benchmark).** Given bearers $B$ and analysts $a_1, \ldots, a_m$, a **benchmark** is a finite set

$$
\beta = \{(I_1, V_1), \ldots, (I_n, V_n)\},
$$

where each $I_i = \langle \Gamma_i, \{\psi_i\} \rangle$ is an implication and each $V_i = (v_{i,1}, \ldots, v_{i,m})$ records analyst $a_j$'s verdict $v_{i,j} \in \{\mathit{good}, \mathit{bad}, \mathit{abstain}\}$ on $I_i$.

*In code:* `infereval.benchmark.Benchmark`; items are `BenchmarkItem` (`premises`, `conclusions`, `analyst_verdicts`), analysts are `analysts`.

!!! note "Implementation"
    `conclusions` may have any number of bearers, including none, which is used for exclusivity items. Benchmarks can also declare analyst `panels`, per-item `rsr_target`, `tags`, roles, `references` and `analyst_rationales`. See [Authoring benchmarks](authoring_benchmarks.md) and [JSON schemas](schemas.md).

**Definition 5 (Evaluation).** An **evaluation** of $M$ over β is

$$
\eta = \{(I_1, V_1, E_M(I_1)), \ldots, (I_n, V_n, E_M(I_n))\}.
$$

*In code:* `infereval.evaluation.Evaluation`, produced by `evaluate()`. Each item also records its samples and vote counts. The evaluation records `benchmark_hash`, so it can be checked against the benchmark it was run on.

Agreement is characterized along three axes: **coverage** (how often $M$ gives a substantive verdict), **Cohen's κ** (agreement with a reference position) and **Fleiss' κ** (coherence with the community of analysts). Both κs are restricted to items where every annotator involved is substantive. This separates *whether* $M$ takes a position from *how well* it does when it does.

**Definition 6 (Coverage).**

$$
\mathrm{cov}(\eta) = \frac{\lvert \{ i : E_M(I_i) \neq \mathit{abstain} \} \rvert}{n},
\qquad
\mathrm{cov}_j(\eta) = \frac{\lvert \{ i : v_{i,j} \neq \mathit{abstain} \} \rvert}{n}.
$$

*In code:* `metrics.coverage`, `metrics.coverage_per_analyst`.

**Definition 7 (Substantive index).** For a reference verdict function $r : \{1, \ldots, n\} \to \{\mathit{good}, \mathit{bad}, \mathit{abstain}\}$,

$$
S(\eta, r) = \{\, i : E_M(I_i) \in \{\mathit{good}, \mathit{bad}\} \;\wedge\; r(i) \in \{\mathit{good}, \mathit{bad}\} \,\}.
$$

*In code:* `metrics.substantive_index`.

**Definition 8 (Analyst consensus).**

$$
c_i =
\begin{cases}
\mathit{good} & \text{if } \lvert\{ j : v_{i,j} = \mathit{good} \}\rvert > \lvert\{ j : v_{i,j} = \mathit{bad} \}\rvert, \\
\mathit{bad} & \text{if } \lvert\{ j : v_{i,j} = \mathit{bad} \}\rvert > \lvert\{ j : v_{i,j} = \mathit{good} \}\rvert, \\
\mathit{abstain} & \text{otherwise.}
\end{cases}
$$

Abstaining analysts count toward neither side.

*In code:* `metrics.consensus_verdict`; `consensus_reference` (r = c) and `analyst_reference` (r = one analyst's column).

**Definition 9 (Cohen's κ).** Let $S = S(\eta, r)$ and $n_S = \lvert S \rvert$. Then

$$
p_o = \frac{\lvert\{ i \in S : E_M(I_i) = r(i) \}\rvert}{n_S},
\qquad
p_e = \sum_{c \in \{\mathit{good}, \mathit{bad}\}} p_M(c)\, p_r(c),
$$

$$
p_M(c) = \frac{\lvert\{ i \in S : E_M(I_i) = c \}\rvert}{n_S},
\qquad
p_r(c) = \frac{\lvert\{ i \in S : r(i) = c \}\rvert}{n_S},
\qquad
\kappa_C(\eta, r) = \frac{p_o - p_e}{1 - p_e}.
$$

*In code:* `metrics.cohens_kappa(eta, reference)`. It returns `None`, with a logged warning, when $S$ is empty or $p_e = 1$.

!!! note "Implementation"
    An optional per-item `weights` function computes a weighted variant; for example, `margin_weight` weights items by the vote margin. With no weights, the result is exactly the formula above.

**Definition 10 (Fleiss' κ).** Treat $M$ as the $(m+1)$-th annotator ("analyst" is reserved for the human labelers). Let

$$
S_F = \{\, i : E_M(I_i) \in \{\mathit{good}, \mathit{bad}\} \;\wedge\; v_{i,j} \in \{\mathit{good}, \mathit{bad}\} \text{ for all } j \,\},
\qquad n_F = \lvert S_F \rvert .
$$

For $i \in S_F$ and $c \in \{\mathit{good}, \mathit{bad}\}$, let $n_{i,c} = \lvert\{ j : v_{i,j} = c \}\rvert + \mathbb{1}[E_M(I_i) = c]$. Then

$$
P_i = \frac{1}{(m+1)\,m} \sum_{c} n_{i,c}\,(n_{i,c} - 1),
\qquad
\bar{P} = \frac{1}{n_F} \sum_{i \in S_F} P_i,
$$

$$
p_c = \frac{\sum_{i \in S_F} n_{i,c}}{n_F\,(m+1)},
\qquad
\bar{P}_e = \sum_{c} p_c^{2},
\qquad
\kappa_F(\eta) = \frac{\bar{P} - \bar{P}_e}{1 - \bar{P}_e}.
$$

The **inter-analyst Fleiss' κ**, $\kappa_F^{*}(\beta)$, is computed the same way over the analyst verdicts alone, with $m$ annotators and $n_{i,c} = \lvert\{ j : v_{i,j} = c \}\rvert$.

*In code:* `metrics.fleiss_kappa(eta)`, `metrics.inter_analyst_fleiss(source)`. Both return `None`, with a logged warning, when there are fewer than two annotators, $S_F$ is empty, or $\bar{P}_e = 1$.

!!! note "Implementation"
    $\kappa_F^{*}$ uses every analyst column the benchmark records, across all panels. `analyst_indices` restricts it to a subset, and `inter_analyst_fleiss_per_panel` gives the per-panel decomposition. Fleiss' κ also accepts per-item weights, as Cohen's does.

**Remark 2 (Reading κ against the inter-analyst baseline).** $\kappa_F^{*}(\beta)$ is the baseline for reading $\kappa_C(\eta, r)$ and $\kappa_F(\eta)$. If $M$'s agreement with the analysts approaches the analysts' agreement with one another, $M$ is participating in the practice at a level comparable to competent practitioners. If adding $M$ to $\kappa_F$ substantially lowers agreement relative to $\kappa_F^{*}$, $M$ diverges from competent practice.

The baseline is **undefined**, and the comparison unavailable, when there are fewer than two analysts, when no item has all analysts substantive, or when every analyst rating over $S_F$ falls in one class ($\bar{P}_e = 1$). Analysts who agree on every item but whose items include both *good* and *bad* give $\kappa_F^{*} = 1$: perfect, well-defined agreement, and the ceiling against which $M$ is read.

**Remark 3 (RSR-targeted benchmarks).** A benchmark is **RSR-targeted** for a target inference $\langle X, \{\psi\} \rangle$ when its items have the form $I_i = \langle X \cup Y_i, \{\psi\} \rangle$ for various side-premise extensions $Y_i$. The analyst verdicts then record whether each $Y_i$ preserves the inference, that is, whether $\langle Y_i, \emptyset \rangle \in \mathrm{RSR}(\langle X, \{\psi\} \rangle)$. The agreement measures over such a benchmark bear on $M$'s mastery of that RSR: $M$ agrees with the analysts' RSR-membership verdicts to the extent that $\kappa_C(\eta, r)$ approaches $\kappa_F^{*}(\beta)$. The stop-sign example is a small RSR-targeted benchmark.

*In code:* `BenchmarkItem.rsr_target` (`X`, `A`); `MetricsReport.by_rsr_target`; `structure.rsr_role_consistency_check`.

**Decompositions.** Coverage and both κs can be reported for any subset of items: by target inference, by kind of variation (defeater, irrelevant addition, weakening), or by any other feature of the benchmark. Decompositions show patterns that aggregate figures hide.

*In code:* `MetricsReport.by_tag`, `MetricsReport.by_rsr_target`; `infereval metrics --by-tag / --by-rsr-target`. See [Interpreting metrics](interpreting_metrics.md).

## References

Hlobil, U., & Brandom, R. B. (2025). *Reasons for Logic, Logic for Reasons*. Routledge.
