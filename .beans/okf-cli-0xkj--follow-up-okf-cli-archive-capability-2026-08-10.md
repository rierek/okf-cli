---
# okf-cli-0xkj
title: Follow-up okf-cli archive capability 2026-08-10
status: todo
type: epic
priority: normal
created_at: 2026-08-10T06:45:07Z
updated_at: 2026-08-10T09:17:36Z
parent: okf-cli-huow
---

Findings raised by the PO during the 2026-08-10 review of milestone okf-cli-huow. Side findings and rejects that no existing leaf covers land here.


## Scope of this epic — operationalized 2026-08-10

Five leaves, all carrying a Gate-A-validated acceptance block. Three sources feed them: the PO review of 2026-08-10 (`5436`), the R-15 real-catalogue run (`mk7m`, `gqss`), and reviewer findings parked during the milestone realization (`h12o`, `yixf`).

`mk7m`, `h12o` and `yixf` were re-parented into this epic during operationalization. They belonged to milestone `okf-cli-huow`, which is now accepted and terminal; open work below an accepted milestone would be invisible to the roadmap.

Two of the five are blockers for a production recommendation of `archive` on the real catalogue: `mk7m` and `gqss`. Both describe residue that the obvious verification cannot see — one lands writes in an unnamed repository, the other leaves directories git does not track. The other three are quality work with no user-visible defect behind them.

No implementation order is fixed. `mk7m` and `gqss` touch the same code path and would sensibly go to one implementer; `h12o` needs a planner decision on a spec-fixed signature before an implementer can start.
