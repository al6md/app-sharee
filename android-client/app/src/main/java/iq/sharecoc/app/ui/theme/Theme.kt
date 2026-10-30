package iq.sharecoc.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection

private val DarkColorScheme = darkColorScheme(
    primary = AccentGold,
    onPrimary = PrimaryDark,
    primaryContainer = PrimaryGreen,
    onPrimaryContainer = TextWhite,
    secondary = AccentGoldLight,
    onSecondary = PrimaryDark,
    background = PrimaryDark,
    onBackground = TextWhite,
    surface = PrimarySurface,
    onSurface = TextWhite,
    surfaceVariant = CardBackground,
    onSurfaceVariant = TextLight
)

@Composable
fun ShareCOCTheme(content: @Composable () -> Unit) {
    // إجبار اتجاه الواجهة من اليمين لليسار (RTL) لدعم اللغة العربية بشكل أصيل
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
        MaterialTheme(
            colorScheme = DarkColorScheme,
            content = content
        )
    }
}
