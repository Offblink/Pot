// The material3 coordinate changed versioning away from CMP itself (1.9.0 is
// the latest stable while CMP is at 1.12.2) — the plugin's accessor still
// carries the CORRECT aligned coordinate, just at ERROR-level deprecation.
// Suppressing keeps us on the aligned version instead of guessing one.
@file:Suppress("DEPRECATION")

import org.jetbrains.compose.desktop.application.dsl.TargetFormat

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
    @Suppress("DEPRECATION") // aligned coordinate; literal versions drift
    implementation(compose.material3)
    // Minimal JSON for the loopback API payloads (mirror of the hub routes).
    implementation("org.json:json:20240303")
}

kotlin {
    jvmToolchain(17)
}

// Pot's version lives in ../pyproject.toml (the Python package declares it). The
// launcher must not grow a second copy: read it here, generate a constant for the
// About page, and hand the same string to the installer, so a release cannot ship
// three versions.
val potVersion: String =
    Regex("""(?m)^version\s*=\s*"([^"]+)"""")
        .find(file("../pyproject.toml").readText())
        ?.groupValues?.get(1)
        ?: error("no version in ../pyproject.toml")

val generatedVersionDir = layout.buildDirectory.dir("generated/pot-version")
val writeBuildInfo =
    tasks.register("writeBuildInfo") {
        val version = potVersion
        val outDir = generatedVersionDir
        inputs.property("version", version)
        outputs.dir(outDir)
        doLast {
            val dir = outDir.get().asFile.resolve("pot/launcher")
            dir.mkdirs()
            dir.resolve("BuildInfo.kt").writeText(
                """
                |package pot.launcher
                |
                |/** Generated from ../pyproject.toml by the build — do not edit. */
                |const val POT_VERSION: String = "$version"
                |
                """.trimMargin(),
            )
        }
    }
sourceSets["main"].java.srcDir(generatedVersionDir)
tasks.named("compileKotlin") { dependsOn(writeBuildInfo) }

compose.desktop {
    application {
        mainClass = "pot.launcher.MainKt"

        nativeDistributions {
            targetFormats(TargetFormat.Msi)
            packageName = "Pot"
            packageVersion = potVersion
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
