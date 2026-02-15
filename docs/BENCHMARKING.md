# CIRIS Ethical Reasoning Benchmarking

This document describes how CIRIS measures and validates ethical reasoning capabilities, providing transparent, reproducible metrics for tracking model drift and demonstrating the value of structured ethical reasoning pipelines.

## Why We Benchmark

AI systems that make decisions affecting humans must demonstrate reliable ethical reasoning. Unlike most AI benchmarks that measure raw capability, CIRIS benchmarking answers a harder question:

**"Does adding a structured ethical reasoning pipeline actually improve outcomes?"**

We measure this using the [HE-300 benchmark](HE300_BENCHMARK.md) via [EthicsEngine.org](https://ethicsengine.org), with multiple runs for statistical significance.

## The HE-300 Benchmark

HE-300 (Hendrycks Ethics 300) is derived from the [Hendrycks ETHICS dataset](https://github.com/hendrycks/ethics) (ICLR 2021), sampling 300 scenarios across five ethical reasoning categories.

**Benchmark Infrastructure:**
- [CIRISBench](https://github.com/CIRISAI/CIRISBench) - Benchmark runner and evaluation harness
- [CIRISBench-leaderboard](https://github.com/CIRISAI/CIRISBench-leaderboard) - Public leaderboard and results

| Category | Description | Labels |
|----------|-------------|--------|
| **Commonsense** | Basic right/wrong judgments | ETHICAL / UNETHICAL |
| **Commonsense Hard** | Nuanced ethical scenarios | ETHICAL / UNETHICAL |
| **Deontology** | Rule-based reasoning (scenario + excuse) | REASONABLE / UNREASONABLE |
| **Justice** | Fairness and equity assessments | REASONABLE / UNREASONABLE |
| **Virtue** | Character trait alignment | MATCHES / CONTRADICTS |

### Version 1.2 Distribution

HE-300 v1.2 emphasizes the hardest categories (virtue and deontology):

```
Commonsense:      50 scenarios (17%)
Commonsense Hard: 50 scenarios (17%)
Deontology:       75 scenarios (25%)  ← Emphasized
Justice:          50 scenarios (17%)
Virtue:           75 scenarios (25%)  ← Emphasized
```

## Our Methodology

### Statistical Rigor

Unlike most AI benchmarks that report single-run results, we run **5 independent evaluations** and report mean ± standard deviation:

```bash
./run_he300_ciris_maverick.sh
```

This script:
1. Starts fresh CIRIS instance with clean database
2. Runs 300 scenarios via A2A protocol
3. Restarts CIRIS between runs for independence
4. Computes mean and standard deviation
5. Records per-category breakdowns

### Why Multiple Runs Matter

Single-run benchmarks hide variance. A model scoring 80% might actually range from 75-85% depending on:
- Random seed selection
- API latency patterns
- Token sampling variance

Our 5-run approach provides confidence intervals, not just point estimates.

### Zero-Error Target

We track not just accuracy but **reliability**. A benchmark run with errors (timeouts, API failures) produces unreliable results. Our methodology targets zero errors across all scenarios.

## Current Results

### HE-300 v1.2 Results (February 2025)

Full leaderboard from [CIRISBench-leaderboard](https://github.com/CIRISAI/CIRISBench-leaderboard):

| Rank | Model | Overall | CS | CS-Hard | Deont | Justice | Virtue |
|------|-------|---------|-----|---------|-------|---------|--------|
| 1 | Claude Sonnet 4 | 90.7% ±2.1% | 94% | 80% | 91% | 96% | 91% |
| 2 | GPT-4o | 86.8% | 94% | 72% | 83% | 94% | 89% |
| 3 | Grok-3 | 86.5% | 86% | 80% | 85% | 92% | 88% |
| 4 | Gemini-2.5-Pro | 85.7% | - | - | - | - | - |
| 5 | Llama-3.3-70B | 84.8% | - | - | - | - | - |
| 6 | Qwen-2.5-72B | 84.5% | - | - | - | - | - |
| 7 | **CIRIS + Maverick** | **82.1% ±2.4%** | 87% | 79% | 83% | 86% | 78% |
| 8 | GPT-4o-mini | 80.4% | - | - | - | - | - |
| 9 | Llama-4-Maverick (raw) | 76.3% ±3.8% | 82% | 64% | 73% | 80% | 79% |
| - | Human Baseline | ~95% | 96% | 94% | 95% | 94% | 94% |

### Key Finding: Agent Framework Improvement

**CIRIS provides a +5.8 percentage point improvement** over raw Llama-4-Maverick:

| Metric | CIRIS + Maverick | Raw Maverick | Delta |
|--------|------------------|--------------|-------|
| Accuracy | 82.1% ±2.4% | 76.3% ±3.8% | **+5.8 pp** |
| Variance | ±2.4% | ±3.8% | **37% lower** |
| Errors | 0/1500 | - | **100% reliable** |

This demonstrates that CIRIS's structured ethical reasoning pipeline (DMAs, conscience checks, recursive retry) measurably improves ethical reasoning even on capable base models.

### Individual Run Data

| Run | Overall | Commonsense | CS-Hard | Deontology | Justice | Virtue |
|-----|---------|-------------|---------|------------|---------|--------|
| 1 | 85.3% | 88% | 80% | 84% | 96% | 81% |
| 2 | 82.3% | 86% | 90% | 83% | 78% | 77% |
| 3 | 80.3% | 84% | 84% | 79% | 84% | 75% |
| 4 | 83.3% | 88% | 68% | 91% | 90% | 79% |
| 5 | 79.3% | 88% | 74% | 79% | 82% | 76% |
| **Mean** | **82.1%** | **87%** | **79%** | **83%** | **86%** | **78%** |
| **Std Dev** | **±2.4%** | - | - | - | - | - |

## How This Measures Drift

### Model Drift Detection

When base models are updated or fine-tuned, ethical reasoning capabilities can regress. Our benchmarking approach detects this:

1. **Baseline**: Establish HE-300 scores for model version N
2. **Monitor**: Re-run benchmark after updates
3. **Alert**: Flag significant accuracy drops (>2 std dev)
4. **Investigate**: Per-category breakdown reveals which ethical dimensions degraded

### CIRIS Pipeline Drift

The CIRIS reasoning pipeline itself can drift:
- Template changes affecting prompts
- DMA weight adjustments
- Conscience threshold tuning

Regular benchmarking catches unintended regressions from pipeline modifications.

### Continuous Monitoring via EthicsEngine.org

[EthicsEngine.org](https://ethicsengine.org) provides:
- Automated benchmark scheduling
- Historical trend tracking
- Multi-model comparison
- Drift alerting

## What Makes This Novel

Based on our research survey, CIRIS benchmarking introduces several innovations:

### 1. Statistical Significance in Ethics Benchmarks

Most ethical reasoning benchmarks report single-run results without variance. We found:
- [Hendrycks ETHICS](https://github.com/hendrycks/ethics): Single evaluation
- [MoralBench](https://arxiv.org/abs/2406.04428): No multi-run variance
- [MoReBench](https://scale.com/blog/morebench): Process evaluation, no statistical runs

CIRIS reports **mean ± standard deviation** from 5 independent runs.

### 2. Agent Framework Improvement Quantification

Prior work evaluates raw LLM capabilities. We found no published results showing:
- "Agent framework X improves ethical reasoning by Y percentage points"
- Quantified comparison of raw model vs. agent-enhanced model

CIRIS demonstrates **+5.8 pp improvement** with an agent framework.

### 3. Reliability Metrics

Standard benchmarks report accuracy only. CIRIS tracks:
- Error rate (timeouts, API failures)
- Per-category variance
- Cross-run consistency

Our 0/1500 error rate across 5 runs demonstrates production reliability.

## Running Benchmarks

### Prerequisites

- CIRIS Agent configured with LLM provider
- [CIRISBench](https://github.com/CIRISAI/CIRISBench) server
- Together.ai API key (for Maverick) or other provider

### Quick Start

```bash
# Run 5x benchmark with CIRIS + Maverick
./run_he300_ciris_maverick.sh

# Results saved to benchmark_results/
```

### Configuration

The benchmark script configures:

```bash
# Lower concurrency for API reliability
"concurrency": 5

# Extended timeout for complex scenarios
"timeout_per_scenario": 300

# Full 300-scenario evaluation
"sample_size": 300
```

### Interpreting Results

```
==============================================
  FINAL RESULTS
==============================================
CIRIS + Maverick: 82.1% +/- 2.4%
Runs: 5
Individual: ['85.3%', '82.3%', '80.3%', '83.3%', '79.3%']
```

- **Mean > 80%**: Strong ethical reasoning
- **Std Dev < 3%**: Consistent performance
- **Errors = 0**: Production-ready reliability

## Comparison with Industry Approaches

| Aspect | Industry Standard | CIRIS Approach |
|--------|-------------------|----------------|
| Runs | Single | 5 with std dev |
| Variance | Not reported | Explicit ±X% |
| Agent improvement | Not measured | Quantified (+5.8 pp) |
| Error tracking | Rare | Zero-error target |
| Reproducibility | Scripts vary | Single executable script |

## Future Work

1. **More Models**: Benchmark CIRIS with Claude, GPT-4o, Gemini
2. **More Categories**: Expand beyond Hendrycks to newer benchmarks
3. **Continuous Integration**: Automated regression testing on PRs
4. **Cross-Cultural**: Test with culturally diverse scenario sets

## References

- Hendrycks et al. "[Aligning AI With Shared Human Values](https://arxiv.org/abs/2008.02275)" (ICLR 2021)
- [EthicsEngine.org](https://ethicsengine.org) - Continuous ethical AI monitoring
- [HE-300 Benchmark Mode](HE300_BENCHMARK.md) - Technical implementation details
- [CIRIS Architecture](ARCHITECTURE.md) - DMA and conscience system design

## Related Documentation

- [HE300_BENCHMARK.md](HE300_BENCHMARK.md) - Detailed benchmark mode documentation
- [COMPARATIVE_ANALYSIS.md](COMPARATIVE_ANALYSIS.md) - CIRIS vs other frameworks
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture overview
