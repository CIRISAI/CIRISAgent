# Semantic Scoring System - Pure Evaluation

## Purpose
Use GPT-4 semantic evaluation to score all CIRIS modules for mission alignment.
- **Passing Score: ≥0.6**
- **No recommendations from the tool**
- **Only identify scores and red flags**

---

## Phase 1: Complete Semantic Scoring (Immediate)

### 1.1 Score All 35 Modules
- [ ] Run semantic evaluator on all 35 telemetry docs
- [ ] Use GPT-4 to score each covenant principle (0.0-1.0)
- [ ] Calculate mission alignment score (average of 6 principles)
- [ ] Store scores in database
- [ ] Generate score report

### 1.2 Identify Passing Modules
- [ ] List all modules with score ≥0.6 (PASSING)
- [ ] List all modules with score <0.6 (NEEDS ATTENTION)
- [ ] Create distribution chart of scores
- [ ] Calculate system-wide average
- [ ] Identify top 5 and bottom 5 modules

### 1.3 Red Flag Detection
- [ ] Flag any module with ANY principle <0.2 (CRITICAL)
- [ ] Flag any module with mission score <0.4 (HIGH RISK)
- [ ] Flag any module with transparency <0.3 (AUDIT RISK)
- [ ] Flag any module with non_maleficence <0.3 (SAFETY RISK)
- [ ] Flag any module with justice <0.3 (FAIRNESS RISK)

---

## Phase 2: Semantic Analysis Report (Day 1)

### 2.1 Score Summary
- [ ] Create score matrix (35 modules × 6 principles)
- [ ] Generate heatmap visualization
- [ ] Calculate principle averages across system
- [ ] Identify systemic strengths (principles >0.7)
- [ ] Identify systemic weaknesses (principles <0.5)

### 2.2 Pass/Fail Report
- [ ] Count modules passing (≥0.6)
- [ ] Count modules failing (<0.6)
- [ ] Calculate pass rate percentage
- [ ] Group by module type (BUS, SERVICE, COMPONENT, etc.)
- [ ] Identify patterns in pass/fail

### 2.3 Red Flag Report
- [ ] List all critical red flags
- [ ] Prioritize by severity
- [ ] Group by risk type
- [ ] Create executive summary
- [ ] Generate compliance matrix

---

## Phase 3: Continuous Scoring Pipeline (Day 2)

### 3.1 Automated Scoring
- [ ] Create cron job for weekly scoring
- [ ] Set up score change detection
- [ ] Build score history tracking
- [ ] Enable trend analysis
- [ ] Create score alerts

### 3.2 Score Validation
- [ ] Run scoring 3 times for consistency
- [ ] Calculate score variance
- [ ] Identify unstable scores
- [ ] Create confidence intervals
- [ ] Flag inconsistent evaluations

### 3.3 Scoring Dashboard
- [ ] Build real-time score display
- [ ] Show current vs. baseline scores
- [ ] Display red flag alerts
- [ ] Create score timeline
- [ ] Enable score drill-down

---

## Phase 4: Integration with Existing Tools (Day 3)

### 4.1 Grace Integration
- [ ] Add semantic score check to Grace
- [ ] Block commits if module drops below 0.6
- [ ] Add red flag warnings
- [ ] Create score improvement hints
- [ ] Enable score tracking in CI

### 4.2 API Endpoints for Scores
- [ ] GET /v1/telemetry/scores - All current scores
- [ ] GET /v1/telemetry/scores/{module} - Module score
- [ ] GET /v1/telemetry/redflags - Current red flags
- [ ] GET /v1/telemetry/trends - Score trends
- [ ] GET /v1/telemetry/compliance - Pass/fail status

### 4.3 Test Integration
- [ ] Add semantic score assertions to tests
- [ ] Fail tests if score <0.6
- [ ] Add red flag tests
- [ ] Create score regression tests
- [ ] Enable mission validation in CI

---

## Success Metrics

### Quantitative Targets
- [ ] 100% of modules scored semantically
- [ ] ≥80% of modules scoring ≥0.6
- [ ] 0 critical red flags (any principle <0.2)
- [ ] <5 high risk modules (score <0.4)
- [ ] System average ≥0.65

### Quality Checks
- [ ] Score consistency >90% (variance <0.1)
- [ ] All scores validated by GPT-4
- [ ] No heuristic scoring used
- [ ] Complete principle coverage
- [ ] Full module coverage

---

## Commands

### Run Complete Scoring
```bash
python -m tools.telemetry_tool.semantic_scorer --all
```

### Check Specific Module Score
```bash
python -m tools.telemetry_tool.semantic_scorer --module LLM_BUS
```

### Generate Red Flag Report
```bash
python -m tools.telemetry_tool.semantic_scorer --redflags
```

### View Score Dashboard
```bash
python -m tools.telemetry_tool.semantic_scorer --dashboard
```

### Export Score Matrix
```bash
python -m tools.telemetry_tool.semantic_scorer --export scores.csv
```

---

## Red Flag Thresholds

| Principle | Critical (<) | High Risk (<) | Warning (<) | Pass (≥) |
|-----------|-------------|---------------|-------------|----------|
| Beneficence | 0.2 | 0.4 | 0.5 | 0.6 |
| Non-maleficence | 0.2 | 0.4 | 0.5 | 0.6 |
| Transparency | 0.2 | 0.4 | 0.5 | 0.6 |
| Autonomy | 0.2 | 0.4 | 0.5 | 0.6 |
| Justice | 0.2 | 0.4 | 0.5 | 0.6 |
| Coherence | 0.2 | 0.4 | 0.5 | 0.6 |
| **Overall** | **0.2** | **0.4** | **0.5** | **0.6** |

---

## What We're NOT Doing

- ❌ NOT implementing recommendations from the tool
- ❌ NOT assuming what modules should do
- ❌ NOT adding features based on scores
- ❌ NOT changing modules based on evaluation
- ❌ NOT using heuristics or keywords

## What We ARE Doing

- ✅ Getting pure semantic scores from GPT-4
- ✅ Identifying passing (≥0.6) and failing (<0.6) modules
- ✅ Detecting red flags and risks
- ✅ Creating visibility into mission alignment
- ✅ Enabling score-based quality gates

---

## Output Files

```
/home/emoore/CIRISAgent/tools/telemetry_tool/scores/
├── semantic_scores.json        # All module scores
├── red_flags.json              # Critical issues
├── score_matrix.csv            # Full scoring matrix
├── pass_fail_report.md         # Summary report
└── score_history.db            # Historical scores
```

---

*This is pure semantic scoring. No assumptions. No recommendations. Just truth.*
