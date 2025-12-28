plugins {
    // Kotlin Multiplatform
    kotlin("multiplatform").version("1.9.22").apply(false)
    kotlin("android").version("1.9.22").apply(false)

    // Android - using 8.1.0 to match android/ (8.2.2 causes ctypes crash on x86_64 emulators)
    id("com.android.application").version("8.1.0").apply(false)
    id("com.android.library").version("8.1.0").apply(false)

    // Compose Multiplatform
    id("org.jetbrains.compose").version("1.6.0").apply(false)

    // Python runtime - using 17.0.0
    // Known issue: x86_64 emulator crashes during ctypes initialization (works on ARM devices)
    id("com.chaquo.python").version("17.0.0").apply(false)
}

tasks.register("clean", Delete::class) {
    delete(rootProject.buildDir)
}
