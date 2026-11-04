package pot.launcher

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 设置页（spec §4.2）: host lifecycle + paths, and the model config the chat rides. */
@Composable
fun SettingsPage(
    state: PotState,
    host: HostManager,
    settings: LauncherSettings,
) {
    val p = pal
    var python by remember { mutableStateOf(settings.python) }
    var repo by remember { mutableStateOf(settings.repo) }
    var apiKey by remember { mutableStateOf("") }
    var endpoint by remember { mutableStateOf("") }
    var modelOpen by remember { mutableStateOf(false) }

    LaunchedEffect(host.status) {
        if (host.status == HostStatus.RUNNING) state.loadModel()
    }
    LaunchedEffect(state.model) {
        endpoint = state.model?.optString("endpoint") ?: endpoint
    }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // ── status ──
        Surface(color = p.surface, shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)) {
            Column(Modifier.fillMaxWidth().padding(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    StatusBadge(host)
                    Spacer(Modifier.weight(1f))
                    if (host.status == HostStatus.RUNNING || host.status == HostStatus.STARTING) {
                        OutlinedButton(onClick = { host.stop() }) { Text("停止宿主") }
                    } else {
                        Button(onClick = { host.start() }) { Text("启动宿主") }
                    }
                    Button(onClick = { host.openChat() }, enabled = host.status == HostStatus.RUNNING) {
                        Text("打开聊天")
                    }
                }
                Spacer(Modifier.height(10.dp))
                val info = host.info
                if (info != null) {
                    Muted(
                        "pid ${info.optLong("pid")} · 版本 ${info.optString("version")} · " +
                            "已运行 ${"%.0f".format(info.optDouble("uptimeS"))}s",
                    )
                    Spacer(Modifier.height(4.dp))
                    Muted("WebUI ${host.webuiUrl}   Hub ${host.hubUrl}")
                } else if (host.lastError.isNotEmpty()) {
                    Text(host.lastError, color = p.error, fontSize = 12.sp)
                }
            }
        }

        // ── host paths ──
        Surface(color = p.surface, shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)) {
            Column(Modifier.fillMaxWidth().padding(16.dp)) {
                SectionTitle("宿主")
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(python, { python = it }, label = { Text("python 可执行文件") }, singleLine = true, modifier = Modifier.width(300.dp))
                    OutlinedTextField(repo, { repo = it }, label = { Text("仓库根目录（含 pot/ 包）") }, singleLine = true, modifier = Modifier.weight(1f))
                }
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Switch(settings.autoRestart, { settings.autoRestart = it; settings.save() })
                    Text("宿主崩溃后自动重启", fontSize = 13.sp)
                    Spacer(Modifier.width(16.dp))
                    Switch(settings.autoStart, { settings.autoStart = it; settings.save() })
                    Text("启动器打开时就拉起宿主", fontSize = 13.sp)
                    Spacer(Modifier.weight(1f))
                    Button(
                        onClick = {
                            settings.python = python.trim()
                            settings.repo = repo.trim()
                            settings.save()
                            state.toast("已保存（下次启动宿主时生效）")
                        },
                    ) { Text("保存路径") }
                }
            }
        }

        // ── model ──
        Surface(color = p.surface, shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)) {
            Column(Modifier.fillMaxWidth().padding(16.dp)) {
                SectionTitle("模型")
                Spacer(Modifier.height(10.dp))
                val model = state.model
                if (model == null) {
                    Muted("宿主运行中才能读取模型配置。")
                } else {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("当前：", color = p.muted, fontSize = 12.sp)
                        Text(model.optString("model"), color = p.fg, fontFamily = FontFamily.Monospace, fontSize = 13.sp)
                        Box {
                            OutlinedButton(onClick = { modelOpen = true }) { Text("换模型") }
                            DropdownMenu(expanded = modelOpen, onDismissRequest = { modelOpen = false }) {
                                val list = model.optJSONArray("models")
                                if (list != null) {
                                    for (i in 0 until list.length()) {
                                        val name = list.optString(i)
                                        DropdownMenuItem(text = { Text(name) }, onClick = {
                                            modelOpen = false
                                            state.switchModel(name)
                                        })
                                    }
                                }
                            }
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    OutlinedTextField(endpoint, { endpoint = it }, label = { Text("接口地址（endpoint）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(apiKey, { apiKey = it }, label = { Text("API Key（留空=不改）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(10.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button(
                            onClick = {
                                state.saveModel(apiKey.ifBlank { null }, endpoint.ifBlank { null }, null)
                                apiKey = ""
                            },
                        ) { Text("保存模型配置") }
                        OutlinedButton(onClick = { state.loadModel() }) { Text("重新读取") }
                    }
                }
            }
        }
    }
}

@Composable
fun StatusBadge(host: HostManager) {
    val p = pal
    val (text, color) =
        when (host.status) {
            HostStatus.RUNNING -> "运行中" to p.primary
            HostStatus.STARTING -> "启动中…" to p.warning
            HostStatus.STOPPING -> "停止中…" to p.warning
            HostStatus.CRASHED -> "已崩溃" to p.error
            HostStatus.STOPPED -> "未运行" to p.muted
        }
    Surface(color = color.copy(alpha = 0.15f), shape = androidx.compose.foundation.shape.RoundedCornerShape(99.dp)) {
        Text(
            "● $text",
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 3.dp),
            color = color,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}
