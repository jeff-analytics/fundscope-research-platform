# FundScope V9.2.2

## Scope

V9.2.2 is a usability, rendering and cold-query resilience release based on V9.2.1.

## Fixes

- Fixed same-route navigation from Similarity Breakdown to Fund Research.
- Rebuilt the Research Explorer object switcher to prevent vertical label wrapping and cramped controls.
- Removed the fixed 12-quarter asset-allocation window. The chart now follows all locally collected quarters and adds data zoom only when needed.
- Increased chart grid/title margins and centered y-axis names across research scatter plots.
- Split Institutional Consensus core results from historical coverage loading.
- Added progressive local consensus loading: a market snapshot is returned quickly while the exact comparable Fund Master cohort is computed once in the background.
- Added automatic polling from the snapshot to the exact cohort result and a working retry action.
- Cache keys include the active database path to avoid cross-database cache contamination in tests or alternate data directories.
