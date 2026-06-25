# CIRIS Engine - Continuous Integration (CI) Process Map

The CI/CD pipeline for the CIRIS Engine is a massive, multi-stage matrix designed to produce a highly verified 2.9.7+ image. It guarantees that every component across the ecosystem (Server, Agent, Leviculum Edge networking, and Persistence models) undergoes rigorous cross-platform fan-out, QA, and conformance checks. The pipeline orchestrates the execution of nearly 15,000 unit tests and verifies end-to-end functionality via robust staging and integration processes.

## 1. Pre-Flight & Static Analysis
The first gate focuses on ensuring basic code integrity and verifying structural evidence logic before spinning up heavy testing matrices.

* **Localization Guard**: A critical stdlib-only guard is executed (`tools/dev/check_localization_sync.py`). This guarantees reference coverage and mirror parity for Android/iOS bundles (ensuring keys referenced in Kotlin exist and translate properly in `en.json`).
* **D27 Conformance Gate**: Enforces structural runtime safety by ensuring runtime code does not mistakenly depend on its own documentation (`tools/dev/check_no_runtime_md_reference.py`).
* **Strict Type Checking (MyPy)**: Complete static type analysis utilizing `mypy` against the strict `mypy.ini` configuration for the entire `ciris_engine`.

## 2. Mass Test Sharding (Unit Tests)
The engine’s massive test suite (~11,500 tests) is processed efficiently using parallel execution to minimize feedback latency.

* **8-Way Parallel Execution Matrix**: Tests are dynamically split into 8 independent, parallel jobs using `pytest-split`.
* **Deep Code Coverage**: Results from all 8 parallel workers are consolidated into a comprehensive `coverage.xml` manifest.
* **Test Optimization Tracking**: Durations and slowest-test artifacts are collected continuously to highlight the top 1% slowest tests and detect potential regressions.

## 3. Advanced Persistence & State Testing
The pipeline exercises dual backend configurations simultaneously to ensure data integrity and structural parity.

* **PostgreSQL Dual Backend Tests**: Tests are aggressively run against a Dockerized PostgreSQL database to ensure equivalence between the lightweight internal SQLite implementation and the highly available PostgreSQL model used in distributed deployments.
* **Database Spin Up / Tear Down**: Verifies automated backend provision sequences and rollback logic.

## 4. Staged Quality Assurance (QA)
Staged QA evaluates the compiled application locally exactly as a customer would experience the release (acting as a byte-for-byte install parity check).

* **Cross-Platform Install Parity Assertion**: Validates that the active repository logic is fundamentally identical to what is packaged inside built `.whl` artifacts.
* **Dual-Backend Conformance Sweep (`qa_runner`)**: Full UI, API, and system execution checks run iteratively against both SQLite and PostgreSQL backends on the staged `venv`.
* **Upgrade-Compat Fixture Capture**: Ensures zero regressions when databases are upgraded between minor/major schemas across releases.

## 5. Leviculum Vendor & Edge Integration
The Edge routing module integration represents a massive layer of complexity for mesh-network functionality.

* **Leviculum Edge / Reticulum-rs Vendor**: Edge libraries (like `ciris_edge` which leverages the underlying Rust implementations of Leviculum/Reticulum for robust packet radio/LoRa/TCP-loopback support) are deeply integrated. Tests run across the unified interface to ensure proper cryptographic mesh-routing and network addressing.
* **FFI & Runtime Parity**: Edge 1.x / 2.x C-ABI integrations via `PyO3/UniFFI` are directly vetted on all operating systems.

## 6. Multi-Platform Artifact Generation
With code fully proven, cross-platform wheels (binaries/executables) are concurrently forged.

* **Wheel Generation Matrix**: Dedicated matrix builds concurrently forge OS-specific `.whl` binaries across `Windows x64`, `Linux x64`, and `macOS ARM64`.
* **Headless Generation**: Specifically constructs headless server binaries targeting streamlined background/Docker deployments.
* **CIRIS Desktop UberJar / PyInstaller**: Generates full offline distributions via PyInstaller and packs standalone installers utilizing the `Inno Setup` compiler with bundled, trimmed JRE implementations.

## 7. Registry & Conformance Verification (CIRISRegistry)
The agent operates via a strictly vetted trust layer. Unsigned software will not execute on client endpoints.

* **Canonical Runtime Tree Formulation**: Generates canonical hashes of the exact directory layout.
* **Manifest Cryptographic Signing**: Both the Python runtime manifest and Mobile `Resources.zip` layout manifests are signed.
* **CIRISRegistry Verification Contract**: Builds are officially registered via `ciris-build-sign` tool ensuring compliance checks against `CIRISVerify v2.0.3+` pass and allow for deployment distribution.
* **CIRISManager Notification**: Central management hubs are notified of release success and monitor subsequent deployment waves.

## 8. Release Strategy (Finalization)
Finally, production-ready artifacts are securely uploaded to their distribution points.

* **PyPI / Alias Packaging**: Packages are indexed and delivered securely.
* **Docker Multi-Arch Images**: Container registry logic creates, layers, signs, and pushes multi-architecture images directly onto the GitHub Container Registry.
* **Mobile/Android Deployments**: `Chaquopy` integrated APKs natively executing the verified wheels are produced.
* **GitHub Releases**: An aggregated, tagged version combines the Mobile APKs, Windows Installer, and generated Manifests into the official user-facing release channel.