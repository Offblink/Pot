package pot.launcher

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import java.awt.EventQueue
import java.awt.MenuItem
import java.awt.PopupMenu
import java.awt.SystemTray
import java.awt.TrayIcon
import java.awt.image.BufferedImage
import kotlinx.coroutines.delay

fun main() = application {
    val settings = remember { LauncherSettings(LauncherSettings.settingsFile()).also { it.load() } }
    val host = remember { HostManager(settings) }
    val state = remember { PotState(host) }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    var page by remember { mutableStateOf(0) }
    val tray = remember { TrayController() }

    LaunchedEffect(Unit) {
        if (settings.autoStart) host.start()
    }
    // One board poller for the whole app: cheap (loopback JSON), and the
    // lease countdowns/statuses stay honest without per-page plumbing.
    LaunchedEffect(Unit) {
        while (true) {
            state.refreshBoard()
            delay(3000)
        }
    }
    LaunchedEffect(host.status) {
        if (host.status == HostStatus.RUNNING) state.loadModel()
    }
    LaunchedEffect(state.snack) {
        val msg = state.snack
        if (msg.isNotEmpty()) {
            state.snack = ""
            snackbar.showSnackbar(msg)
        }
    }
    // 托盘语义（裁决 Q5）：host 运行才有托盘；点托盘菜单进 WebUI / 停 host / 退出。
    LaunchedEffect(host.status, host.webuiUrl) {
        tray.update(
            active = host.status == HostStatus.RUNNING || host.status == HostStatus.STARTING,
            running = host.status == HostStatus.RUNNING,
            onOpenChat = { host.openChat() },
            onStart = { host.start() },
            onStop = { host.stop() },
            onExit = {
                host.stopBlocking()
                tray.dispose()
                exitApplication()
            },
        )
    }

    Window(
        onCloseRequest = {
            host.stopBlocking()
            tray.dispose()
            exitApplication()
        },
        title = "Pot",
        state = rememberWindowState(width = 940.dp, height = 600.dp),
    ) {
        PotTheme(settings.dark) {
            Scaffold(
                snackbarHost = { SnackbarHost(snackbar) },
                topBar = { TopBar(host, settings, page) { page = it } },
            ) { insets ->
                Box(Modifier.padding(insets).fillMaxSize()) {
                    when (page) {
                        0 -> BoardPage(state, settings)
                        1 -> SettingsPage(state, host, settings)
                        else -> AboutPage(host)
                    }
                }
            }
        }
    }
    @Suppress("UNUSED_EXPRESSION") scope
}

@Composable
private fun TopBar(
    host: HostManager,
    settings: LauncherSettings,
    page: Int,
    onPage: (Int) -> Unit,
) {
    val p = pal
    Surface(color = p.surface) {
        Row(
            Modifier.fillMaxWidth().height(56.dp).padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Box(Modifier.background(p.primary, RoundedCornerShape(99.dp)).padding(6.dp))
            Text("Pot", fontSize = 17.sp, fontWeight = FontWeight.Bold, color = p.fg)
            StatusBadge(host)
            Box(Modifier.padding(horizontal = 10.dp))
            NavPill("看板", page == 0) { onPage(0) }
            NavPill("设置", page == 1) { onPage(1) }
            NavPill("关于", page == 2) { onPage(2) }
            androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
            ThemeToggle(settings.dark) {
                settings.dark = !settings.dark
                settings.save()
            }
        }
    }
}

/**
 * Top-right theme switch: gradient track (dawn → night) with a spring knob.
 * Compose cannot tween a gradient itself, so the two stop colors animate
 * independently while the knob slides — one continuous gradient transition.
 */
@Composable
private fun ThemeToggle(
    dark: Boolean,
    onToggle: () -> Unit,
) {
    val warm = pal.warning
    val trackA by androidx.compose.animation.animateColorAsState(
        if (dark) androidx.compose.ui.graphics.Color(0xFF3B2A6B) else warm,
        animationSpec = androidx.compose.animation.core.tween(450),
        label = "trackA",
    )
    val trackB by androidx.compose.animation.animateColorAsState(
        if (dark) androidx.compose.ui.graphics.Color(0xFF1E1B4B) else pal.primary,
        animationSpec = androidx.compose.animation.core.tween(450),
        label = "trackB",
    )
    val knobX by androidx.compose.animation.core.animateDpAsState(
        targetValue = if (dark) 34.dp else 2.dp,
        animationSpec =
            androidx.compose.animation.core.spring(
                dampingRatio = 0.55f,
                stiffness = 600f,
            ),
        label = "knob",
    )
    val sunColor = androidx.compose.ui.graphics.Color(0xFFB45309)
    val moonColor = androidx.compose.ui.graphics.Color(0xFF312E81)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(
            Modifier
                .width(58.dp)
                .height(26.dp)
                .clip(RoundedCornerShape(99.dp))
                .background(
                    androidx.compose.ui.graphics.Brush.horizontalGradient(listOf(trackA, trackB)),
                )
                .border(1.dp, pal.outline, RoundedCornerShape(99.dp))
                .clickable(onClick = onToggle),
        ) {
            // The inactive icon uses the SAME 22dp box + 12sp glyph as the knob
            // icon (only the alpha differs): different box/font sizes shifted
            // the glyph's optical centre (user report).
            Box(Modifier.offset(x = 2.dp, y = 2.dp).size(22.dp), contentAlignment = Alignment.Center) {
                Text(
                    "☀",
                    fontSize = 12.sp,
                    color = androidx.compose.ui.graphics.Color.White.copy(alpha = if (dark) 0.85f else 0f),
                )
            }
            Box(Modifier.offset(x = 34.dp, y = 2.dp).size(22.dp), contentAlignment = Alignment.Center) {
                Text(
                    "☾",
                    fontSize = 12.sp,
                    color = androidx.compose.ui.graphics.Color.White.copy(alpha = if (dark) 0f else 0.85f),
                )
            }
            // … and the active icon rides centered INSIDE the knob (fixed-size
            // Centered box — the previous baseline-offset Text sat low). The
            // knob gets a shadow + hairline border so white-on-white never
            // hides the glyph (user report: 月亮与滑块都是白色不明显).
            Box(
                Modifier
                    .offset(x = knobX, y = 2.dp)
                    .size(22.dp)
                    .shadow(3.dp, RoundedCornerShape(99.dp))
                    .background(androidx.compose.ui.graphics.Color.White, RoundedCornerShape(99.dp))
                    .border(0.5.dp, pal.muted.copy(alpha = 0.45f), RoundedCornerShape(99.dp)),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    if (dark) "☾" else "☀",
                    fontSize = 12.sp,
                    color = if (dark) moonColor else sunColor,
                )
            }
        }
        Text(if (dark) "深" else "浅", fontSize = 11.sp, color = pal.muted)
    }
}

@Composable
private fun NavPill(
    label: String,
    active: Boolean,
    onClick: () -> Unit,
) {
    val p = pal
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(9.dp),
        color = if (active) p.surfaceVariant else androidx.compose.ui.graphics.Color.Transparent,
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            color = if (active) p.fg else p.muted,
            fontSize = 13.sp,
            fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

/** AWT tray: exists only while the host runs (spec 裁决 Q5), rebuilt on each state change. */
class TrayController {
    private var icon: TrayIcon? = null

    fun update(
        active: Boolean,
        running: Boolean,
        onOpenChat: () -> Unit,
        onStart: () -> Unit,
        onStop: () -> Unit,
        onExit: () -> Unit,
    ) {
        EventQueue.invokeLater {
            icon?.let {
                runCatching { SystemTray.getSystemTray().remove(it) }
                icon = null
            }
            if (!active || !SystemTray.isSupported()) return@invokeLater
            runCatching {
                val menu = PopupMenu()
                menu.add(
                    MenuItem("打开聊天").apply {
                        isEnabled = running
                        addActionListener { onOpenChat() }
                    },
                )
                menu.add(
                    MenuItem(if (running) "停止宿主" else "启动宿主").apply {
                        addActionListener { if (running) onStop() else onStart() }
                    },
                )
                menu.addSeparator()
                menu.add(MenuItem("退出").apply { addActionListener { onExit() } })
                val ti = TrayIcon(trayImage(), "Pot — 看板/设置/打开聊天", menu)
                ti.isImageAutoSize = true
                SystemTray.getSystemTray().add(ti)
                icon = ti
            }
        }
    }

    fun dispose() {
        EventQueue.invokeLater {
            icon?.let { runCatching { SystemTray.getSystemTray().remove(it) } }
            icon = null
        }
    }

    /** 16×16 green dot with a white P — no resource file needed. */
    private fun trayImage(): BufferedImage {
        val img = BufferedImage(16, 16, BufferedImage.TYPE_INT_ARGB)
        val g = img.createGraphics()
        g.setRenderingHint(
            java.awt.RenderingHints.KEY_ANTIALIASING,
            java.awt.RenderingHints.VALUE_ANTIALIAS_ON,
        )
        g.color = java.awt.Color(0x4A, 0xDE, 0x80)
        g.fillOval(0, 0, 15, 15)
        g.color = java.awt.Color(0x06, 0x06, 0x0A)
        g.font = java.awt.Font("Segoe UI", java.awt.Font.BOLD, 11)
        g.drawString("P", 4, 12)
        g.dispose()
        return img
    }
}
