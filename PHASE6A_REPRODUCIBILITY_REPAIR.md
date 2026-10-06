# Phase 6A Reproducibility Repair

This restores a small replayable validation gate without changing the frozen
Phase 5 trading logic.

Checks:
1. Required BTC datasets and core MTF/backtest modules exist.
2. `compileall` passes.
3. Existing Phase 5B long-history smoke test completes successfully.
4. Dataset SHA-256 fingerprints and run status are recorded in JSON.
5. GitHub Actions fails closed unless the report says `PASS`.

Research/backtest only. No live execution.

This gate does **not** resolve the prior Phase 5M candidate-count mismatch
and does **not** promote NEAR_EDGE to production.
