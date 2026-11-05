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
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import java.io.File
import java.nio.channels.FileChannel
import java.nio.file.StandardOpenOption
import kotlin.system.exitProcess
import kotlinx.coroutines.delay

/** The app mark: the potted-plant emoji (🪴), rasterised ahead of time into
 *  `src/main/resources/icons/` — Chromium renders colour emoji, AWT does not.
 *  Window/taskbar and tray all read it from here, so there is one icon. */
fun appIcon(size: Int = 256): java.awt.Image? =
    runCatching {
        // Top-level functions have no `javaClass`; any app class reaches the same
        // classpath, and the path is absolute, so which one does not matter.
        TrayController::class.java.getResourceAsStream("/icons/pot-icon-$size.png")?.use {
            javax.imageio.ImageIO.read(it)
        }
    }.getOrNull()

/**
 * One launcher per user (handoff 2026-11-05): without this, a second `Pot.exe`
 * doubles the tray icons and races the first over `data/board.sqlite` and
 * `config.json`. `%APPDATA%\Pot\launcher.lock` is held by an OS file lock for the
 * whole process life; APPDATA is per-user, so the lock is per-user too — a
 * machine-wide lock would freeze out every other account for no reason.
 *
 * Fail-open on I/O errors (a broken APPDATA must not stop the launcher from
 * starting), fail-closed only when the lock really is held elsewhere.
 */
private object SingleInstance {
    /** Kept referenced for the process's life: a GC'd channel would close and release the lock. */
    private var held: FileChannel? = null

    fun claim(): Boolean {
        val folder = File(System.getenv("APPDATA") ?: System.getProperty("user.home"), "Pot")
        folder.mkdirs()
        val lockFile = File(folder, "launcher.lock")
        val channel =
            try {
                FileChannel.open(lockFile.toPath(), StandardOpenOption.CREATE, StandardOpenOption.WRITE)
            } catch (e: Exception) {
                Log.warn("lock: open ${lockFile.absolutePath} failed: ${e.message} — starting anyway")
                return true
            }
        val lock =
            try {
                channel.tryLock()
            } catch (e: java.nio.channels.OverlappingFileLockException) {
                // Same JVM already holds it — unreachable while boot runs exactly once
                // (the remember gate above); reachable again only if someone re-introduces
                // a composable-body side effect, and then this stack names the caller.
                channel.close()
                Log.warn("lock: same-JVM re-entry into main()\n" + Throwable().stackTraceToString().trimEnd())
                return false
            } catch (e: Exception) {
                Log.warn("lock: tryLock failed: ${e.message} — starting anyway")
                channel.close()
                return true
            }
        if (lock == null) {
            // Another process holds it (Windows returns null, no exception).
            channel.close()
            return false
        }
        held = channel
        return true
    }
}

/**
 * One-time boot lives inside `remember` on purpose: the `application` lambda is
 * @Composable, so its body RE-RUNS on every recomposition — on this box the host
 * status flip recomposed it ~0.15s after the spawn, re-ran `claim()`, and the
 * second `exitProcess(0)` killed the first instance (re-entry stack arrived on
 * the AWT event thread, 2026-11-05; the handoff's "三条 run" was this, not
 * three instances). `remember` runs the block exactly once per composition.
 */
fun main() = application {
    // Everything below can fail, and the log (plus the default uncaught-exception
    // handler it installs) is what a bug report gets read from.
    val settings =
        remember {
            Log.install()
            if (!SingleInstance.claim()) {
                Log.info("refused: another instance holds the lock")
                exitProcess(0)
            }
            Log.info("settings=${LauncherSettings.settingsFile().absolutePath}")
            // Swing's only surface is the tray popup (see TrayController): the system
            // look makes it sit next to the shell's own menus instead of the Metal theme.
            runCatching { javax.swing.UIManager.setLookAndFeel(javax.swing.UIManager.getSystemLookAndFeelClassName()) }
            LauncherSettings(LauncherSettings.settingsFile()).also { it.load() }.also {
                Log.info("launcher up: python=${it.python} repo=${it.repo} lang=${it.lang.code} autoStart=${it.autoStart} dark=${it.dark}")
            }
        }
    val host = remember { HostManager(settings) }
    val state = remember { PotState(host) }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    var page by remember { mutableStateOf(0) }
    val tray = remember { TrayController() }
    // The Compose window, captured from the content scope: closing requests hide it,
    // and the tray has to be able to bring it back (裁决 24).
    var winRef by remember { mutableStateOf<java.awt.Window?>(null) }
    // Tray 显示窗口 is only useful while the window is hidden (user 2026-11-05:
    // 「仅在窗口未打开时才启用」) — compose state, so the menu re-evaluates on flip.
    var winVisible by remember { mutableStateOf(true) }

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
    // One switch, two halves (spec §74): config.json `ui_lang` is what the WebUI's
    // /lang.js serves, so every change — and every host start, for the case where the
    // language was flipped while the host was down — is pushed there.
    LaunchedEffect(host.status, settings.lang) {
        if (host.status == HostStatus.RUNNING) state.pushLang(settings.lang.code)
    }
    LaunchedEffect(state.snack) {
        val msg = state.snack
        if (msg.isNotEmpty()) {
            state.snack = ""
            snackbar.showSnackbar(msg)
        }
    }
    // 托盘（裁决 24）：进程活着托盘就在——关窗只是把窗口收起来，宿主照跑。
    // 菜单在弹出时读状态与文案，所以这里只需要刷新回调与 tooltip（语言是 key，
    // 否则 tooltip 会停在上一种语言）。
    LaunchedEffect(host.status, settings.lang, winVisible) {
        tray.update(
            running = host.status == HostStatus.RUNNING,
            windowVisible = winVisible,
            onShow = {
                Log.info("tray: show window requested")
                winRef?.let {
                    it.isVisible = true
                    it.toFront()
                    it.requestFocus()
                    winVisible = true
                } ?: Log.warn("tray: no window handle yet")
            },
            onOpenLogs = { Log.openFolder() },
            onOpenChat = { host.openChat() },
            onStart = { host.start() },
            onStop = { host.stop() },
            onExit = {
                Log.info("tray: quit requested")
                host.stopBlocking()
                tray.dispose()
                exitApplication()
            },
        )
    }

    Window(
        // Close-to-tray (裁决 24): hiding keeps the host and the board alive; the
        // only way out is 退出 in the tray menu.
        onCloseRequest = {
            Log.info("window: close requested -> hide to tray (host keeps running)")
            winRef?.isVisible = false
            winVisible = false
        },
        title = "Pot",
        state = rememberWindowState(width = 940.dp, height = 600.dp),
    ) {
        // Taskbar/title-bar mark (the AWT window owns the icon; Compose has no
        // icon parameter on Window), plus the handle the tray needs to un-hide it.
        LaunchedEffect(Unit) {
            winRef = window
            appIcon(64)?.let { window.iconImage = it }
        }
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
            Text("Pot", fontSize = 17.sp, fontWeight = FontWeight.Bold, color = p.fg)
            StatusBadge(host)
            Box(Modifier.padding(horizontal = 10.dp))
            NavPill(Strings.t("看板", "Board"), page == 0) { onPage(0) }
            NavPill(Strings.t("设置", "Settings"), page == 1) { onPage(1) }
            NavPill(Strings.t("关于", "About"), page == 2) { onPage(2) }
            androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
            // 打开聊天 is a constant affordance, not a settings-page errand: it sits
            // left of the language switch, enabled only while the host answers.
            Button(
                onClick = { host.openChat() },
                enabled = host.status == HostStatus.RUNNING,
                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 14.dp),
                modifier = Modifier.height(32.dp),
            ) { Text(Strings.t("打开聊天", "Open chat"), fontSize = 13.sp) }
            Box(Modifier.padding(horizontal = 4.dp))
            LangMenu(settings)
            Box(Modifier.padding(horizontal = 4.dp))
            ThemeToggle(settings.dark) {
                settings.dark = !settings.dark
                settings.save()
            }
        }
    }
}

/**
 * The one language switch (spec §74): the launcher repaints immediately and
 * `LauncherSettings.setLang` saves the code that Main pushes into config.json
 * `ui_lang`, which is where the WebUI's /lang.js reads it.
 *
 * Two options only, so a click TOGGLES them (user 2026-11-05: 「像这种两种备选的，
 * 点一下直接切换就好了」) — a dropdown for a binary choice was one click too many.
 */
@Composable
private fun LangMenu(settings: LauncherSettings) {
    OutlinedButton(
        onClick = {
            val next = if (settings.lang == Lang.ZH) Lang.EN else Lang.ZH
            Log.info("ui: lang toggle -> ${next.code}")
            settings.chooseLang(next)
        },
        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp),
        modifier = Modifier.height(30.dp),
    ) {
        Text(Strings.t("中文", "EN"), fontSize = 12.sp, color = pal.fg)
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
        Text(
            if (dark) Strings.t("深", "Dark") else Strings.t("浅", "Light"),
            fontSize = 11.sp,
            color = pal.muted,
        )
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
        onClick = {
            Log.info("ui: nav $label")
            onClick()
        },
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
