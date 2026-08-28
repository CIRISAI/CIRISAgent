// CIRIS application shells.
//
// The shared Kotlin/Compose client is NOT built here any more. It is published
// by CIRISAI/CIRISClient as `ciris-client-<version>.aar` (Android) and
// `ciris-client-<version>.xcframework.zip` (iOS), and this tree contains only
// the two app shells that wrap it: the APK and the IPA.
//
// There is no `:shared`, `:desktopApp` or `:generated-api` module:
//   - :shared        -> the published .aar / .xcframework
//   - :desktopApp    -> the desktop uber-jar inside the `ciris-client` wheel,
//                       which `ciris_server.desktop_launcher` already locates
//   - :generated-api -> deleted upstream; the published client carries zero
//                       references to `ai.ciris.api`, so nothing consumes it
rootProject.name = "CIRIS-Apps"

pluginManagement {
    repositories {
        google()
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        // The published ciris-client .aar, fetched into android/libs/ by
        // tools/fetch_client_artifacts.py. Declared here rather than in the
        // module because dependencyResolutionManagement owns repositories for
        // the whole build; a project-level `repositories {}` block would be
        // ignored or rejected depending on the mode.
        flatDir { dirs("android/libs") }
    }
}

include(":android")
