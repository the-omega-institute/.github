# The Omega Institute

**trureturing: a scientific method for AI to discover truth and find its next question.**

We build a Lean 4 library in which questions, computation, checked proofs and open
boundaries accumulate as reusable knowledge. Each proved result states its exact
assumptions; each refutation carries a machine-checked witness; each open question is
marked as open.

**[→ trureturing](https://github.com/the-omega-institute/trureturing)** ·
[Read the book](https://the-omega-institute.github.io/trureturing-mdbook/) ·
[Explore the atlas](https://the-omega-institute.github.io/trureturing-pages/atlas.html) ·
[Vision](https://github.com/the-omega-institute/trureturing/blob/dev/docs/VISION.md) ·
[Watch the films](https://github.com/the-omega-institute/trureturing-film)

## By the numbers

*Measured on `trureturing@dev`, 2026-09-27.*

| | |
|---|---|
| **4,981** | Lean modules in the frozen ledger |
| **30,000+** | theorem declarations in the Lean source |
| **411** | problems from the literature (OEIS, Erdős problems, recent papers), each with sources |
| **71** | conjectures and claims from the literature refuted in Lean |

## Publications

- B. Cloitre, H. Ma, W. Zhang.
  **A Padovan-automatic description of a nested recurrence.** Zenodo, 2026.
  [doi:10.5281/zenodo.22979217](https://doi.org/10.5281/zenodo.22979217) ·
  [manuscript, certificates and Lean proofs](https://github.com/the-omega-institute/a076502-padovan)
- H. Ma, W. Zhang, M. I. Cázares.
  **A Certificate-Producing Cascade for Equational Implication: The SAIR EQT2 Stage 2 Solver.**
  [arXiv:2609.00706](https://arxiv.org/abs/2609.00706), 2026 ·
  [solver](https://github.com/the-omega-institute/sair-eqt2-stage2-solver)
- M. I. Cázares, W. Zhang, H. Ma.
  **Mechanism-level routing failure in LLMs over Lean-verified algebraic structures.**
  [arXiv:2607.04534](https://arxiv.org/abs/2607.04534), 2026

## Selected results

- **A Padovan-automatic nested recurrence.** OEIS A076502 has exact floor-offset set
  `{-1, 0, 1, 2}`, a uniform discrepancy bound and least balance constant 4, with an
  explicit 26-letter morphic presentation.
  [Problem](https://the-omega-institute.github.io/trureturing-mdbook/Problems/oeis-a076502-nested-recurrence-floor-refutation.html)
- **Sahbi Conjecture 6.4, proved.** The sub-quorum chromatic number of the Boolean cube
  `Q_n` equals `2^(n-1)` for every `n ≥ 2`.
  [Problem and proof](https://the-omega-institute.github.io/trureturing-mdbook/Problems/sahbi-hypercube-subquorum.html)
- **Greathouse's formula for OEIS A175406, refuted.** At `n = 1121626023352383` the
  conjectured `floor((n + 1/2) log 2)` exceeds the true value by one; the Lean proof uses
  certified logarithm bounds.
  [Problem](https://the-omega-institute.github.io/trureturing-mdbook/Problems/oeis-a175406-log-two-floor-refutation.html)
- **A blind spot of local observation.** A Bell state and the classical mixture of `00`
  and `11` have identical single-qubit marginals; the correlation sector omitted by local
  descriptions has real dimension `(m² − 1)(n² − 1)`.
  [Lean](https://github.com/the-omega-institute/trureturing/blob/dev/D5/S3/Quantum/Entanglement/LocalMarginalCorrelationBlindSpot.lean)
- **Golden-ratio coordinates of Zeckendorf digits.** The deficit
  `β(a) + β(b) − β(a + b)` takes values only in `{−1, 0, 1}` for all natural inputs.
  [Lean](https://github.com/the-omega-institute/trureturing/blob/dev/D5/S1/Deficit/DeficitThreeValued.lean)

## Take part

Bring a question that matters to you. In Claude Code or Codex, paste:

```text
Help me explore https://github.com/the-omega-institute/trureturing: use an existing checkout or clone it into a new directory if needed, read AGENTS.md and README.md, then read the relevant SKILL.md under skills/ to investigate a question I care about and find a checked result or a clearly stated open question.
```

The [contribution guide](https://github.com/the-omega-institute/trureturing/blob/dev/docs/CONTRIBUTING.md)
covers forks, checks and pull requests. Contributions in English and Chinese are welcome.

## Part of [Chrono AI](https://www.chrono-ai.fun/)
