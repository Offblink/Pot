package pot.launcher

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.File
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/** Where the launcher keeps its own state (host paths, restart policy, theme). */
class LauncherSettings(
    val file: File,
) {
    var python by mutableStateOf("python")
    var repo by mutableStateOf(defaultRepo())
    var autoRestart by mutableStateOf(true)
    var autoStart by mutableStateOf(true)
    var dark by mutableStateOf(false)

    /** Launcher language; the same switch writes config.json `ui_lang` (see Main). */
    var lang by mutableStateOf(Lang.ZH)
        private set

    /** One switch, two halves: the launcher repaints now, the WebUI follows on reload. */
    fun chooseLang(value: Lang) {
        lang = value
        Strings.lang = value
        save()
    }

    fun load() {
        if (!file.isFile) {
            Strings.lang = lang
            return
        }
        runCatching {
            val j = JSONObject(file.readText(Charsets.UTF_8))
            python = j.optString("python", python)
            repo = j.optString("repo", repo)
            autoRestart = j.optBoolean("autoRestart", autoRestart)
            autoStart = j.optBoolean("autoStart", autoStart)
            dark = j.optBoolean("dark", dark)
            lang = Lang.of(j.optString("lang", lang.code))
        }
        Strings.lang = lang
    }

    fun save() {
        runCatching {
            file.parentFile?.mkdirs()
            val j =
                JSONObject()
                    .put("python", python)
                    .put("repo", repo)
                    .put("autoRestart", autoRestart)
                    .put("autoStart", autoStart)
                    .put("dark", dark)
                    .put("lang", lang.code)
            file.writeText(j.toString(2), Charsets.UTF_8)
        }
    }

    companion object {
        fun settingsFile(): File {
            val base = System.getenv("APPDATA") ?: System.getProperty("user.home")
            return File(base, "Pot/launcher.json")
        }

        /** Running from source (`gradle run`) puts us one level under the repo root. */
        fun defaultRepo(): String = File(System.getProperty("user.dir")).parent ?: "."
    }
}

enum class HostStatus { STOPPED, STARTING, RUNNING, CRASHED, STOPPING }

/**
 * The Python host's lifecycle (spec §4.1 方案 A): spawn `python -m pot --web`,
 * parse the two URL lines it prints, poll `/api/host/status`, and keep the
 * process tree killable. A crash restarts it with backoff while the setting
 * allows it — the launcher survives the host, that is the point of the design.
 */
class HostManager(
    private val settings: LauncherSettings,
) {
    var status by mutableStateOf(HostStatus.STOPPED)
        private set
    var webuiUrl by mutableStateOf("")
        private set
    var hubUrl by mutableStateOf("")
        private set
    var info by mutableStateOf<JSONObject?>(null)
        private set
    var lastError by mutableStateOf("")
        private set

    val token: String = readToken()

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var process: Process? = null
    private var poll: Job? = null
    private var starts = 0
    private var stopping = false

    // ── the loopback calls (token attached the way the hub reads it) ──

    fun hubGet(path: String): JSONObject {
        val sep = if ('?' in path) '&' else '?'
        return Api.get("$hubUrl$path$sep" + "token=" + enc(token))
    }

    fun hubPost(
        path: String,
        body: JSONObject,
    ): JSONObject {
        body.put("token", token)
        return Api.post("$hubUrl$path", body)
    }

    fun webuiGet(path: String): JSONObject = Api.get("$webuiUrl$path")

    fun webuiPost(
        path: String,
        body: JSONObject,
    ): JSONObject = Api.post("$webuiUrl$path", body)

    // ── lifecycle ──

    fun start() {
        if (status == HostStatus.STARTING || status == HostStatus.RUNNING) return
        stopping = false
        status = HostStatus.STARTING
        Log.info("host: start requested (python=${settings.python}, repo=${settings.repo})")
        lastError = ""
        webuiUrl = ""
        hubUrl = ""
        scope.launch {
            while (true) {
                val code =
                    runCatching { runProcess() }.getOrElse { e ->
                        lastError = e.message ?: Strings.t("启动失败", "Failed to start")
                        -1
                    }
                if (stopping) {
                    Log.info("host: exited (code=$code) after a stop request")
                    status = HostStatus.STOPPED
                    return@launch
                }
                Log.warn("host: exited (code=$code)${if (lastError.isEmpty()) "" else " — $lastError"}")
                status = HostStatus.CRASHED
                poll?.cancel()
                if (lastError.isEmpty()) {
                    lastError = Strings.t("宿主退出 (code=$code)", "host exited (code=$code)")
                }
                if (!settings.autoRestart) return@launch
                starts += 1
                if (starts > MAX_RESTARTS) {
                    lastError =
                        Strings.t(
                            "连续启动失败 $MAX_RESTARTS 次，已停止自动重启",
                            "$MAX_RESTARTS failed starts in a row — auto-restart stopped",
                        )
                    return@launch
                }
                delay(starts * 1000L)
                status = HostStatus.STARTING
                webuiUrl = ""
                hubUrl = ""
            }
        }
    }

    fun stop() {
        stopping = true
        poll?.cancel()
        status = HostStatus.STOPPING
        val p = process
        if (p != null && p.isAlive) {
            killTree(p.pid())
        } else {
            status = HostStatus.STOPPED
        }
    }

    /** Window close: kill synchronously enough that no host survives the app. */
    fun stopBlocking(timeoutMs: Long = 3000) {
        stopping = true
        poll?.cancel()
        val p = process
        if (p != null && p.isAlive) {
            killTree(p.pid())
            runCatching { p.waitFor(timeoutMs, TimeUnit.MILLISECONDS) }
        }
        status = HostStatus.STOPPED
    }

    fun openChat() {
        if (webuiUrl.isNotEmpty()) {
            java.awt.Desktop.getDesktop().browse(java.net.URI.create("$webuiUrl/?t=" + enc(token)))
        }
    }

    // ── internals ──

    /** Blocking: spawn, drain stdout for the URLs, wait for exit. */
    private fun runProcess(): Int {
        val pb =
            ProcessBuilder(settings.python, "-m", "pot", "--web")
                .directory(File(settings.repo))
                .redirectErrorStream(true)
        // Piped stdout is block-buffered in CPython: without this the two URL
        // lines (the whole subprocess handshake) sit in the pipe buffer and
        // the launcher never leaves STARTING (real-machine finding).
        pb.environment()["PYTHONUNBUFFERED"] = "1"
        pb.environment()["PYTHONIOENCODING"] = "utf-8"
        // "Open chat" is the launcher's own action — the host must not grab
        // the desktop by opening a browser on every spawn.
        pb.environment()["POT_NO_BROWSER"] = "1"
        Log.info("host: spawning ${settings.python} -m pot --web")
        val p = pb.start()
        process = p
        Log.info("host: pid=${p.pid()}")
        val drainer =
            Thread {
                p.inputStream.bufferedReader(Charsets.UTF_8).useLines { lines ->
                    lines.forEach { line ->
                        Regex("Pot WebUI: (\\S+)").find(line)?.let { m ->
                            webuiUrl = m.groupValues[1]
                        }
                        Regex("Pot Hub: (\\S+)").find(line)?.let { m ->
                            hubUrl = m.groupValues[1]
                        }
                        if (webuiUrl.isNotEmpty() && hubUrl.isNotEmpty() && status != HostStatus.RUNNING) {
                            Log.info("host: up (webui=$webuiUrl hub=$hubUrl)")
                            status = HostStatus.RUNNING
                            lastError = ""
                            beginPolling()
                        }
                    }
                }
            }
        drainer.isDaemon = true
        drainer.start()
        return p.waitFor()
    }

    private fun beginPolling() {
        poll?.cancel()
        poll =
            scope.launch {
                var fails = 0
                while (isActive) {
                    try {
                        val st = Api.get("$hubUrl/api/host/status?token=" + enc(token))
                        info = st
                        fails = 0
                        // A host that has been up a while is a stable start: forget crash history.
                        if (st.optDouble("uptimeS", 0.0) > 5.0) starts = 0
                        delay(POLL_MS)
                    } catch (e: Exception) {
                        fails += 1
                        if (fails >= 3 && status == HostStatus.RUNNING) {
                            Log.warn("host: lost the status poll — ${e.message ?: "unknown"}")
                            lastError =
                                Strings.t("失去与宿主连接：", "Lost the connection to the host: ") +
                                    (e.message ?: "unknown")
                            process?.let { if (it.isAlive) killTree(it.pid()) }
                            break
                        }
                        delay(1500)
                    }
                }
            }
    }

    private fun killTree(pid: Long) {
        Log.info("host: kill tree $pid")
        runCatching {
            ProcessBuilder("taskkill", "/T", "/F", "/PID", pid.toString())
                .redirectErrorStream(true)
                .start()
                .waitFor(10, TimeUnit.SECONDS)
        }
        runCatching { process?.destroyForcibly() }
    }

    companion object {
        private const val POLL_MS = 2000L
        private const val MAX_RESTARTS = 5

        fun enc(s: String): String = URLEncoder.encode(s, Charsets.UTF_8)

        fun readToken(): String =
            runCatching {
                File(System.getProperty("user.home"), ".pot/webui_token").readText(Charsets.UTF_8).trim()
            }.getOrDefault("")
    }
}
