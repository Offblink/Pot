package pot.launcher

import java.awt.EventQueue
import java.awt.SystemTray
import java.awt.TrayIcon
import java.awt.image.BufferedImage

/**
 * Tray icon + its menu. Exists only while the host runs (spec 裁决 Q5) and is
 * rebuilt on every state/language change.
 *
 * The menu is a SWING popup, not an AWT `PopupMenu` (user report 2026-11-04, twice:
 * 「中文失败」). Windows menus are native win32 menus and draw their labels with the
 * SYSTEM menu font; the JDK's `WMenuItemPeer.setFont` does not change that, so on
 * this English Windows every Chinese label came out as tofu boxes even after
 * `MenuItem.font` was set to Microsoft YaHei. Java2D has real font fallback, so a
 * Swing popup is the one shape that renders both languages.
 */
class TrayController {
    private var icon: TrayIcon? = null

    private var running = false
    private var onOpenChat: () -> Unit = {}
    private var onStart: () -> Unit = {}
    private var onStop: () -> Unit = {}
    private var onExit: () -> Unit = {}

    /** Owner for a heavyweight popup: a 1×1 window with no taskbar entry. */
    private val popupOwner: javax.swing.JWindow by lazy {
        javax.swing.JWindow().apply {
            setBounds(0, 0, 1, 1)
            isVisible = true
        }
    }

    fun update(
        active: Boolean,
        running: Boolean,
        onOpenChat: () -> Unit,
        onStart: () -> Unit,
        onStop: () -> Unit,
        onExit: () -> Unit,
    ) {
        this.running = running
        this.onOpenChat = onOpenChat
        this.onStart = onStart
        this.onStop = onStop
        this.onExit = onExit
        EventQueue.invokeLater {
            icon?.let {
                runCatching { SystemTray.getSystemTray().remove(it) }
                icon = null
            }
            if (!active || !SystemTray.isSupported()) return@invokeLater
            runCatching {
                val ti =
                    TrayIcon(
                        trayImage(),
                        Strings.t("Pot — 看板/设置/打开聊天", "Pot — board / settings / open chat"),
                    )
                ti.isImageAutoSize = true
                ti.addMouseListener(
                    object : java.awt.event.MouseAdapter() {
                        override fun mousePressed(e: java.awt.event.MouseEvent) = maybePopup(e)

                        override fun mouseReleased(e: java.awt.event.MouseEvent) = maybePopup(e)
                    },
                )
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

    private fun maybePopup(e: java.awt.event.MouseEvent) {
        if (e.isPopupTrigger) {
            EventQueue.invokeLater { showMenu() }
        } else if (e.button == java.awt.event.MouseEvent.BUTTON1 && running) {
            onOpenChat()
        }
    }

    private fun showMenu() {
        val menu = javax.swing.JPopupMenu()
        // A heavyweight popup can float above the taskbar; a lightweight one would
        // be clipped to the (invisible, 1×1) owner.
        menu.isLightWeightPopupEnabled = false

        fun item(
            label: String,
            enabled: Boolean = true,
            action: () -> Unit,
        ) {
            val entry = javax.swing.JMenuItem(label)
            entry.isEnabled = enabled
            entry.addActionListener {
                menu.isVisible = false
                action()
            }
            menu.add(entry)
        }

        item(Strings.t("打开聊天", "Open chat"), running) { onOpenChat() }
        if (running) {
            item(Strings.t("停止宿主", "Stop host")) { onStop() }
        } else {
            item(Strings.t("启动宿主", "Start host")) { onStart() }
        }
        menu.addSeparator()
        item(Strings.t("退出", "Quit")) { onExit() }

        val at = java.awt.MouseInfo.getPointerInfo()?.location ?: return
        // Pop UP from the click (user, 2026-11-04: 「显示在任务栏上面，不要盖住」):
        // the icon sits in the tray, so showing at the pointer drops the menu over
        // the taskbar. Work area = screen minus taskbar; clamp inside it.
        val work = java.awt.GraphicsEnvironment.getLocalGraphicsEnvironment().maximumWindowBounds
        val size = menu.preferredSize
        val x = at.x.coerceIn(work.x, (work.x + work.width - size.width).coerceAtLeast(work.x))
        val y = (at.y - size.height).coerceAtLeast(work.y)
        menu.show(popupOwner, x, y)
        // A popup that never takes focus cannot learn that the user clicked
        // somewhere else, so it stayed on screen after the flyout closed (user
        // report 2026-11-04: 「出现托盘关了还在的情况，我想点击其他区域关闭的」).
        // Take focus for the popup window and close on its loss.
        (javax.swing.SwingUtilities.getWindowAncestor(menu) as? java.awt.Window)?.let { w ->
            w.setFocusableWindowState(true)
            w.addWindowFocusListener(
                object : java.awt.event.WindowAdapter() {
                    override fun windowLostFocus(e: java.awt.event.WindowEvent) {
                        menu.isVisible = false
                    }
                },
            )
            w.requestFocus()
        }
    }

    /** The app mark, 32px (Windows trays scale it down; auto-size keeps the ratio). */
    private fun trayImage(): BufferedImage {
        val icon = appIcon(32)
        if (icon is BufferedImage) return icon
        // Fallback: a green dot with a white P, so a missing resource is not a
        // tray with no icon at all.
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
