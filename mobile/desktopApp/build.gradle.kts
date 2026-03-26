import org.jetbrains.compose.desktop.application.dsl.TargetFormat

plugins {
    kotlin("jvm")
    kotlin("plugin.serialization") version "1.9.22"
    id("org.jetbrains.compose")
}

dependencies {
    implementation(project(":shared"))
    implementation(compose.desktop.currentOs)
    implementation(compose.runtime)
    implementation(compose.foundation)
    implementation(compose.material3)

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-swing:1.8.0")

    // Test automation server (Ktor embedded)
    val ktorVersion = "2.3.12"
    implementation("io.ktor:ktor-server-core:$ktorVersion")
    implementation("io.ktor:ktor-server-cio:$ktorVersion")
    implementation("io.ktor:ktor-server-content-negotiation:$ktorVersion")
    implementation("io.ktor:ktor-serialization-kotlinx-json:$ktorVersion")
    implementation("io.ktor:ktor-server-status-pages:$ktorVersion")
}

compose.desktop {
    application {
        mainClass = "ai.ciris.desktop.MainKt"

        nativeDistributions {
            targetFormats(TargetFormat.Dmg, TargetFormat.Msi, TargetFormat.Deb)
            packageName = "CIRIS"
            packageVersion = "2.0.0"
            description = "CIRIS Agent Desktop Application"
            vendor = "CIRIS L3C"

            macOS {
                bundleID = "ai.ciris.desktop"
                iconFile.set(project.file("icons/icon.icns"))
            }

            windows {
                iconFile.set(project.file("icons/icon.ico"))
                menuGroup = "CIRIS"
                upgradeUuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            }

            linux {
                iconFile.set(project.file("icons/icon.png"))
            }
        }
    }
}

kotlin {
    jvmToolchain(17)
}

// Sync localization JSON files from main repo to resources
tasks.register<Sync>("syncLocalizationResources") {
    description = "Sync localization JSON files from main repo to resources"
    from("../../localization") {
        include("*.json")
        exclude("manifest.json")
    }
    into("src/main/resources/localization")
}

// Ensure localization resources are synced before processing resources
tasks.named("processResources") {
    dependsOn("syncLocalizationResources")
}
