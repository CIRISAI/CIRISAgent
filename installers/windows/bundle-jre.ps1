# Trim a JDK 17 install down to the minimal modules the CIRIS desktop JAR
# actually uses, then drop the result in `dist/runtime/` so Inno Setup can
# bundle it.
#
# The Compose Multiplatform Skia bindings + our Ktor / coroutines / kotlinx-
# datetime stack pull these JDK modules. List is generous on purpose: when
# the desktop JAR launches and dies with `java.lang.NoClassDefFoundError`,
# add the missing module here rather than hunting for the minimal-minimal
# set. Disk savings from over-trimming are small; user-facing crashes from
# under-trimming are catastrophic.
#
# Usage:
#     .\bundle-jre.ps1 -JarPath ..\..\client\desktopApp\build\compose\jars\CIRIS-windows-x64-2.7.6.jar -OutputDir ..\..\dist\runtime
#
# Prereqs:
#     JAVA_HOME points to a JDK 17+ install (jlink is part of the JDK).
#     The CIRIS desktop JAR must already be built (the build.yml job copies
#     it from the matrix Windows wheel build).

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$JarPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $JarPath)) {
    Write-Error "Desktop JAR not found at: $JarPath"
    exit 1
}

if (-not $env:JAVA_HOME) {
    Write-Error "JAVA_HOME not set — needed to locate jlink"
    exit 1
}

$jlink = Join-Path $env:JAVA_HOME "bin\jlink.exe"
if (-not (Test-Path $jlink)) {
    Write-Error "jlink not found at $jlink — JDK 17+ required (JRE alone is insufficient)"
    exit 1
}

# Modules required by the Compose desktop bundle. Generous baseline. If a
# module is added/removed, update the comment below explaining why.
#
#  java.base                — always required
#  java.desktop             — AWT / Swing / Skia native bindings
#  java.management          — JMX hooks Compose / coroutines emit metrics through
#  java.logging             — Compose / Ktor logging
#  java.naming              — TLS hostname verification, service-loader bindings
#  java.net.http            — Ktor uses java.net.http on JVM 11+
#  java.security.jgss       — Kerberos (rarely used but cheap to include)
#  java.sql                 — Compose runtime imports java.sql.Date in places
#  jdk.crypto.ec            — Elliptic-curve ciphers for TLS to api.* hosts
#  jdk.localedata           — i18n; locales=en restricts data to ~English
#  jdk.unsupported          — sun.misc.Unsafe — Compose / kotlinx coroutines use this
#  jdk.zipfs                — JarFileSystem is used by classloader internals
$modules = @(
    "java.base",
    "java.desktop",
    "java.management",
    "java.logging",
    "java.naming",
    "java.net.http",
    "java.security.jgss",
    "java.sql",
    "jdk.crypto.ec",
    "jdk.localedata",
    "jdk.unsupported",
    "jdk.zipfs"
) -join ","

# Clean any previous trimmed runtime — jlink refuses to write into a non-empty
# directory.
if (Test-Path $OutputDir) {
    Write-Host "Removing previous runtime at $OutputDir"
    Remove-Item -Recurse -Force $OutputDir
}

Write-Host "Running jlink to produce trimmed runtime"
Write-Host "  modules: $modules"
Write-Host "  output:  $OutputDir"

& $jlink `
    --add-modules $modules `
    --strip-debug `
    --no-man-pages `
    --no-header-files `
    --include-locales=en `
    --compress=2 `
    --output $OutputDir

if ($LASTEXITCODE -ne 0) {
    Write-Error "jlink failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$javaExe = Join-Path $OutputDir "bin\java.exe"
if (-not (Test-Path $javaExe)) {
    Write-Error "Trimmed runtime missing java.exe at $javaExe — jlink may have silently produced an incomplete image"
    exit 1
}

# Quick smoke test — the trimmed JRE must at least answer -version without
# blowing up, otherwise the installer ships a broken JRE.
& $javaExe -version
if ($LASTEXITCODE -ne 0) {
    Write-Error "Trimmed JRE failed -version smoke test"
    exit $LASTEXITCODE
}

$size = (Get-ChildItem $OutputDir -Recurse | Measure-Object -Sum Length).Sum / 1MB
Write-Host ("Trimmed JRE built — {0:N1} MB at {1}" -f $size, $OutputDir)
