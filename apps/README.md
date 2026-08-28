# CIRIS application shells

The two app shells that wrap the published CIRIS client: the Android APK and the
iOS IPA.

**The client UI is not built here.** It lives in
[CIRISAI/CIRISClient](https://github.com/CIRISAI/CIRISClient) and ships as
release artifacts. This directory contains only what a store build needs and an
`.aar` cannot provide: the manifest, the entry-point Activity, the Chaquopy
Python runtime, signing config, icons, and the Xcode project.

```
apps/
  android/    APK shell   — manifest, MainActivity, Chaquopy, wheels, signing
  ios/        IPA shell   — Xcode project + the iOS substrate Resources
  gradle/ gradlew settings.gradle.kts build.gradle.kts
```

## Getting the client

Both artifacts are fetched, never committed — they are pre-built binaries of
another repo's source, and at 15 MB + 108 MB per bump they would put this repo
into the size audit's failure band within a few releases.

```bash
python3 tools/fetch_client_artifacts.py               # both platforms
python3 tools/fetch_client_artifacts.py --platform android
```

The version comes from the `ciris-client==` pin in `requirements.txt`. That pin
exists because `ciris-server` requires a *range* (`>=0.5.190,<0.6`), and a range
resolves differently on different machines — the `.aar` linked into the APK and
the client inside the Python wheel must be the same build, not merely compatible
ones.

## Building

```bash
cd apps
./gradlew :android:assembleDebug
```

`local.properties` is machine-specific and gitignored; create it with
`sdk.dir=/path/to/Android/Sdk`.

## The dependency block you must not trim

`android/build.gradle` names ~25 libraries — coroutines, ktor, yubikit, billing,
coil — that the app itself never imports. They are there because **the published
`.aar` carries no POM**: it is a bare archive on a GitHub release, not a Maven
artifact, so it contributes no transitive dependencies. Every library the shared
client uses internally has to be declared here or the class is simply absent at
runtime.

Deleting a line from that block does not break the build. It breaks the app, on
whichever screen touches the missing class. Keep it in step with CIRISClient's
own `shared/build.gradle.kts` when bumping the pin.

## What used to be here

| was | now |
|---|---|
| `client/shared` | the published `.aar` / `.xcframework` |
| `client/desktopApp` | the uber-jar inside the `ciris-client` wheel, located by `ciris_engine/desktop_launcher.py` |
| `client/generated-api` | deleted upstream — the published client has zero `ai.ciris.api` references |
