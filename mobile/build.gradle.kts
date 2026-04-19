plugins {
    // Kotlin 2.x with new Compose compiler architecture
    kotlin("multiplatform").version("2.0.21").apply(false)
    kotlin("android").version("2.0.21").apply(false)
    kotlin("plugin.serialization").version("2.0.21").apply(false)
    kotlin("plugin.compose").version("2.0.21").apply(false)

    // Android Gradle Plugin 8.5+ (required for Kotlin 2.x)
    id("com.android.application").version("8.5.2").apply(false)
    id("com.android.library").version("8.5.2").apply(false)

    // Compose Multiplatform 1.7+
    id("org.jetbrains.compose").version("1.7.1").apply(false)

    // Python runtime - Chaquopy 17.0.0 (compatible with AGP 8.5+, Kotlin 2.x)
    id("com.chaquo.python").version("17.0.0").apply(false)
}

// Clean task - extend base plugin's clean
tasks.matching { it.name == "clean" }.configureEach {
    doLast {
        delete(rootProject.layout.buildDirectory)
    }
}
