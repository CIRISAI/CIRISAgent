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
