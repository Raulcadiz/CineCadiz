import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    // kotlin.android lo incluye AGP 9.x — no aplicar manualmente
    alias(libs.plugins.kotlin.compose)
}

val keystorePropsFile = rootProject.file("keystore.properties")
val keystoreProps = Properties().apply {
    if (keystorePropsFile.exists()) load(keystorePropsFile.inputStream())
}

// versionCode auto-increments with each build (seconds since epoch, fits in Int until year 2038+)
// This guarantees every new APK can install over the previous one without uninstalling.
val autoVersionCode = (System.currentTimeMillis() / 1000).toInt()

android {
    namespace = "com.example.cinecity"
    compileSdk {
        version = release(36) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "com.cinecadiz.app"
        minSdk = 21
        targetSdk = 36
        versionCode = autoVersionCode
        versionName = "2.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        // Single signing config used by ALL build types so the signature never
        // changes between debug and release — eliminating the need to uninstall.
        create("appKey") {
            storeFile     = file(keystoreProps["storeFile"] as String)
            storePassword = keystoreProps["storePassword"] as String
            keyAlias      = keystoreProps["keyAlias"]      as String
            keyPassword   = keystoreProps["keyPassword"]   as String
        }
    }

    buildTypes {
        release {
            signingConfig     = signingConfigs.getByName("appKey")
            isMinifyEnabled   = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            // Same key as release → debug APKs can upgrade/downgrade with release APKs.
            signingConfig   = signingConfigs.getByName("appKey")
            isMinifyEnabled = false
            isDebuggable    = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    buildFeatures {
        compose = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    // AppCompat (needed for AppCompatActivity)
    implementation(libs.appcompat)

    // Compose BOM
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.icons.extended)
    debugImplementation(libs.compose.ui.tooling)

    // Activity & Navigation
    implementation(libs.activity.compose)
    implementation(libs.navigation.compose)

    // Lifecycle / ViewModel
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.lifecycle.runtime)

    // Network
    implementation(libs.retrofit)
    implementation(libs.retrofit.gson)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.gson)

    // Images
    implementation(libs.coil)

    // Media3 ExoPlayer
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.exoplayer.hls)
    implementation(libs.media3.datasource)
    implementation(libs.media3.ui)

    // Coroutines
    implementation(libs.coroutines.android)

    // Tests
    testImplementation(libs.junit)
    androidTestImplementation(libs.ext.junit)
    androidTestImplementation(libs.espresso.core)
}
