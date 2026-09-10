# prior_work - the first iteration, preserved as evidence

`VALIDATION.md` section 3 makes specific claims about the first attempt at this
work: that its tests could not fail, that a wind condition leaked into a
zero-wind baseline, that a "30 second" hover was a loop counter. Those claims
are the strongest argument in the case study for why the rest of it was
restructured.

A document that says "check my work" and then cites files the reader cannot
open is not saying much. So the cited artifacts are here.

Nothing in this directory has been edited. These are the files as they were.

## What is here, and what it evidences

| File | Cited for |
|---|---|
| `results/wind_test_complete_20260908_204146.txt` | The `distance / speed` fake timebase; identical adjusted range across all three wind scenarios; drift identical to two decimal places; the inverted crosswind factor |
| `results/hover_test_20260908_003202.txt` | `Target 46.00 min / Actual 0.50 min / FAIL` - comparing how long the test ran against how long the aircraft flies |
| `HoverScript_01.py` | Line 88, `# time.sleep(1)`, commented out - which is why "30 seconds" was a loop counter and the run took 0.76 s of wall time |
| `battery_model_v1.py` | The defect list: retroactive energy rewriting in `tick()`, drag energy collapsing to zero, the `1 + (v/50)^2` wind curve with no physical basis, the inverted direction factor, `CdA = 0.04 m2`, no induced-power term at all. Renamed from `battery_model.py` only to avoid colliding with the current model on the import path. |

Two claims worth checking directly, because they are the easiest to verify and
the hardest to argue with:

```bash
sed -n '88p' prior_work/HoverScript_01.py        # the commented-out sleep
sed -n '50p' prior_work/battery_model_v1.py      # the emoji
```

## On the emoji, and the ASCII policy

The rest of this repository is ASCII-only, and a byte scan across it comes back
clean. **This directory is deliberately exempt**, and `battery_model_v1.py`
contains three non-ASCII bytes at line 50: a check-mark emoji, in a file whose
own constraint list forbade them.

Stripping it to satisfy the policy would destroy the evidence for a claim made
about it. The violation is the finding.

## What this directory is not

It is not a criticism of the person who wrote it, who is the same person who
wrote the replacement. Every defect here is what happens when a test harness is
built before the simulator's actual capabilities have been established - which
is exactly why `probe_sim_capabilities.py` now runs before anything else, and
why `PREDICTIONS.md` exists at all.

The useful comparison is not "bad code, good code". It is that the first
version produced confident output with no way to tell whether any of it was
true, and the second produces a board with two entities it refuses to model and
a held-out anchor that misses by +14.2%.
