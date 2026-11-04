package pot.launcher

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun Chip(
    text: String,
    color: Color,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        color = color.copy(alpha = 0.14f),
        shape = RoundedCornerShape(99.dp),
    ) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 7.dp, vertical = 1.dp),
            color = color,
            fontSize = 10.sp,
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
fun TagRow(vararg chips: Pair<String, Color>) {
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        chips.forEach { (text, color) -> Chip(text, color) }
    }
}

@Composable
fun Muted(
    text: String,
    modifier: Modifier = Modifier,
) {
    Text(text, modifier = modifier, color = pal.muted, fontSize = 11.sp)
}

@Composable
fun SectionTitle(text: String) {
    Text(
        text,
        color = pal.muted,
        fontSize = 11.sp,
        fontFamily = FontFamily.Monospace,
        letterSpacing = 1.sp,
    )
}
