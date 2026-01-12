plugins {
    kotlin("multiplatform")
    kotlin("plugin.serialization") version "1.9.22"
    id("com.android.library")
    id("org.jetbrains.compose")
}

kotlin {
    androidTarget {
        compilations.all {
            kotlinOptions {
                jvmTarget = "17"
            }
        }
    }

    listOf(
        iosX64(),
        iosArm64(),
        iosSimulatorArm64()
    ).forEach { iosTarget ->
        iosTarget.binaries.framework {
            baseName = "shared"
            isStatic = true

            // Export Compose runtime for iOS
            export(compose.runtime)
            export(compose.foundation)
            export(compose.material3)
        }
    }

    sourceSets {
        val commonMain by getting {
            dependencies {
                // Compose Multiplatform
                implementation(compose.runtime)
                implementation(compose.foundation)
                implementation(compose.material3)
                implementation(compose.components.resources)
                @OptIn(org.jetbrains.compose.ExperimentalComposeLibrary::class)
                implementation(compose.components.uiToolingPreview)

                // Coroutines
                implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.0")

                // Serialization
                implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")

                // Date/Time
                implementation("org.jetbrains.kotlinx:kotlinx-datetime:0.5.0")

                // Ktor client (replaces OkHttp)
                implementation("io.ktor:ktor-client-core:2.3.7")
                implementation("io.ktor:ktor-client-content-negotiation:2.3.7")
                implementation("io.ktor:ktor-serialization-kotlinx-json:2.3.7")
                implementation("io.ktor:ktor-client-logging:2.3.7")
                implementation("io.ktor:ktor-client-auth:2.3.7")

                // Multiplatform ViewModel (KMP-compatible)
                implementation("org.jetbrains.androidx.lifecycle:lifecycle-viewmodel-compose:2.8.0")
                implementation("org.jetbrains.androidx.lifecycle:lifecycle-runtime-compose:2.8.0")

                // Navigation
                implementation("org.jetbrains.androidx.navigation:navigation-compose:2.7.0-alpha03")
            }
        }

        val androidMain by getting {
            dependencies {
                // Ktor Android engine
                implementation("io.ktor:ktor-client-okhttp:2.3.7")

                // Android-specific
                implementation("androidx.core:core-ktx:1.12.0")
                implementation("androidx.security:security-crypto:1.1.0-alpha06")

                // Google Play Services
                implementation("com.google.android.gms:play-services-auth:20.7.0")
                implementation("com.android.billingclient:billing-ktx:7.1.1")
                implementation("com.google.android.play:integrity:1.4.0")

                // Chrome Custom Tabs
                implementation("androidx.browser:browser:1.7.0")

                // Image loading
                implementation("io.coil-kt:coil-compose:2.5.0")
            }
        }

        val iosMain by creating {
            dependsOn(commonMain)
            dependencies {
                // Ktor iOS engine
                implementation("io.ktor:ktor-client-darwin:2.3.7")
            }
        }

        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
                implementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.0")
            }
        }

        val iosX64Main by getting { dependsOn(iosMain) }
        val iosArm64Main by getting { dependsOn(iosMain) }
        val iosSimulatorArm64Main by getting { dependsOn(iosMain) }
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
