package pot.launcher

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/**
 * TRead palette (spec §6): the launcher and the web UI are one skin. Hex values
 * are the same pairs web/style.css carries.
 */
data class Palette(
    val background: Color,
    val surface: Color,
    val surfaceVariant: Color,
    val outline: Color,
    val fg: Color,
    val muted: Color,
    val primary: Color,
    val onPrimary: Color,
    val secondary: Color,
    val tertiary: Color,
    val error: Color,
    val warning: Color,
)

val DarkPalette =
    Palette(
        background = Color(0xFF06060A),
        surface = Color(0xFF0A0A14),
        surfaceVariant = Color(0xFF0D0D18),
        outline = Color(0xFF1A1A2E),
        fg = Color(0xFFE0E0E0),
        muted = Color(0xFF666666),
        primary = Color(0xFF4ADE80),
        onPrimary = Color(0xFF06060A),
        secondary = Color(0xFF60A5FA),
        tertiary = Color(0xFFA78BFA),
        error = Color(0xFFF87171),
        warning = Color(0xFFFBBF24),
    )

val LightPalette =
    Palette(
        background = Color(0xFFF6F7F9),
        surface = Color(0xFFFFFFFF),
        surfaceVariant = Color(0xFFECEEF2),
        outline = Color(0xFFE2E5EA),
        fg = Color(0xFF1B1D22),
        muted = Color(0xFF6B7280),
        primary = Color(0xFF15803D),
        onPrimary = Color(0xFFFFFFFF),
        secondary = Color(0xFF2563EB),
        tertiary = Color(0xFF7C3AED),
        error = Color(0xFFDC2626),
        warning = Color(0xFFD97706),
    )

val LocalPalette = staticCompositionLocalOf { LightPalette }

/** The palette of the current theme, for composables that need the raw values. */
val pal: Palette
    @Composable
    get() = LocalPalette.current

@Composable
fun PotTheme(
    dark: Boolean,
    content: @Composable () -> Unit,
) {
    val p = if (dark) DarkPalette else LightPalette
    val scheme =
        if (dark) {
            darkColorScheme(
                primary = p.primary,
                onPrimary = p.onPrimary,
                secondary = p.secondary,
                tertiary = p.tertiary,
                background = p.background,
                onBackground = p.fg,
                surface = p.surface,
                onSurface = p.fg,
                surfaceVariant = p.surfaceVariant,
                onSurfaceVariant = p.muted,
                outline = p.outline,
                error = p.error,
                onError = Color.White,
            )
        } else {
            lightColorScheme(
                primary = p.primary,
                onPrimary = p.onPrimary,
                secondary = p.secondary,
                tertiary = p.tertiary,
                background = p.background,
                onBackground = p.fg,
                surface = p.surface,
                onSurface = p.fg,
                surfaceVariant = p.surfaceVariant,
                onSurfaceVariant = p.muted,
                outline = p.outline,
                error = p.error,
                onError = Color.White,
            )
        }
    androidx.compose.runtime.CompositionLocalProvider(
        LocalPalette provides p,
    ) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}

/** Column accent per board status (spec §4.2/§6: 两端一皮). */
@Composable
fun statusColor(status: String): Color {
    val p = pal
    return when (status) {
        "todo" -> p.secondary
        "doing" -> p.warning
        "review" -> p.tertiary
        "done" -> p.primary
        "blocked" -> p.error
        else -> p.muted
    }
}
