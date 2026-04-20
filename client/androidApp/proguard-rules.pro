# CIRIS Mobile ProGuard Rules (KMP version)
# Based on original android/app/proguard-rules.pro

# Keep Python runtime classes
-keep class com.chaquo.python.** { *; }
-dontwarn com.chaquo.python.**

# Keep Compose classes
-keep class androidx.compose.** { *; }
-keep class androidx.lifecycle.** { *; }

# Keep Ktor client
-keep class io.ktor.** { *; }
-dontwarn io.ktor.**

# Keep kotlinx serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keep,includedescriptorclasses class ai.ciris.mobile.shared.models.**$$serializer { *; }
-keepclassmembers class ai.ciris.mobile.shared.models.** {
    *** Companion;
}
-keepclasseswithmembers class ai.ciris.mobile.shared.models.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Keep Google Play Services
-keep class com.google.android.gms.** { *; }
-dontwarn com.google.android.gms.**

# Keep Billing client
-keep class com.android.billingclient.** { *; }

# Keep shared module
-keep class ai.ciris.mobile.shared.** { *; }
