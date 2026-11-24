# Downstream display monitor

Pages, Mathesis and the public paper catalog call the SHA-pinned reusable
`display-monitor.yml` workflow. Their `.github/display-monitor.json` files own
public probes, repair targets, permitted paths and verification commands.

An hourly or post-deployment run loads real public pages in an isolated browser
and checks bounded JSON contracts. Healthy runs use no model. A manual
`verify_model` run also exercises the existing Omega Live Ops model route, then
repairs a disposable broken reader through the actual verification and fresh
review stages. That acceptance fixture never publishes a PR.

Before every model call, trusted commands prove both read-only and workspace-write
execution, including rejected writes outside the workspace and rejected outbound
network access. The repair job installs Ubuntu's distribution `bubblewrap` and
loads its `bwrap-userns-restrict` AppArmor profile following the
[Codex Ubuntu setup instructions](https://learn.chatgpt.com/docs/sandboxing).
This applies only to that disposable monitor runner. The filesystem and network
checks fail closed; a returned model message alone does not establish execution
readiness.

For an anomaly, an ephemeral Codex proposes one small patch in the responsible
registered repository. It receives only the caller's model key. Registered
commands and a fresh read-only Codex review must pass. A separate trusted job
validates the inventory, base SHA and producing run/attempt before submitting a
PR. Neither code execution nor candidate verification receives a GitHub write
credential. The reusable code is held outside the model's writable workspace.

Own-repository repair PRs use the repository token or a configured repository-bound
NyxID GitHub route. A later run can merge those monitor-created PRs only after
their producing run and actual GitHub PR checks pass.
Existing approval or branch requirements remain effective. Upstream patches are
PRs for their owners to merge; the monitor never merges them.

Cross-repository submission uses `NYXID_MONITOR_GITHUB_KEY` with explicit
`github_service` registrations. Each service's upstream URL is fixed to one
GitHub repository. The key allows only those services and the required Git/PR
operations; upstream merge operations are excluded. Per-agent bindings reuse
the already encrypted GitHub credential without reading or exporting it. These
publication keys are independently revocable and never reach model execution.
The credential's existing GitHub account remains the published PR author; the
registered `publisher_login` and original run bind local automatic reconciliation.
Model keys are owned by Omega Live Ops; these GitHub bindings remain with the
owner of the existing GitHub connection rather than copying that credential.

Alternatively, submission can use `DISPLAY_MONITOR_PR_TOKEN`, a GitHub App
installation token or fine-grained credential limited to the explicitly
registered repositories with contents/PR write permissions. It is available
only in the submission job. The caller's built-in token cannot grant rights in
another repository. Without this credential, an upstream candidate remains a
two-day run artifact and the submission reports the missing authorization.
The monitor never substitutes an organization administrator session or exports a
broad personal token. The model secret is `NYXID_MONITOR_KEY`, issued independently
per caller under Omega Live Ops, proxy-only for its existing Chrono LLM service.

Research manuscripts, review and trust decisions, mail, DOI deposits, private
records and core trureturing/requests writes are outside scope. Consumer display
bugs are fixed locally. Outreach or another explicitly registered display
dependency receives a PR when its public integration code owns the fault.
Unsupported scientific/source changes retain their actual missing prerequisite
rather than fabricating a code fix or starting another research task.

The only durable incident/repair records are the normal PR and its GitHub run.
Run artifacts expire after two days. A stable probe-set fingerprint deduplicates
the same incident. Published bytes, actual workflow completion and served-page
observations remain different evidence; a model PASS is not a deployment receipt.

Run `python3 -m unittest discover -s monitor/tests -v` and
`node --check monitor/browser.cjs` for this component's checks. External commands
and GitHub mutations are mocked in the unit tests; production probes and hosted
workflow runs separately establish actual transport/browser behavior.
