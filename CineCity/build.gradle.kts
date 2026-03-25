plugins {
    alias(libs.plugins.android.application) apply false
    // kotlin.android lo incluye AGP 9.x internamente — no declarar aquí
    alias(libs.plugins.kotlin.compose) apply false
}
