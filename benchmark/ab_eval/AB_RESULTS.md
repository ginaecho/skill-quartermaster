# A/B eval — skill selection: full set vs. compiled loadout

_Backend_: **LIVE Anthropic: claude-opus-4-8**  
_Tasks_: 60 (seed 7).  Full menu: 840 skills.  Loadout cap: 30.

Each task is a user request whose correct skill is known (gold). The model picks one skill from the menu; we score gold-hit accuracy.

| Condition | menu size | gold-hit accuracy |
|---|--:|--:|
| **A — full installed set** | 840 | **93%** |
| **B — Quartermaster loadout** | ≤30 | **97%** |
| Δ (loadout − full) | | **+3 pts** |

Decomposition of the loadout condition:

- Recall — gold skill present in the loadout: **100%** (if it's hidden, it can't be picked)
- Selection accuracy given the gold skill is present: **97%**

**Result: trimming to the loadout did not hurt selection (97% vs 93%)** — the agent finds the right skill at least as often with ~30 skills as with 840, at a fraction of the context cost.


_Reproduce_: `python3 benchmark/ab_eval/run_ab_eval.py <corpus> <source>` (set ANTHROPIC_API_KEY for the live run).
