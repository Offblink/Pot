package pot.launcher

import java.awt.Color
import java.awt.Dimension
import java.awt.EventQueue
import java.awt.GraphicsEnvironment
import java.awt.MouseInfo
import java.awt.SystemTray
import java.awt.TrayIcon
import java.awt.event.ActionEvent
import java.awt.event.MouseEvent
import java.awt.event.WindowAdapter
import java.awt.event.WindowEvent
import java.awt.image.BufferedImage
import javax.swing.AbstractAction
import javax.swing.BorderFactory
import javax.swing.BoxLayout
import javax.swing.JButton
import javax.swing.JPanel
import javax.swing.JSeparator
import javax.swing.JWindow
import javax.swing.KeyStroke
import javax.swing.UIManager

/**
 * Tray icon + its menu. Lives as long as the launcher process does (裁决 24:
 * closing the window hides it here, so the icon must outlive both the window and
 * the host). State and strings are read when the menu opens, so nothing has to be
 * rebuilt on a language flip — only the tooltip is refreshed.
 *
 * The menu is NOT an AWT `PopupMenu` (user report 2026-11-04, twice: 「中文失败」):
 * Windows menus are native win32 menus, they draw with the SYSTEM menu font and the
 * JDK's `WMenuItemPeer.setFont` does not change that, so on this English Windows
 * every Chinese label came out as tofu. It is not a Swing `JPopupMenu` either: those
 * live in a window the PopupFactory creates unfocusable, so it never learns that the
 * user clicked elsewhere and stayed on screen as an orphan (「托盘关了还在」). This
 * is our own focusable `JWindow` with flat buttons — one shape that both paints
 * Chinese and closes on the first click anywhere else.
 */
class TrayController {
    private var icon: TrayIcon? = null
    private var popup: JWindow? = null
    private var leaveWatch: javax.swing.Timer? = null

    private var running = false
    private var windowVisible = true
    private var onShow: () -> Unit = {}
    private var onOpenLogs: () -> Unit = {}
    private var onOpenChat: () -> Unit = {}
    private var onStart: () -> Unit = {}
    private var onStop: () -> Unit = {}
    private var onExit: () -> Unit = {}

    fun update(
        running: Boolean,
        windowVisible: Boolean,
        onShow: () -> Unit,
        onOpenLogs: () -> Unit,
        onOpenChat: () -> Unit,
        onStart: () -> Unit,
        onStop: () -> Unit,
        onExit: () -> Unit,
    ) {
        this.running = running
        this.windowVisible = windowVisible
        this.onShow = onShow
        this.onOpenLogs = onOpenLogs
        this.onOpenChat = onOpenChat
        this.onStart = onStart
        this.onStop = onStop
        this.onExit = onExit
        EventQueue.invokeLater {
            val existing = icon
            if (existing != null) { // already up: only the tooltip can change
                existing.toolTip = trayTooltip()
                return@invokeLater
            }
            if (!SystemTray.isSupported()) return@invokeLater
            runCatching {
                val ti = TrayIcon(trayImage(), trayTooltip())
                ti.isImageAutoSize = true
                // Windows delivers the *default action* (double-click) separately from
                // mouse events, and some shells eat the single press; both routes end
                // at the same idempotent "show me the window".
                ti.addActionListener { onShow() }
                ti.addMouseListener(
                    object : java.awt.event.MouseAdapter() {
                        override fun mousePressed(e: MouseEvent) = maybePopup(e)

                        override fun mouseReleased(e: MouseEvent) = maybePopup(e)
                    },
                )
                SystemTray.getSystemTray().add(ti)
                icon = ti
            }
        }
    }

    fun dispose() {
        closePopup()
        EventQueue.invokeLater {
            icon?.let { runCatching { SystemTray.getSystemTray().remove(it) } }
            icon = null
        }
    }

    /** The one place an open menu dies; safe to call at any time. */
    private fun closePopup() {
        leaveWatch?.stop()
        leaveWatch = null
        val open = popup
        popup = null
        runCatching { if (open != null && open.isDisplayable) open.dispose() }
    }

    private fun maybePopup(e: MouseEvent) {
        if (e.isPopupTrigger) {
            EventQueue.invokeLater { showMenu() }
        } else if (e.button == MouseEvent.BUTTON1) {
            // Left click brings the window back — with close-to-tray it is the only
            // way home when the board is hidden; 打开聊天 lives in the menu.
            onShow()
        }
    }

    private fun showMenu() {
        closePopup()

        val panel =
            JPanel().apply {
                layout = BoxLayout(this, BoxLayout.Y_AXIS)
                background = UIManager.getColor("PopupMenu.background") ?: Color.WHITE
                border =
                    BorderFactory.createLineBorder(
                        UIManager.getColor("PopupMenu.borderColor") ?: Color(0xC8, 0xC8, 0xC8),
                    )
            }

        fun add(
            label: String,
            enabled: Boolean = true,
            action: () -> Unit,
        ) {
            val button = menuItem(label, enabled, action)
            button.alignmentX = 0f
            button.maximumSize = Dimension(Int.MAX_VALUE, button.preferredSize.height)
            panel.add(button)
        }

        // Only useful while the window is hidden (user 2026-11-05: 仅在窗口未打开时才启用).
        add(potString("显示窗口", "Show window"), enabled = !windowVisible) { onShow() }
        // The only log entry (user 2026-11-05): it used to live on the Settings page.
        add(potString("打开日志", "Open logs")) { onOpenLogs() }
        add(potString("打开聊天", "Open chat"), running) { onOpenChat() }
        if (running) {
            add(potString("停止宿主", "Stop host")) { onStop() }
        } else {
            add(potString("启动宿主", "Start host")) { onStart() }
        }
        panel.add(JSeparator().apply { maximumSize = Dimension(Int.MAX_VALUE, height) })
        add(potString("退出", "Quit")) { onExit() }

        val win =
            JWindow().apply {
                isAlwaysOnTop = true
                contentPane.add(panel)
                pack()
            }

        val at = MouseInfo.getPointerInfo()?.location ?: return
        // Pop UP from the click (user: 「显示在任务栏上面，不要盖住」): the icon sits
        // in the tray, so showing at the pointer drops the menu over the taskbar.
        // Work area = screen minus taskbar; clamp inside it.
        val work = GraphicsEnvironment.getLocalGraphicsEnvironment().maximumWindowBounds
        val x = at.x.coerceIn(work.x, (work.x + work.width - win.width).coerceAtLeast(work.x))
        val y = (at.y - win.height).coerceAtLeast(work.y)
        win.setLocation(x, y)

        // The whole point of owning the window: it really takes focus, so clicking
        // anywhere else (another app, the desktop, the shell) closes the menu.
        win.addWindowFocusListener(
            object : WindowAdapter() {
                // Only a real focus LOSS closes it: `windowDeactivated` also fires
                // when the shell's flyout re-activates itself right after our window
                // shows, which killed the menu on the spot (seen on the box).
                override fun windowLostFocus(e: WindowEvent) = closePopup()
            },
        )
        win.rootPane.inputMap.put(KeyStroke.getKeyStroke("ESCAPE"), "pot-close")
        win.rootPane.actionMap.put(
            "pot-close",
            object : AbstractAction() {
                override fun actionPerformed(e: ActionEvent) = closePopup()
            },
        )

        popup = win
        win.isVisible = true
        win.toFront()
        win.requestFocus()
        watchPointer(win)
    }

    /**
     * Close once the pointer leaves the menu. A window shown in response to a tray
     * click does not reliably become the FOREGROUND window on Windows (the shell owns
     * the input that opened the flyout), so a focus-loss listener never fires — that
     * is why the menu kept sitting there (user report, twice). Pointer motion needs
     * no activation: if the cursor is not over the menu, the menu is gone.
     */
    private fun watchPointer(win: JWindow) {
        leaveWatch =
            javax.swing.Timer(150) {
                val open = popup
                if (open == null || !open.isDisplayable) {
                    leaveWatch?.stop()
                    return@Timer
                }
                val at = MouseInfo.getPointerInfo()?.location
                if (at != null) {
                    // Grown by the gap between the click point and the menu edge, so
                    // the pointer resting where it opened is still "inside".
                    val zone = open.bounds.apply { grow(8, 8) }
                    if (!zone.contains(at)) closePopup()
                }
            }.apply {
                initialDelay = 700 // the click that opened it must not count
                start()
            }
    }

    private fun menuItem(
        label: String,
        enabled: Boolean,
        action: () -> Unit,
    ): JButton {
        val hover = UIManager.getColor("MenuItem.selectionBackground") ?: Color(0xDCE8F6)
        val button =
            JButton(label).apply {
                isContentAreaFilled = false
                isBorderPainted = false
                isFocusPainted = false
                horizontalAlignment = javax.swing.SwingConstants.LEFT
                margin = java.awt.Insets(3, 16, 3, 32)
                font = UIManager.getFont("MenuItem.font") ?: font
                isEnabled = enabled
            }
        button.addMouseListener(
            object : java.awt.event.MouseAdapter() {
                override fun mouseEntered(e: MouseEvent) {
                    if (!button.isEnabled) return
                    button.background = hover
                    button.isContentAreaFilled = true
                }

                override fun mouseExited(e: MouseEvent) {
                    button.isContentAreaFilled = false
                }
            },
        )
        button.addActionListener {
            closePopup()
            action()
        }
        return button
    }

    private fun trayTooltip(): String =
        potString("Pot — 角色/设置/打开聊天", "Pot — roles / settings / open chat")

    private fun potString(
        zh: String,
        en: String,
    ): String = Strings.t(zh, en)

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
        g.color = Color(0x4A, 0xDE, 0x80)
        g.fillOval(0, 0, 15, 15)
        g.color = Color(0x06, 0x06, 0x0A)
        g.font = java.awt.Font("Segoe UI", java.awt.Font.BOLD, 11)
        g.drawString("P", 4, 12)
        g.dispose()
        return img
    }
}
