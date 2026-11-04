import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.ui.window.ApplicationScope
import androidx.compose.ui.window.Tray
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.rememberTrayState

// M4 scaffold (spec §4): the full launcher lands page by page — board first,
// then settings/tray/lifecycle. This window exists to prove the toolchain
// (Kotlin 2.3.21 + CMP 1.12.2 + Aliyun mirrors) builds and runs on this box.
fun main() = application {
    val tray = rememberTrayState()
    Window(
        onCloseRequest = ::exitApplication,
        title = "Pot",
        state = androidx.compose.ui.window.WindowState(width = 1000.dp, height = 700.dp),
    ) {
        MaterialTheme { Text("Pot launcher — M4 scaffold") }
    }
}
