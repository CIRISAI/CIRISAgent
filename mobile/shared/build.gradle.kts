import org.jetbrains.kotlin.gradle.ExperimentalWasmDsl
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    kotlin("multiplatform")
    kotlin("plugin.serialization")
    id("com.android.library")
    id("org.jetbrains.compose")
    kotlin("plugin.compose")
}

kotlin {
    // Suppress expect/actual beta warnings - feature is stable enough for production use
    targets.all {
        compilations.all {
            compileTaskProvider.configure {
                compilerOptions {
                    freeCompilerArgs.add("-Xexpect-actual-classes")
                }
            }
        }
    }

    // Android
    androidTarget {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }

    // iOS
    listOf(
        iosX64(),
        iosArm64(),
        iosSimulatorArm64()
    ).forEach { iosTarget ->
        iosTarget.binaries.framework {
            baseName = "shared"
            isStatic = true
        }
    }

    // Desktop (JVM)
    jvm("desktop") {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }

    // Web (WASM) - NEW TARGET
    @OptIn(ExperimentalWasmDsl::class)
    wasmJs {
        moduleName = "ciris-shared"
        browser {
            commonWebpackConfig {
                outputFileName = "ciris-shared.js"
            }
        }
        binaries.executable()
    }

    sourceSets {
        val commonMain by getting {
            dependencies {
                // Compose Multiplatform
                implementation(compose.runtime)
                implementation(compose.foundation)
                implementation(compose.material3)
                implementation(compose.materialIconsExtended)
                implementation(compose.components.resources)
                @OptIn(org.jetbrains.compose.ExperimentalComposeLibrary::class)
                implementation(compose.components.uiToolingPreview)

                // Coroutines
                implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")

                // Serialization
                implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")

                // Date/Time
                implementation("org.jetbrains.kotlinx:kotlinx-datetime:0.6.1")

                // Ktor client
                implementation("io.ktor:ktor-client-core:3.0.3")
                implementation("io.ktor:ktor-client-content-negotiation:3.0.3")
                implementation("io.ktor:ktor-serialization-kotlinx-json:3.0.3")
                implementation("io.ktor:ktor-client-logging:3.0.3")
                implementation("io.ktor:ktor-client-auth:3.0.3")

                // Multiplatform ViewModel
                implementation("org.jetbrains.androidx.lifecycle:lifecycle-viewmodel-compose:2.8.4")
                implementation("org.jetbrains.androidx.lifecycle:lifecycle-runtime-compose:2.8.4")

                // Navigation
                implementation("org.jetbrains.androidx.navigation:navigation-compose:2.8.0-alpha10")

                // Generated API client
                implementation(project(":generated-api"))
            }
        }

        val androidMain by getting {
            dependencies {
                // Ktor Android engine
                implementation("io.ktor:ktor-client-okhttp:3.0.3")

                // Ktor server for local LLM HTTP API and test automation
                implementation("io.ktor:ktor-server-core:3.0.3")
                implementation("io.ktor:ktor-server-cio:3.0.3")
                implementation("io.ktor:ktor-server-content-negotiation:3.0.3")
                implementation("io.ktor:ktor-server-status-pages:3.0.3")

                // On-device LLM inference via ONNX Runtime
                // 64-bit devices (arm64-v8a, x86_64): Full on-device inference
                // 32-bit devices (armeabi-v7a): Falls back to "Local Inference Server" provider
                implementation("com.microsoft.onnxruntime:onnxruntime-android:1.17.0")

                // Android-specific
                implementation("androidx.core:core-ktx:1.12.0")
                implementation("androidx.security:security-crypto:1.1.0-alpha06")
                implementation("androidx.activity:activity-compose:1.9.3")

                // Google Play Services
                implementation("com.google.android.gms:play-services-auth:20.7.0")
                implementation("com.android.billingclient:billing-ktx:7.1.1")
                implementation("com.google.android.play:integrity:1.4.0")

                // Chrome Custom Tabs
                implementation("androidx.browser:browser:1.7.0")

                // Image loading
                implementation("io.coil-kt:coil-compose:2.5.0")

                // WorkManager for background task scheduling
                implementation("androidx.work:work-runtime-ktx:2.9.0")
            }
        }

        val iosMain by creating {
            dependsOn(commonMain)
            dependencies {
                implementation("io.ktor:ktor-client-darwin:3.0.3")
            }
        }

        val iosX64Main by getting { dependsOn(iosMain) }
        val iosArm64Main by getting { dependsOn(iosMain) }
        val iosSimulatorArm64Main by getting { dependsOn(iosMain) }

        val desktopMain by getting {
            dependencies {
                implementation(compose.desktop.currentOs)
                implementation("io.ktor:ktor-client-cio:3.0.3")
            }
        }

        val wasmJsMain by getting {
            dependencies {
                implementation("io.ktor:ktor-client-js:3.0.3")
            }
        }

        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
                implementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
            }
        }
    }
}

android {
    namespace = "ai.ciris.mobile.shared"
    compileSdk = 34

    defaultConfig {
        minSdk = 24
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
