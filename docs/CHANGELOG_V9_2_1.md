# FundScope V9.2.1

## Performance & Navigation

V9.2.1 is a performance-focused maintenance release built on V9.2.0. It does not add a new research module.

### Research Explorer cold-start optimization

- Rewrote the local Fund Explorer cross-section from per-fund pandas loops to batch/vectorized calculations.
- Concentration, turnover, retention, entry/exit, style exposure, sector concentration and drift are computed cross-sectionally.
- Added backend single-flight protection so concurrent requests do not rebuild the same expensive snapshot twice.
- Increased local Explorer, Security Explorer and Manager Explorer cache lifetime for normal research navigation.

Synthetic regression benchmark used 1,500 Fund Masters, 2 report periods and about 75,000 holding rows:

- V9.2.0-style cold Fund Explorer path: about 22.5 seconds
- V9.2.1 cold Fund Explorer path: about 2.2 seconds
- Warm cache: effectively immediate in the same process

Actual performance depends on SSD speed, database size, Security Master coverage and concurrent collection tasks.

### Manager research optimization

- Manager catalog, manager detail and manager style timeline now use longer server-side caches.
- Holdings cache lifetime increased for repeated manager/fund research.
- Manager research limits the interactive timeline read window to the most recent 24 report periods, avoiding full-history scans on every click.
- The page keeps the current result visible while a new manager is loading instead of clearing the whole research canvas.

### Frontend navigation

- Research GET results use longer in-memory stale-while-revalidate caching.
- Explorer no longer clears existing data when changing period or research object.
- A lightweight update indicator replaces the previous full blank/skeleton state when current results already exist.
- The app prewarms Fund Explorer, Manager Catalog/default Manager Research and Smart Money shortly after startup.

### Startup contention

- Normal app startup no longer runs the full Data Center health scan.
- Added `/api/data/presence`, which uses `EXISTS` checks only to decide whether Local Research is available.
- Full COUNT/DISTINCT data-health checks remain in Data Center when explicitly requested.

### Windows runtime

- Windows launcher now checks the Node major version before `npm install`.
- Unsupported Node versions receive a direct Node.js 22 LTS message instead of waiting for npm to fail with `EBADENGINE`.
