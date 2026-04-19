package ai.ciris.mobile.shared.platform

actual fun currentTimeMillis(): Long = js("Date.now()") as Long
