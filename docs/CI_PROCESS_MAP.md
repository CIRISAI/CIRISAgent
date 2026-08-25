# CIRIS Ecosystem - Continuous Integration (CI) Process Map

The CI/CD pipeline for the CIRIS Ecosystem is a massive, multi-stage matrix designed to produce a highly verified 2.9.7+ image. It guarantees that the core ecosystem flow undergoes rigorous cross-platform fan-out, QA, and conformance checks.

To ensure absolute integrity, the CI process strictly evaluates the dependency chain from the foundation up: starting at **CIRISVerify**, moving through **CIRISPersist**, **CIRISEdge**, **CIRISServer**, and culminating in the **CIRISAgent**. Across this entire chain, the pipeline orchestrates the execution of over **15,000 unit tests** and verifies end-to-end functionality via robust staging and integration processes.

---

## 1. CIRISConformance (Ecosystem Matrix & Contract Governance)
While not a deployable binary itself, CIRISConformance dictates the integration boundaries and testing contracts for the entire CI lifecycle. It defines the reference matrices that the underlying substrate elements (Verify, Persist, Edge) must satisfy before any combination is allowed to boot.

* **CI Stages & Steps:**
  * **Adversarial Fire-Tests:** Executes isolated attack vectors against the substrate data-access surfaces (ensuring caller scope admission and hardware-backed attestation holds under duress).
  * **Matrix Alignment Validation:** Enforces strict compatibility floors between dependent projects to prevent cross-library (`PyO3`/`UniFFI`) initialization skew.

## 2. CIRISVerify (Cryptographic & Trust Foundation)
As the bedrock of the ecosystem, CIRISVerify handles structural evidence, attestation, and cryptographic signing. Code cannot progress unless the trust layer is absolutely flawless.

* **CI Stages & Steps:**
  * **Pre-Flight:** AST-level verification and D27 Conformance Gates (ensuring runtime code does not depend on `.md` documentation).
  * **Static Analysis:** Strict `mypy` type checking across all cryptographic modules.
  * **Multi-Arch Compilation:** Builds the underlying C/Rust FFI extensions (`.so`, `.dylib`, `.dll`) for `x86_64` and `aarch64`.
* **Test Coverage:** ~1,500 tests.
  * Focuses heavily on key generation, signature determinism, and isolated hardware-security-module (TPM2) mock testing.

## 3. CIRISPersist (Data & State Management)
Operating immediately above the trust layer, CIRISPersist ensures data durability, secure local storage, and database schema compatibility across platforms.

* **CI Stages & Steps:**
  * **Dual-Backend Conformance Sweep:** Tests are aggressively run against both Dockerized **PostgreSQL** (distributed) and **SQLite** (local/mobile) to ensure absolute functional parity.
  * **Upgrade-Compat Fixture Capture:** Evaluates database migration logic. Snapshots of legacy schemas are loaded and migrated to guarantee zero data loss across upgrades.
  * **Cross-Platform Parity Assertion:** Validates that data serialized on Windows x64 can be losslessly read by macOS ARM64 and Linux runtimes.
* **Test Coverage:** ~2,500 tests.
  * Focuses on ACID compliance, concurrent locking, multi-threaded isolation, and I/O performance regressions.

## 4. CIRISEdge (Mesh Networking & Federation)
The routing and networking tier. This project integrates deeply with external transport vendors and manages the complex, decentralized peer-to-peer logic.

* **CI Stages & Steps:**
  * **Leviculum Vendor Integration:** Deep integration testing with the `Reticulum-rs` and `Leviculum` Rust vendor libraries. Validates the FFI boundary (`PyO3/UniFFI`) for TCP-loopback, LoRa, and Packet Radio transport stubs.
  * **Network Mesh Simulation:** Spawns virtualized local topologies to test `CIRIS-V1` NodeCode peer discovery and cryptographic routing table propagation.
  * **Latency & Drain Assertions:** Checks event loop stalls and asserts that `flush()` and `stop()` mechanisms drain queues within strict millisecond thresholds.
* **Test Coverage:** ~3,000 tests.
  * Covers byte-level packet encoding, asynchronous stream handling, SAS (Short Authentication String) verification, and network boundary fuzzing.

## 5. CIRISServer (Headless Operations & Administration)
The centralized or localized headless engine that orchestrates the persistence and edge layers, handling API requests, A2A (Agent-to-Agent) negotiations, and heavy background tasks.

* **CI Stages & Steps:**
  * **API Conformance:** Full HTTP/REST and Server-Sent Events (SSE) surface testing (e.g., `/v1/federation/*`, `/a2a` endpoints). Validates token-tier gating (Observer vs. Admin).
  * **Headless Generation:** Constructs optimized headless binaries utilizing `PyInstaller` tailored for Docker and headless Linux environments.
  * **Docker Multi-Arch Images:** Container registry logic creates, layers, signs, and pushes multi-architecture images (`amd64`/`arm64`) directly onto the GitHub Container Registry.
* **Test Coverage:** ~3,500 tests.
  * Tests focus on rate-limiting, CORS policies, streaming event serialization, concurrent task processing (`asyncio` limits), and backend provisioning.

## 6. CIRISAgent (User Experience & Mobile Interfaces)
The culmination of the ecosystem. The Agent integrates all lower-level services into a cohesive, user-facing client application and desktop/mobile interface.

* **CI Stages & Steps:**
  * **Localization Guard:** A critical stdlib-only guard (`tools/dev/check_localization_sync.py`) executed to guarantee reference coverage and mirror parity across 29 locales for Android/iOS Kotlin/Swift bundles (preventing raw key renders like `setup_error_signing_unavailable_title`).
  * **Staged Quality Assurance (QA - `qa_runner`):** Full UI, Agent-Mode capability (CLIENT/PROXY/SERVER), and workflow simulation tests. This acts as a byte-for-byte install parity check mimicking exactly what a user installs.
  * **CIRISRegistry Verification:** Generates canonical hashes of the `Resources.zip` and Python runtime tree. Signs the build manifests with `ciris-build-sign` to satisfy the `CIRISVerify v2.0.3+` contract.
  * **Final Output Generation:** Compiles the cross-platform wheels, the `Chaquopy` Android APKs, the Desktop UberJar, and the `Inno Setup` Windows Installer. Aggregates these into the final GitHub Release.
* **Test Coverage:** ~4,500+ tests.
  * Sharded 8-ways for speed. Focuses on UI bridging, complex capability execution, safety interpretation sweeps, and end-to-end integration across all 5 projects.