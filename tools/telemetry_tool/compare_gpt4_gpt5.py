#!/usr/bin/env python3
"""Compare GPT-4 vs GPT-5 scoring results"""

import json
from pathlib import Path

# Load results
gpt4_path = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/scores/gpt-4/semantic_scores.json")
gpt5_path = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/scores/gpt-5/semantic_scores.json")

with open(gpt4_path) as f:
    gpt4_scores = json.load(f)

with open(gpt5_path) as f:
    gpt5_scores = json.load(f)

# Create lookup
gpt4_lookup = {s["module_name"]: s for s in gpt4_scores}
gpt5_lookup = {s["module_name"]: s for s in gpt5_scores}

print("=" * 80)
print("GPT-4 vs GPT-5 SCORING COMPARISON")
print("=" * 80)

# Summary stats
gpt4_passing = [s for s in gpt4_scores if s.get("mission_alignment_score", 0) >= 0.6]
gpt5_passing = [s for s in gpt5_scores if s.get("mission_alignment_score", 0) >= 0.6]

print(f"\n📊 OVERALL STATISTICS:")
print(f"  GPT-4 Pass Rate: {len(gpt4_passing)}/{len(gpt4_scores)} ({len(gpt4_passing)/len(gpt4_scores)*100:.1f}%)")
print(f"  GPT-5 Pass Rate: {len(gpt5_passing)}/{len(gpt5_scores)} ({len(gpt5_passing)/len(gpt5_scores)*100:.1f}%)")

# Average scores
gpt4_avg = sum(s.get("mission_alignment_score", 0) for s in gpt4_scores) / len(gpt4_scores)
gpt5_avg = sum(s.get("mission_alignment_score", 0) for s in gpt5_scores) / len(gpt5_scores)

print(f"\n  GPT-4 Average: {gpt4_avg:.3f}")
print(f"  GPT-5 Average: {gpt5_avg:.3f}")
print(f"  GPT-5 Improvement: {(gpt5_avg - gpt4_avg)/gpt4_avg*100:+.1f}%")

# Module-by-module comparison
print("\n" + "=" * 80)
print("MODULE-BY-MODULE COMPARISON")
print("=" * 80)
print(f"{'Module':<35} {'GPT-4':>8} {'GPT-5':>8} {'Change':>10}")
print("-" * 65)

for module_name in sorted(gpt4_lookup.keys()):
    gpt4_score = gpt4_lookup[module_name].get("mission_alignment_score", 0)
    gpt5_score = gpt5_lookup.get(module_name, {}).get("mission_alignment_score", 0)
    change = gpt5_score - gpt4_score

    # Determine status change
    status = ""
    if gpt4_score < 0.6 and gpt5_score >= 0.6:
        status = " ✅ PASS"
    elif gpt4_score >= 0.6 and gpt5_score < 0.6:
        status = " ❌ FAIL"

    print(f"{module_name:<35} {gpt4_score:>8.3f} {gpt5_score:>8.3f} {change:>+10.3f}{status}")

# Principle comparison
print("\n" + "=" * 80)
print("PRINCIPLE AVERAGES")
print("=" * 80)

principles = ["beneficence", "non_maleficence", "transparency", "autonomy", "justice", "coherence"]
print(f"{'Principle':<20} {'GPT-4':>10} {'GPT-5':>10} {'Change':>10}")
print("-" * 52)

for principle in principles:
    gpt4_avg = sum(s.get(f"{principle}_score", 0) for s in gpt4_scores) / len(gpt4_scores)
    gpt5_avg = sum(s.get(f"{principle}_score", 0) for s in gpt5_scores) / len(gpt5_scores)
    change = gpt5_avg - gpt4_avg
    print(f"{principle.title():<20} {gpt4_avg:>10.3f} {gpt5_avg:>10.3f} {change:>+10.3f}")

# Key insights
print("\n" + "=" * 80)
print("KEY INSIGHTS")
print("=" * 80)

# Biggest improvements
improvements = []
for module_name in gpt4_lookup.keys():
    gpt4_score = gpt4_lookup[module_name].get("mission_alignment_score", 0)
    gpt5_score = gpt5_lookup.get(module_name, {}).get("mission_alignment_score", 0)
    improvements.append((module_name, gpt5_score - gpt4_score))

improvements.sort(key=lambda x: x[1], reverse=True)

print("\n🚀 Top 5 Improvements:")
for module, change in improvements[:5]:
    print(f"  • {module}: {change:+.3f}")

print("\n📉 Top 5 Declines:")
for module, change in improvements[-5:]:
    if change < 0:
        print(f"  • {module}: {change:+.3f}")

# Status changes
print("\n🔄 Status Changes:")
for module_name in gpt4_lookup.keys():
    gpt4_score = gpt4_lookup[module_name].get("mission_alignment_score", 0)
    gpt5_score = gpt5_lookup.get(module_name, {}).get("mission_alignment_score", 0)

    if gpt4_score < 0.6 and gpt5_score >= 0.6:
        print(f"  ✅ {module_name}: FAIL → PASS ({gpt4_score:.3f} → {gpt5_score:.3f})")
    elif gpt4_score >= 0.6 and gpt5_score < 0.6:
        print(f"  ❌ {module_name}: PASS → FAIL ({gpt4_score:.3f} → {gpt5_score:.3f})")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)

if gpt5_avg > gpt4_avg:
    print(f"✅ GPT-5 shows {(gpt5_avg - gpt4_avg)/gpt4_avg*100:.1f}% improvement in understanding mission alignment")
else:
    print(f"⚠️ GPT-5 shows {(gpt5_avg - gpt4_avg)/gpt4_avg*100:.1f}% decrease in mission alignment scores")

print(f"🎯 GPT-5 passes {len(gpt5_passing) - len(gpt4_passing):+d} more modules than GPT-4")
print(
    f"📊 Both models agree on {sum(1 for m in gpt4_lookup if (gpt4_lookup[m].get('mission_alignment_score', 0) >= 0.6) == (gpt5_lookup.get(m, {}).get('mission_alignment_score', 0) >= 0.6))} module pass/fail statuses"
)
