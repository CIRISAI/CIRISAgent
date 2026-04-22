"""Bootstrap baseline evidence for remaining investigation phases (Sections 2-12).

Creates a lightweight, reproducible first-pass inventory so each section has:
- a command log
- a quick signal summary (hit counts)
- a markdown baseline report

This does NOT replace deep verification; it establishes a concrete starting point.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence


@dataclass(frozen=True)
class Probe:
    id: str
    description: str
    command: str


@dataclass(frozen=True)
class SectionBaseline:
    section: str
    title: str
    phase: str
    probes: Sequence[Probe]


BASELINES: Sequence[SectionBaseline] = (
    SectionBaseline(
        section="section2",
        title="Known bugs to verify and propose fixes",
        phase="A",
        probes=(
            Probe("accord_timestamp", "ACCORD timestamp window mismatch references", "rg -n \"5.?minute|24.?hour|timestamp\" ciris_engine tests docs"),
            Probe("security_batch", "v2.6.2 security-fix references", "rg -n \"v2.6.2|security fix|security-fix\" docs tests ciris_engine"),
            Probe("broken_nav", "Known broken pages references", "rg -n \"/verify|/commons|/compliance|/post-quantum|/principles|/sage|/scout|/medical|/trust\" docs client ciris_engine"),
        ),
    ),
    SectionBaseline(
        section="section3",
        title="Security surface for external audit / bounty scoping",
        phase="B",
        probes=(
            Probe("auth_surface", "Authentication and identity surface", "rg -n \"oauth|api key|wise authority|attestation|certificate|verify\" ciris_engine tests"),
            Probe("pq_keys", "Ed25519 + ML-DSA-65 key handling", "rg -n \"ed25519|ml-dsa|mldsa|dual signature|hybrid\" ciris_engine tests"),
            Probe("kill_switch", "Kill switch paths", "rg -n \"kill switch|killswitch|shutdown signal|terminate\" ciris_engine tests"),
        ),
    ),
    SectionBaseline(
        section="section4",
        title="Polyglot ACCORD coherence",
        phase="C",
        probes=(
            Probe("accord_impls", "ACCORD implementation file spread", "rg -n \"accord\" ciris_engine tests tools docs"),
            Probe("accord_vectors", "Shared ACCORD test vectors", "rg -n \"test vector|vectors|accord\" tests tools docs"),
            Probe("accord_line_claim", "Line-count claim references", "rg -n \"1,494|1494|line count\" docs"),
        ),
    ),
    SectionBaseline(
        section="section5",
        title="Lean 4 formal verification",
        phase="C",
        probes=(
            Probe("lean_files", "Lean theorem files", "rg -n \"theorem|lemma|sorry|axiom|admit\" --glob \"*.lean\" ."),
            Probe("consistent_lie", "CONSISTENT-LIE references", "rg -n \"CONSISTENT-LIE|consistent lie|NP-complete|ETH\" docs ."),
        ),
    ),
    SectionBaseline(
        section="section6",
        title="RATCHET validation harness",
        phase="C",
        probes=(
            Probe("ratchet_engines", "RATCHET engine references", "rg -n \"DetectionEngine|GeometricEngine|ComplexityEngine|FederationEngine|RATCHET\" ."),
            Probe("ratchet_tests", "RATCHET test references", "rg -n \"RT-0[1-5]|red-team|falsification|F-[1-5]\" tests docs ."),
        ),
    ),
    SectionBaseline(
        section="section7",
        title="Bus-factor and code legibility",
        phase="D",
        probes=(
            Probe("onboarding", "Onboarding and quickstart docs", "rg -n \"getting started|quickstart|run locally|setup wizard\" README.md docs CLAUDE.md"),
            Probe("succession", "Succession clause references", "rg -n \"succession|designated successor|dissolution|trademark|domain\" docs"),
        ),
    ),
    SectionBaseline(
        section="section8",
        title="Test coverage against the thesis",
        phase="A",
        probes=(
            Probe("thesis_components", "Accountability component test coverage refs", "rg -n \"audit chain|wise authority|conscience|parasocial|kill switch|attestation\" tests"),
            Probe("adversarial", "Adversarial / red-team test naming", "rg -n \"adversarial|red-team|negative|attack|regression\" tests"),
        ),
    ),
    SectionBaseline(
        section="section9",
        title="Documentation and undocumented invariants",
        phase="A",
        probes=(
            Probe("magic_numbers", "Potential load-bearing constants", "rg -n \"14 days|30.?min|20.?msg|timestamp|threshold|magic\" ciris_engine docs"),
            Probe("env_vars", "Environment variable reads", "rg -n \"os\\.environ|getenv\" ciris_engine ciris_adapters ciris_sdk tools"),
        ),
    ),
    SectionBaseline(
        section="section10",
        title="Production deployment and ops",
        phase="B",
        probes=(
            Probe("deployment", "Deployment pipeline references", "rg -n \"deploy|agents\\.ciris\\.ai|docker-compose|vultr|hetzner|replication|backup|restore\" docs deployment CLAUDE.md"),
            Probe("observability", "Observability alerts/logging", "rg -n \"alert|metrics|incidents|audit-chain-integrity|kill-switch|deferral failure\" docs ciris_engine"),
        ),
    ),
    SectionBaseline(
        section="section11",
        title="CIRISVerify / CIRISRegistry / CIRISLens (Rust)",
        phase="D",
        probes=(
            Probe("rust_crates", "Rust crate references", "rg -n \"CIRISVerify|CIRISRegistry|CIRISLens|crates\\.io|Cargo\\.toml\" ."),
        ),
    ),
    SectionBaseline(
        section="section12",
        title="Commons graph (Want/Need/Have/Lend/Barter)",
        phase="D",
        probes=(
            Probe("commons_graph", "Commons graph roadmap references", "rg -n \"Want|Need|Have|Lend|Barter|commons graph|/commons\" docs ciris_engine client"),
        ),
    ),
)


def run_command(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, shell=True, text=True, capture_output=True)


def extract_hit_count(stdout: str) -> int:
    lines = [line for line in stdout.splitlines() if line.strip()]
    return len(lines)


def main() -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    root = Path(f"reports/investigation/baseline_remaining_phases_{timestamp}")
    evidence_dir = root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]] = []
    command_log_lines: list[str] = []

    for section in BASELINES:
        section_results: list[dict[str, object]] = []
        for probe in section.probes:
            proc = run_command(probe.command)
            hit_count = extract_hit_count(proc.stdout)
            out_file = evidence_dir / f"{section.section}_{probe.id}.txt"
            out_file.write_text(proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.stderr else ""), encoding="utf-8")

            section_results.append(
                {
                    "probe_id": probe.id,
                    "description": probe.description,
                    "command": probe.command,
                    "hit_count": hit_count,
                    "exit_code": proc.returncode,
                    "evidence_file": out_file.as_posix(),
                }
            )
            command_log_lines.append(probe.command)

        md_lines = [
            f"# {section.section.upper()} Baseline — {section.title}",
            "",
            f"Phase: {section.phase}",
            "",
            "## Probe Results",
            "",
        ]
        for result in section_results:
            md_lines.append(
                f"- `{result['probe_id']}`: {result['description']} | hits={result['hit_count']} | exit={result['exit_code']} | evidence=`{result['evidence_file']}`"
            )

        md_lines.extend(
            [
                "",
                "## Baseline Interpretation",
                "",
                "- This is a discovery baseline only (signal inventory), not a claim-level verification.",
                "- Use the evidence files above to drive deep, line-by-line validation in follow-up passes.",
                "",
                "## Priority",
                "",
                "- Ship-before-June-1: convert high-hit probes into fully validated findings with file/line references.",
                "- Ship-this-quarter: add automation to compute stable metrics and drift alerts.",
            ]
        )

        section_md = root / f"{section.section}_baseline.md"
        section_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

        manifest.append(
            {
                "section": section.section,
                "title": section.title,
                "phase": section.phase,
                "results": section_results,
                "baseline_report": section_md.as_posix(),
            }
        )

    (root / "commands.txt").write_text("\n".join(command_log_lines) + "\n", encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(root.as_posix())


if __name__ == "__main__":
    main()
