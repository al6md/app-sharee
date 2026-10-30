# Proguard rules for Share COC
-keepattributes Signature
-keepattributes *Annotation*
-keep class iq.sharecoc.app.data.models.** { *; }
-keep class com.google.gson.** { *; }
-dontwarn okhttp3.**
-dontwarn okio.**
