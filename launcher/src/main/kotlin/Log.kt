package pot.launcher

import java.io.File
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * The launcher's log — one file per day under `%APPDATA%\Pot\logs\`, the same
 * shape the Python host writes into `logs/pot-YYYYMMDD.log`. The host has had a
 * log from the start; the launcher had none, so a silent exit (the tray episode,
 * 2026-11-05) left no evidence at all.
 *
 * Keep the format boring: `HH:mm:ss.SSS LEVEL message`, flushed on every line
 * (a crash must not eat the last lines), one writer thread at a time.
 */
object Log {
    private val fmt: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm:ss.SSS")
    private val stamp: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
    private val lock = Any()

    /** Set once by [install]; null until then (early calls still go to stdout). */
    private var file: File? = null

    fun install(): File {
        val folder = File(System.getenv("APPDATA") ?: System.getProperty("user.home"), "Pot/logs")
        folder.mkdirs()
        prune(folder)
        val target = File(folder, "launcher-${LocalDate.now().format(DateTimeFormatter.BASIC_ISO_DATE)}.log")
        file = target
        val header =
            "--- run ${LocalDateTime.now().format(stamp)} pot ${POT_VERSION} " +
                "| java ${System.getProperty("java.version")} | ${System.getProperty("os.name")} " +
                "${System.getProperty("os.version")} | user.dir=${System.getProperty("user.dir")}"
        write("INFO", header)
        // The reason this exists: anything that ends the process must leave a trace.
        Thread.setDefaultUncaughtExceptionHandler { thread, err ->
            error("uncaught in ${thread.name}", err)
        }
        return target
    }

    fun path(): String = file?.absolutePath ?: "(log not installed)"

    fun info(msg: String) = write("INFO", msg)

    fun warn(msg: String) = write("WARN", msg)

    fun error(msg: String, err: Throwable? = null) {
        write("ERROR", msg)
        err?.let { write("ERROR", it.stackTraceToString().trimEnd()) }
    }

    /** Open the log folder in Explorer (Settings page button). */
    fun openFolder() {
        runCatching {
            val folder = file?.parentFile ?: return
            java.awt.Desktop.getDesktop().open(folder)
        }.onFailure { error("open log folder failed", it) }
    }

    private fun write(level: String, message: String) {
        val line = "${LocalDateTime.now().format(fmt)} $level $message"
        synchronized(lock) {
            println(line) // gradle run / console builds still see it live
            val target = file ?: return
            runCatching { target.appendText(line + "\n") }
        }
    }

    /** Keep a fortnight, like the host does. */
    private fun prune(folder: File) {
        val cutoff = LocalDate.now().minusDays(14)
        folder.listFiles { f -> f.isFile && f.name.startsWith("launcher-") && f.name.endsWith(".log") }
            ?.forEach { f ->
                val day = f.name.removePrefix("launcher-").removeSuffix(".log")
                runCatching {
                    if (LocalDate.parse(day, DateTimeFormatter.BASIC_ISO_DATE).isBefore(cutoff)) f.delete()
                }
            }
    }
}
