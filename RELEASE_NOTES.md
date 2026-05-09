# Release Notes

## Unreleased

### Added

- Added `quantlab.agentic`, a reusable agentic review layer for QuantLab selection pipelines.
  - Defines serializable review schemas: `ReviewContext`, `CandidateStock`, `ReviewFinding`, and `ReviewDecision`.
  - Adds deterministic reviewers for liquidity, sector-flow exposure, and industry concentration.
  - Adds `AgenticReviewEngine` to aggregate reviewer findings into structured `approve`, `reduce`, `veto`, or `review` decisions.
  - Adds `review_cli.py` for running daily reviews from pipeline meta files without embedding agent logic in experiment scripts.
- Added sector fund-flow data utilities under `quantlab.data`.
  - `sector_flow_download.py` supports AKShare and Tushare DC providers.
  - `sector_flow_features.py` builds rolling sector-flow ranks, z-scores, persistence, and hot/cold sector labels.
  - `sector_flow_utils.py` centralizes calendar alignment, standard columns, and table I/O.
- Added `docs/project_architecture.html`, a static architecture overview for the full QuantLab pipeline.
- Linked the architecture overview from `README.md` and `README_CN.md` so the GitHub project entry points expose the new design directly.

### Changed

- Ignored external TradingAgents reference artifacts via `.gitignore`; QuantLab now keeps only the derived `quantlab.agentic` module rather than vendoring the upstream project.
- Updated README module descriptions to include the independent agentic review layer and sector fund-flow data layer.

