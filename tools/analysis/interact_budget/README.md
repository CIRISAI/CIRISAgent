# interact_budget — what our timeout and retry settings actually buy

Toys for reasoning about the interact budget on **measured** provider latency,
built for CIRISAgent#1186 (retry/timeout budgets, local vs remote profiles).

Nothing here changes the agent. It answers questions like *"what deadline gives
99% of users a reply?"* and *"does retrying help or hurt on a Jetson?"* before
anyone changes a default.

## Files

| file | what it is |
|---|---|
| `extract_latency.py` | builds a dataset from agent logs (five-platform `live-qa-*` artifacts) |
| `latency.2026-09-23.json` | snapshot: 7 gate runs, 61 unique logs, 633 LLM calls, `qwen/qwen3.6-35b-a3b` via OpenRouter |
| `pipeline.py` | Monte-Carlo of one H3ERE interact against an **elastic** (cloud) provider |
| `local_provider.py` | the conscience stage against a **capacity-bound** box with N slots |
| `explore.py` | CLI over both |

```bash
python -m tools.analysis.interact_budget.explore calibrate     # model vs observed
python -m tools.analysis.interact_budget.explore ceiling       # the part no deadline buys back
python -m tools.analysis.interact_budget.explore scenarios     # configs vs a target (default 99%)
python -m tools.analysis.interact_budget.explore experience    # what users actually receive
python -m tools.analysis.interact_budget.explore tails         # sensitivity to the unmeasured tail
python -m tools.analysis.interact_budget.explore local --speed 3
python -m tools.analysis.interact_budget.explore local-sweep
```

## The pipeline being modelled (from the code)

```
stage 1  EthicalPDMA | CSDMA | BaseDSDMA   concurrent   -> slowest member
stage 2  IDMA                              sequential
stage 3  ActionSelectionPDMA               sequential
stage 4  four conscience shards            concurrent   -> needs ALL FOUR
+        per-interact overhead             measured (median 6.6s)
```

A shard that exhausts its attempts fails **closed** (`check_ran=False`) → the
thought becomes PONDER → the user gets no reply however long anyone waits. So
every config has a **ceiling**: its success rate with an infinite deadline.

## Assumptions — read before trusting a number

1. **The tail past the conscience budget is not measured.** A call that exceeds
   45s logs a timeout, not a duration, so the data is right-censored. The mass
   past 45s *is* measured (10.7% of conscience calls); its *shape* is not.
   `--tail` varies it. Near 99% the answer is driven by the measured mass and
   barely moves (189–193s across three tail shapes); near 99.9% it lives entirely
   in the unmeasured region — don't trust a 99.9% number from this.
2. **Retries are independent draws — for an elastic provider.** Measured:
   P(retry also times out | first did) = 3/18 = 17% vs a 10.7% base rate —
   indistinguishable at this n. This is **false** on a capacity-bound box; that is
   what `local_provider.py` is for.
3. **Stage members are sampled independently.** Real concurrent calls in one
   thought are probably positively correlated, so the model's max-of-N runs a
   little slow: calibration p50 is ~11s high, p90 within ~4s. Its deadlines are
   therefore slightly generous, not optimistic.
4. **`--speed` for a local box is a guess.** Measure the real box with
   `extract_latency.py` and pass the result as `--latency` instead.

## Calibration (snapshot)

```
observed  n=42     p50 71.7s  p90 123.8s   within 110s: 71%
model     n=20000  p50 83.0s  p90 127.6s   within 110s: 72%
```

## Findings on the snapshot (2026-09-23)

**Remote (elastic).** Per-call conscience timeout rate 10.7%; the stage needs all
four shards, so the ceiling is set by attempt count, not by the deadline:

| attempts | ceiling |
|---|---|
| 1 | 63.7% |
| 2 (today) | 95.5% |
| 3 | 99.5% |
| 4 | 99.95% |

| config | within 110s | ceiling | deadline for 99% |
|---|---|---|---|
| today 45s × 2 | 72% | 94% | **unreachable** |
| 45s × 4 | 72% | 99.8% | **~193s** |
| fail-fast 30s × 4 | 64% | 95% | unreachable |

Fail-fast is *worse* here: p50 is ~5s but p90 ~35s, so there is real work in the
20–45s band, and shortening the per-try converts slow successes into timeouts
faster than extra attempts recover them.

What users receive at 45s × 4: 110s deadline → 72% get a reply (p50 74s);
~195s deadline → 99% get a reply (p50 85s). The deadline is a cap on patience,
not a cost anyone pays until the tail.

**Local (capacity-bound, 1 slot, cancel does not free the slot).** One long try
dominates two short ones on every axis:

| per-try × attempts | ok | p90 | slot-seconds wasted on abandoned calls |
|---|---|---|---|
| 45s × 2 (today) | 94.3% | 207s | 56s |
| 240s × 1 | 98.9% | 154s | 4s |

Because a retry on such a box queues *behind* the generation it abandoned.

## Rebuilding the dataset

```bash
for r in <run ids>; do for a in live-qa-windows live-qa-linux-android live-qa-macos-ios; do
  gh run download $r -n $a -D runs/$r/$a; done; done
python -m tools.analysis.interact_budget.extract_latency runs/ --runs <ids> \
  -o tools/analysis/interact_budget/latency.$(date +%F).json
```
