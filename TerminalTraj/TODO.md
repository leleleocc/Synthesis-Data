# TODO

- [ ] Allow pinned test-only dependencies to install inside `tests/test.sh`; keep task/runtime dependencies in the base environment or candidate overlay.
- [ ] Replace separate task/verifier/package approvals with one staged finalization step over a temporary package tree, using progressive prompt disclosure plus filesystem gates.
- [ ] Let final review select and edit candidates, then reassemble packages and rerun the final contract and verifier checks before publishing.
- [ ] Add candidate feasibility smoke tests after overlay build, including service startup, resource limits, positive/negative verifier probes, and final package hashes.
- [ ] Fix UTF-8 log/session collection and report final packaged-candidate rate separately from the aggregate phase reward.
