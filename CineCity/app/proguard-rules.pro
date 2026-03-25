-keepattributes SourceFile,LineNumberTable

# Gson / Retrofit data classes
-keepclassmembers class com.example.cinecity.data.model.** { *; }
-keep class com.example.cinecity.data.model.** { *; }

# Retrofit interface
-keep,allowobfuscation interface com.example.cinecity.data.api.ApiService

# Gson
-keepattributes Signature
-keepattributes *Annotation*
-dontwarn sun.misc.**
-keep class com.google.gson.** { *; }
-keep class * implements com.google.gson.TypeAdapterFactory
-keep class * implements com.google.gson.JsonSerializer
-keep class * implements com.google.gson.JsonDeserializer

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class okhttp3.** { *; }

# Coil
-dontwarn coil.**

# Media3 / ExoPlayer
-dontwarn androidx.media3.**

# Kotlin
-dontwarn kotlin.**
-keep class kotlin.** { *; }
-keep class kotlinx.** { *; }
