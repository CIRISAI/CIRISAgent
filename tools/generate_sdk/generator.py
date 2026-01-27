"""
SDK Generator - Main logic for generating Kotlin Multiplatform API client.
"""

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests


class SDKGenerator:
    """Generates Kotlin Multiplatform SDK from CIRIS OpenAPI spec."""

    # Version alignment with mobile project
    KOTLIN_VERSION = "1.9.22"
    KTOR_VERSION = "2.3.7"
    COROUTINES_VERSION = "1.8.0"
    SERIALIZATION_VERSION = "1.6.3"
    DATETIME_VERSION = "0.5.0"

    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            current = Path(__file__).parent
            while current != current.parent:
                if (current / "mobile").exists():
                    project_root = current
                    break
                current = current.parent
            if project_root is None:
                raise RuntimeError("Could not find project root")

        self.project_root = Path(project_root)
        self.mobile_dir = self.project_root / "mobile"
        self.generated_api_dir = self.mobile_dir / "generated-api"
        self.openapi_spec = self.mobile_dir / "openapi.json"
        self.generator_config = self.mobile_dir / "openapi-generator-config.yaml"

    def fetch_openapi_spec(self, server_url: str = "http://localhost:8765") -> bool:
        """Fetch OpenAPI spec from running CIRIS server."""
        print(f"Fetching OpenAPI spec from {server_url}/openapi.json...")
        try:
            response = requests.get(f"{server_url}/openapi.json", timeout=10)
            response.raise_for_status()
            with open(self.openapi_spec, "w") as f:
                json.dump(response.json(), f, indent=2)
            print(f"  Saved ({len(response.content)} bytes)")
            return True
        except Exception as e:
            print(f"  ERROR: {e}")
            return False

    def start_server_and_fetch(self, port: int = 8765, timeout: int = 30) -> bool:
        """Start CIRIS server, fetch spec, then stop server."""
        print("Starting CIRIS API server...")
        server_proc = subprocess.Popen(
            [sys.executable, "main.py", "--adapter", "api", "--mock-llm", "--port", str(port)],
            cwd=self.project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            server_url = f"http://localhost:{port}"
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    if requests.get(f"{server_url}/openapi.json", timeout=2).status_code == 200:
                        break
                except requests.exceptions.ConnectionError:
                    pass
                time.sleep(1)
            else:
                print(f"  ERROR: Server did not start within {timeout} seconds")
                return False
            return self.fetch_openapi_spec(server_url)
        finally:
            print("Stopping CIRIS API server...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()

    def create_generator_config(self) -> None:
        """Create OpenAPI generator configuration file."""
        config = """generatorName: kotlin
outputDir: ./generated-api
inputSpec: ./openapi.json
packageName: ai.ciris.api
apiPackage: ai.ciris.api.apis
modelPackage: ai.ciris.api.models
library: multiplatform
additionalProperties:
  serializationLibrary: kotlinx_serialization
  useCoroutines: true
  dateLibrary: kotlinx-datetime
  enumPropertyNaming: UPPERCASE
  sourceFolder: src/commonMain/kotlin
"""
        with open(self.generator_config, "w") as f:
            f.write(config)
        print(f"Created generator config")

    def run_generator(self) -> bool:
        """Run OpenAPI generator CLI."""
        print("Running OpenAPI generator...")
        if not self.openapi_spec.exists():
            print(f"  ERROR: OpenAPI spec not found")
            return False
        if not self.generator_config.exists():
            self.create_generator_config()

        result = subprocess.run(
            ["npx", "@openapitools/openapi-generator-cli", "generate", "-c", str(self.generator_config)],
            cwd=self.mobile_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  ERROR: Generator failed\n{result.stderr}")
            return False
        print("  Generator completed successfully")
        return True

    def fix_generated_code(self) -> None:
        """Apply fixes to generated Kotlin code."""
        print("Applying fixes to generated code...")

        src_dir = self.generated_api_dir / "src" / "commonMain" / "kotlin"
        if not src_dir.exists():
            print("  ERROR: Source directory not found")
            return

        fixes_applied = 0
        files_deleted = 0

        # Process all Kotlin files
        for kt_file in src_dir.rglob("*.kt"):
            content = kt_file.read_text()
            original = content

            # Fix 1: Remove duplicate @Serializable (both same-line and multi-line)
            content = re.sub(r"@Serializable\s*@Serializable", "@Serializable", content)
            content = re.sub(r"@Serializable\s*\n\s*@Serializable", "@Serializable", content)

            # Fix 2: Replace kotlin.time.Instant with kotlinx.datetime.Instant
            content = content.replace("kotlin.time.Instant", "kotlinx.datetime.Instant")

            # Fix 3: Replace AnyOfLessThanGreaterThan with String (safest generic type)
            content = content.replace("AnyOfLessThanGreaterThan", "kotlin.String")

            # Fix 4: Add @file:OptIn for infrastructure files using experimental APIs
            if "infrastructure" in str(kt_file):
                if ("Base64" in content or "toHexString" in content) and "@file:OptIn" not in content:
                    content = (
                        "@file:OptIn(kotlin.io.encoding.ExperimentalEncodingApi::class, kotlin.ExperimentalStdlibApi::class)\n\n"
                        + content
                    )

            # Fix 5: Ensure Instant import exists
            if "Instant" in content and "import kotlinx.datetime.Instant" not in content:
                # Add after package statement
                content = re.sub(
                    r"(package [^\n]+\n)",
                    r"\1\nimport kotlinx.datetime.Instant\n",
                    content,
                    count=1,
                )

            # Fix 6: Remove duplicate imports
            lines = content.split("\n")
            seen_imports = set()
            new_lines = []
            for line in lines:
                if line.strip().startswith("import "):
                    if line.strip() not in seen_imports:
                        seen_imports.add(line.strip())
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            content = "\n".join(new_lines)

            # Fix 7: Remove invalid imports (import to self package models that don't exist)
            content = re.sub(r"import ai\.ciris\.api\.models\.(String|kotlin\.String)\n", "", content)

            # Fix 8: Fix duplicate enum serial names
            if "enum class" in content:
                content = re.sub(r'@SerialName\(value = "ok"\)(\s+)OK2', r'@SerialName(value = "ok_2")\1OK2', content)
                content = re.sub(
                    r'@SerialName\(value = "error"\)(\s+)ERROR2', r'@SerialName(value = "error_2")\1ERROR2', content
                )

            # Fix 9: Replace ALL kotlin.Any/Any? with JsonElement (for serialization)
            # This handles val declarations, Map types, and serializer generics
            # Handle kotlin.collections.Map<..., kotlin.Any> (fully qualified) - do first to avoid partial matches
            content = re.sub(
                r"kotlin\.collections\.Map<([^,]+),\s*kotlin\.Any\?>",
                r"kotlin.collections.Map<\1, kotlinx.serialization.json.JsonElement?>",
                content,
            )
            content = re.sub(
                r"kotlin\.collections\.Map<([^,]+),\s*kotlin\.Any>",
                r"kotlin.collections.Map<\1, kotlinx.serialization.json.JsonElement>",
                content,
            )
            # Handle shorthand Map<..., kotlin.Any> including in serializer<Map<...>>
            content = re.sub(
                r"Map<([^,]+),\s*kotlin\.Any\?>", r"Map<\1, kotlinx.serialization.json.JsonElement?>", content
            )
            content = re.sub(
                r"Map<([^,]+),\s*kotlin\.Any>", r"Map<\1, kotlinx.serialization.json.JsonElement>", content
            )
            # Handle direct kotlin.Any types (but NOT in function params - avoid enum companions)
            # Only replace if preceded by ): or ,\s* (indicates property type, not function param)
            content = re.sub(
                r"(val\s+`?\w+`?\s*:\s*)kotlin\.Any\?", r"\1kotlinx.serialization.json.JsonElement?", content
            )
            content = re.sub(
                r"(val\s+`?\w+`?\s*:\s*)kotlin\.Any(?![?\w])", r"\1kotlinx.serialization.json.JsonElement", content
            )

            # Fix 10: Handle nullable Map mismatches in API files - make them safe
            if "/apis/" in str(kt_file):
                # If passing nullable map where non-null expected, add ?: emptyMap()
                content = re.sub(
                    r"val localVariableBody = (\w+)\(requestBody\)",
                    r"val localVariableBody = \1(requestBody ?: emptyMap())",
                    content,
                )

            # Fix 11: Make 'data' field nullable to handle server errors gracefully
            # The server may return empty/null data on errors, but OpenAPI marks it required
            content = re.sub(
                r'@SerialName\(value = "data"\)\s*@Required\s+val\s+`?data`?\s*:\s*(\w+),',
                r'@SerialName(value = "data") val `data`: \1? = null,',
                content,
            )

            if content != original:
                kt_file.write_text(content)
                fixes_applied += 1

        # Delete only truly unfixable files (malformed structure)
        unfixable = [
            "ConfigurationFieldDefinition.kt",
            "ConfigurationStep.kt",
            "ConfigurationSessionResponse.kt",
            "ConfigurationStatusResponse.kt",
            "SuccessResponseConfigurationSessionResponse.kt",
            "SuccessResponseConfigurationStatusResponse.kt",
        ]
        for filename in unfixable:
            for kt_file in src_dir.rglob(filename):
                if kt_file.exists():
                    kt_file.unlink()
                    files_deleted += 1
                    print(f"  Deleted: {filename}")

        # Create stub types for deleted files to prevent API compilation errors
        self._create_stub_types(src_dir)

        print(f"  Applied fixes to {fixes_applied} files, deleted {files_deleted}")

    def _create_stub_types(self, src_dir: Path) -> None:
        """Create stub types for deleted models to keep APIs compiling."""
        models_dir = src_dir / "ai" / "ciris" / "api" / "models"

        stubs = {
            "ConfigurationStep.kt": """package ai.ciris.api.models
import kotlinx.serialization.*
@Serializable
data class ConfigurationStep(val id: String? = null)
""",
            "ConfigurationSessionResponse.kt": """package ai.ciris.api.models
import kotlinx.serialization.*
@Serializable
data class ConfigurationSessionResponse(val sessionId: String? = null)
""",
            "ConfigurationStatusResponse.kt": """package ai.ciris.api.models
import kotlinx.serialization.*
@Serializable
data class ConfigurationStatusResponse(val status: String? = null)
""",
            "SuccessResponseConfigurationSessionResponse.kt": """package ai.ciris.api.models
import kotlinx.serialization.*
@Serializable
data class SuccessResponseConfigurationSessionResponse(val success: Boolean = true, val data: ConfigurationSessionResponse? = null)
""",
            "SuccessResponseConfigurationStatusResponse.kt": """package ai.ciris.api.models
import kotlinx.serialization.*
@Serializable
data class SuccessResponseConfigurationStatusResponse(val success: Boolean = true, val data: ConfigurationStatusResponse? = null)
""",
        }

        for filename, content in stubs.items():
            stub_file = models_dir / filename
            stub_file.write_text(content)
            print(f"  Created stub: {filename}")

    def create_build_gradle(self) -> None:
        """Create compatible build.gradle.kts."""
        print("Creating build.gradle.kts...")
        build_gradle = f"""plugins {{
    kotlin("multiplatform") version "{self.KOTLIN_VERSION}"
    kotlin("plugin.serialization") version "{self.KOTLIN_VERSION}"
    id("com.android.library")
}}

group = "ai.ciris.mobile"
version = "1.0.0"

repositories {{
    mavenCentral()
    google()
}}

kotlin {{
    androidTarget {{
        compilations.all {{
            kotlinOptions {{
                jvmTarget = "17"
            }}
        }}
    }}
    iosX64()
    iosArm64()
    iosSimulatorArm64()

    sourceSets {{
        val commonMain by getting {{
            dependencies {{
                implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:{self.COROUTINES_VERSION}")
                implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:{self.SERIALIZATION_VERSION}")
                api("io.ktor:ktor-client-core:{self.KTOR_VERSION}")
                api("io.ktor:ktor-client-content-negotiation:{self.KTOR_VERSION}")
                api("io.ktor:ktor-serialization-kotlinx-json:{self.KTOR_VERSION}")
                api("org.jetbrains.kotlinx:kotlinx-datetime:{self.DATETIME_VERSION}")
            }}
        }}
        val commonTest by getting {{ dependencies {{ implementation(kotlin("test")) }} }}
        val androidMain by getting
        val iosX64Main by getting
        val iosArm64Main by getting
        val iosSimulatorArm64Main by getting
        val iosMain by creating {{
            dependsOn(commonMain)
            iosX64Main.dependsOn(this)
            iosArm64Main.dependsOn(this)
            iosSimulatorArm64Main.dependsOn(this)
        }}
    }}
}}

android {{
    namespace = "ai.ciris.api"
    compileSdk = 34
    defaultConfig {{ minSdk = 24 }}
    compileOptions {{
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }}
}}
"""
        (self.generated_api_dir / "build.gradle.kts").write_text(build_gradle)

    def update_settings_gradle(self) -> None:
        """Ensure generated-api is included."""
        settings_file = self.mobile_dir / "settings.gradle.kts"
        if settings_file.exists():
            content = settings_file.read_text()
            if 'include(":generated-api")' not in content:
                content = content.replace('include(":androidApp")', 'include(":androidApp")\ninclude(":generated-api")')
                settings_file.write_text(content)
                print("  Added :generated-api to settings")

    def update_shared_dependencies(self) -> None:
        """Ensure shared module depends on generated-api."""
        build_file = self.mobile_dir / "shared" / "build.gradle.kts"
        if build_file.exists():
            content = build_file.read_text()
            if 'implementation(project(":generated-api"))' not in content:
                content = content.replace(
                    'implementation("org.jetbrains.androidx.navigation:navigation-compose:2.7.0-alpha03")',
                    """implementation("org.jetbrains.androidx.navigation:navigation-compose:2.7.0-alpha03")
                implementation(project(":generated-api"))""",
                )
                build_file.write_text(content)
                print("  Added dependency to shared")

    def verify_build(self) -> bool:
        """Verify the generated code compiles."""
        print("Verifying build...")
        result = subprocess.run(
            ["./gradlew", ":generated-api:compileDebugKotlinAndroid"],
            cwd=self.mobile_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  Build successful!")
            return True
        else:
            print("  Build failed!")
            errors = [l for l in result.stdout.split("\n") if l.startswith("e:")][:20]
            for e in errors:
                print(f"  {e}")
            return False

    def clean(self) -> None:
        """Remove generated files."""
        print("Cleaning...")
        src_dir = self.generated_api_dir / "src"
        if src_dir.exists():
            shutil.rmtree(src_dir)
        for f in [self.openapi_spec, self.generator_config]:
            if f.exists():
                f.unlink()

    def generate(self, fetch_spec: bool = True, verify: bool = True) -> bool:
        """Run full generation pipeline."""
        print("=" * 60)
        print("CIRIS Mobile SDK Generator")
        print("=" * 60)

        if fetch_spec and not self.start_server_and_fetch():
            return False
        if not self.run_generator():
            return False

        self.fix_generated_code()
        self.create_build_gradle()
        self.update_settings_gradle()
        self.update_shared_dependencies()

        if verify and not self.verify_build():
            print("\nBuild failed. Check errors above.")
            return False

        print("\n" + "=" * 60)
        print("SDK generation complete!")
        print("=" * 60)
        return True
