# CIRIS Android ProGuard Rules

# Keep Python-Java bridge (Chaquopy)
-keep class com.chaquo.python.** { *; }
-dontwarn com.chaquo.python.**

# Keep all CIRIS classes
-keep class ai.ciris.mobile.** { *; }

# Keep Kotlin metadata
-keep class kotlin.Metadata { *; }
-keepclassmembers class * {
    @kotlin.Metadata *;
}

# Keep coroutines
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}

# FastAPI/Pydantic models (accessed from Python)
-keepattributes Signature
-keepattributes *Annotation*

# WebView JavaScript interface
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# Keep native methods
-keepclasseswithmembernames,includedescriptorclasses class * {
    native <methods>;
}

# Remove logging in release builds
-assumenosideeffects class android.util.Log {
    public static *** d(...);
    public static *** v(...);
    public static *** i(...);
}

# Google Play Billing
-keep class com.android.vending.billing.** { *; }

# OkHttp (for billing API)
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class okhttp3.** { *; }
-keep interface okhttp3.** { *; }

# Gson (for JSON parsing in billing)
-keepattributes Signature
-keep class com.google.gson.** { *; }
-keep class * implements com.google.gson.TypeAdapterFactory
-keep class * implements com.google.gson.JsonSerializer
-keep class * implements com.google.gson.JsonDeserializer

# Keep billing data classes for Gson serialization
-keep class ai.ciris.mobile.billing.** { *; }

# Android Security Crypto (EncryptedSharedPreferences)
-keep class com.google.crypto.tink.** { *; }
-keep class androidx.security.crypto.** { *; }

# Tink crypto library dependencies (referenced but not used at runtime)
-dontwarn com.google.api.client.http.**
-dontwarn com.google.api.client.http.javanet.**
-dontwarn org.joda.time.**

# Google API Client (optional dependency of Tink)
-dontwarn com.google.api.client.**
