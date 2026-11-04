package pot.launcher

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

const val LAUNCHER_VERSION = "0.1.0"

/** 关于页：只放关于内容 —— 名字、版本、一句话定位、技术栈。 */
@Composable
fun AboutPage(host: HostManager) {
    val p = pal
    Column(
        Modifier.fillMaxSize().padding(40.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Pot", fontSize = 44.sp, fontWeight = FontWeight.Bold, color = p.primary)
        Text(
            "启动器 $LAUNCHER_VERSION",
            fontSize = 12.sp,
            fontFamily = FontFamily.Monospace,
            color = p.muted,
        )
        Spacer(Modifier.height(18.dp))
        Text("单机常驻角色 + 任务看板的本机 Agent 宿主", fontSize = 15.sp, color = p.fg)
        Spacer(Modifier.height(28.dp))
        Surface(color = p.surface, shape = RoundedCornerShape(12.dp)) {
            Column(Modifier.padding(horizontal = 24.dp, vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                StackLine("启动器", "Kotlin · Compose Multiplatform 1.12.2")
                StackLine("宿主", "Python " + (host.info?.optString("version")?.let { "· host $it" } ?: "· 未连接"))
                StackLine("界面", "TRead 主题（与 WebUI 同源）")
            }
        }
    }
}

@Composable
private fun StackLine(
    label: String,
    value: String,
) {
    val p = pal
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(
            label,
            Modifier.padding(top = 1.dp),
            fontSize = 11.sp,
            fontFamily = FontFamily.Monospace,
            color = p.muted,
        )
        Text(value, fontSize = 13.sp, color = p.fg)
    }
}
