package pot.launcher

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toComposeImageBitmap
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

const val LAUNCHER_VERSION = "0.1.0"

/** 关于页：只放关于内容 —— 名字、版本、一句话定位、技术栈。 */
@Composable
fun AboutPage(host: HostManager) {
    val p = pal
    val mark =
        remember {
            runCatching {
                (appIcon(256) as? java.awt.image.BufferedImage)?.toComposeImageBitmap()
            }.getOrNull()
        }
    Column(
        Modifier.fillMaxSize().padding(40.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        mark?.let {
            Image(bitmap = it, contentDescription = null, modifier = Modifier.size(84.dp))
            Spacer(Modifier.height(10.dp))
        }
        Text("Pot", fontSize = 44.sp, fontWeight = FontWeight.Bold, color = p.primary)
        Text(
            Strings.t("启动器", "Launcher") + " $LAUNCHER_VERSION",
            fontSize = 12.sp,
            fontFamily = FontFamily.Monospace,
            color = p.muted,
        )
        Spacer(Modifier.height(18.dp))
        Text(
            Strings.t(
                "单机常驻角色 + 任务看板的本机 Agent 宿主",
                "A local agent host with resident roles and a task board",
            ),
            fontSize = 15.sp,
            color = p.fg,
        )
        Spacer(Modifier.height(28.dp))
        Surface(color = p.surface, shape = RoundedCornerShape(12.dp)) {
            Column(Modifier.padding(horizontal = 24.dp, vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                StackLine(Strings.t("启动器", "Launcher"), "Kotlin · Compose Multiplatform 1.12.2")
                StackLine(
                    Strings.t("宿主", "Host"),
                    "Python " +
                        (
                            host.info?.optString("version")?.let { "· host $it" }
                                ?: Strings.t("· 未连接", "· not connected")
                        ),
                )
                StackLine(
                    Strings.t("界面", "UI"),
                    Strings.t("TRead 主题（与 WebUI 同源）", "TRead theme (same source as the WebUI)"),
                )
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
