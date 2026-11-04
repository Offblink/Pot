plugins {
    kotlin("jvm") version "2.3.21"
    // Kotlin 2.x needs the compose compiler plugin at the same Kotlin version
    // (scaffold skill pitfall #1) — otherwise: "apply org.jetbrains.kotlin.plugin.compose".
    id("org.jetbrains.kotlin.plugin.compose") version "2.3.21"
    id("org.jetbrains.compose") version "1.12.2"
}

// GFW recipe (scaffold skill): services.gradle.org and dl.google.com are
// unreachable direct — Aliyun mirrors first, official repos as fallback.
repositories {
    maven("https://maven.aliyun.com/repository/public")
    maven("https://maven.aliyun.com/repository/google")
    google()
    mavenCentral()
}

dependencies {
    // Pitfall #2: without compose.desktop.currentOs + material3 the whole
    // file fills with "Unresolved reference 'androidx'".
    implementation(compose.desktop.currentOs)
    implementation(compose.material3)
}

kotlin {
    jvmToolchain(17)
}

compose.desktop {
    application {
        mainClass = "MainKt"

        nativeDistributions {
            targetFormats(TargetFormat.Msi)
            packageName = "Pot"
            packageVersion = "0.1.0"
            description = "Pot launcher — board, settings, host lifecycle"
            vendor = "Pot"

            windows {
                menuGroup = "Pot"
                // per-machine install so the tray app finds its own shortcuts
                upgradeUuid = "8f6e0a4e-0f13-4a21-9d5c-6a1b7d4a9c31"
            }
        }
    }
}
