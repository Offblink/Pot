package pot.launcher

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import org.json.JSONObject

/** (status, Chinese, English) — the label is resolved at paint time, not once at load. */
private val COLUMNS =
    listOf(
        Triple("backlog", "待规划", "Backlog"),
        Triple("todo", "待办", "To do"),
        Triple("doing", "进行中", "Doing"),
        Triple("review", "待验收", "Review"),
        Triple("done", "已完成", "Done"),
        Triple("blocked", "受阻", "Blocked"),
    )

private val PRIORITIES = listOf("urgent", "normal", "low")

/**
 * A column shows at most this many cards (newest first); the rest sit behind
 * the footer's 归档 link (user 2026-11-05: columns grew until scrolling hurt).
 * A cap on the VIEW only — cards are audit records and `deleted` is a soft delete,
 * so nothing is ever removed here.
 */
private const val VISIBLE_PER_COLUMN = 12

private fun updatedAt(card: JSONObject): Long = card.optLong("updatedAt", 0L)

/** `MM-dd HH:mm` for archive rows, comments and the detail's "updated" line. */
private val stampFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("MM-dd HH:mm")

private fun stamp(epochSeconds: Long): String =
    Instant.ofEpochSecond(epochSeconds).atZone(ZoneId.systemDefault()).format(stampFmt)

/** Archive groups: 今天 / 昨天 / 本周 (Monday-based) / 更早. */
private fun dateBucket(epochSeconds: Long): Int {
    val date = Instant.ofEpochSecond(epochSeconds).atZone(ZoneId.systemDefault()).toLocalDate()
    val today = LocalDate.now()
    return when {
        date == today -> 0
        date == today.minusDays(1) -> 1
        !date.isBefore(today.with(DayOfWeek.MONDAY)) -> 2
        else -> 3
    }
}

private fun bucketLabel(bucket: Int): String =
    when (bucket) {
        0 -> Strings.t("今天", "Today")
        1 -> Strings.t("昨天", "Yesterday")
        2 -> Strings.t("本周", "This week")
        else -> Strings.t("更早", "Earlier")
    }

private fun cardLabels(card: JSONObject): List<String> {
    val arr = card.optJSONArray("labels") ?: return emptyList()
    return (0 until arr.length()).map { arr.optString(it) }
}

private fun statusLabel(status: String): String =
    COLUMNS.firstOrNull { it.first == status }?.let { Strings.t(it.second, it.third) } ?: status

/** 看板页（spec §4.2）: six columns + the role table; every human action lives here. */
@Composable
fun BoardPage(
    state: PotState,
    settings: LauncherSettings,
) {
    var tab by remember { mutableStateOf(0) }
    var showCreate by remember { mutableStateOf(false) }
    val p = pal

    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            TabPill(Strings.t("看板", "Board"), tab == 0) { tab = 0 }
            TabPill(Strings.t("角色", "Roles"), tab == 1) { tab = 1 }
            Spacer(Modifier.weight(1f))
            Muted(
                if (Strings.lang == Lang.EN) {
                    val n = state.cards.count { !it.optBoolean("deleted") }
                    if (n == 1) "1 card" else "$n cards"
                } else {
                    "${state.cards.count { !it.optBoolean("deleted") }} 张卡"
                },
            )
            Button(onClick = { showCreate = true }, enabled = state.host.status == HostStatus.RUNNING) {
                Text(Strings.t("＋ 新建卡", "+ New card"))
            }
        }
        if (tab == 0) {
            BoardColumns(state)
        } else {
            RolesPanel(state)
        }
    }

    if (showCreate) {
        CreateCardDialog(state) { showCreate = false }
    }
    @Suppress("UNUSED_EXPRESSION") p
}

@Composable
private fun TabPill(
    label: String,
    active: Boolean,
    onClick: () -> Unit,
) {
    val p = pal
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(9.dp),
        color = if (active) p.surfaceVariant else Color.Transparent,
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

@Composable
private fun BoardColumns(state: PotState) {
    val p = pal
    var archiveStatus by remember { mutableStateOf<String?>(null) }
    Row(
        Modifier.fillMaxSize().padding(horizontal = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        COLUMNS.forEach { (status, zh, en) ->
            // Newest first (user 2026-11-05: 「卡片是从上向下累积的」— the card being
            // worked on now must be the one in view), then capped at the freshest 12.
            val cards =
                state.cards
                    .filter { it.optString("status") == status && !it.optBoolean("deleted") }
                    .sortedByDescending { updatedAt(it) }
            val shown = cards.take(VISIBLE_PER_COLUMN)
            val older = cards.size - shown.size
            Column(
                // Equal shares for columns that carry cards; a column with
                // nothing in it shrinks (空列收窄) so the columns with work keep
                // the room. No horizontal scroll either way: this box runs at
                // 150% DPI, so the 1180px window is only ~787dp wide — six fixed
                // 176dp columns would push the last two off screen.
                Modifier.weight(if (cards.isEmpty()) 0.55f else 1f).fillMaxHeight()
                    .background(p.surface, RoundedCornerShape(12.dp))
                    .border(1.dp, p.outline, RoundedCornerShape(12.dp))
                    .padding(6.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        Modifier.width(3.dp).height(12.dp)
                            .background(statusColor(status), RoundedCornerShape(2.dp)),
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(
                        Strings.t(zh, en),
                        color = statusColor(status),
                        fontSize = 12.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                    Spacer(Modifier.weight(1f))
                    // The column's REAL size, cap or no cap — the footer carries the rest.
                    Muted("${cards.size}")
                }
                Spacer(Modifier.height(8.dp))
                Column(
                    Modifier.weight(1f).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    shown.forEach { card ->
                        // Keyed by id: without it, a refresh that re-sorts the column
                        // would hand an open card's dialog to whatever lands in its slot.
                        key(card.optString("id")) { BoardCard(state, card) }
                    }
                    if (shown.isEmpty()) {
                        Text("—", color = p.muted.copy(alpha = 0.5f), fontSize = 12.sp)
                    }
                }
                if (older > 0) {
                    // Pinned under the list, not scrolled with it: the exit to the
                    // overflow has to stay visible without scrolling to it.
                    TextButton(
                        onClick = {
                            Log.info("ui: archive footer status=$status older=$older")
                            archiveStatus = status
                        },
                        contentPadding = CardPadding,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(
                            Strings.t("更早的 $older 张 · 查看归档", "$older older · view archive"),
                            color = p.muted,
                            fontSize = 11.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
        }
    }
    archiveStatus?.let { status ->
        val (zh, en) = COLUMNS.first { it.first == status }.let { it.second to it.third }
        ArchiveDialog(state, status, zh, en) { archiveStatus = null }
    }
}

/**
 * The column card — deliberately one line (user 2026-11-05: too much scrolling):
 * title, priority dot, role/holder/lease in small print. Labels, desc, checklist,
 * report, comments and the action buttons all live in [CardDetailDialog]; a card
 * with a button row per card is exactly the height that made columns scroll.
 */
@Composable
private fun BoardCard(
    state: PotState,
    card: JSONObject,
) {
    val p = pal
    val status = card.optString("status")
    val role = card.optString("role").ifEmpty { null }
    val holder = card.optString("holder").ifEmpty { null }
    val leaseUntil = if (card.isNull("leaseUntil")) 0L else card.optLong("leaseUntil", 0L)
    val leaseLeft = (leaseUntil - System.currentTimeMillis() / 1000).coerceAtLeast(0L)
    var showDetail by remember { mutableStateOf(false) }

    Surface(
        onClick = {
            Log.info("ui: card open detail id=${card.optString("id")}")
            showDetail = true
        },
        shape = RoundedCornerShape(10.dp),
        color = p.surfaceVariant,
        shadowElevation = 1.dp,
    ) {
        Column(Modifier.padding(horizontal = 9.dp, vertical = 7.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    card.optString("title"),
                    modifier = Modifier.weight(1f),
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = p.fg,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.width(4.dp))
                val priority = card.optString("priority", "normal")
                val dot =
                    when (priority) {
                        "urgent" -> p.error
                        "low" -> p.secondary
                        else -> p.muted
                    }
                Box(Modifier.width(7.dp).height(7.dp).background(dot, RoundedCornerShape(99.dp)))
            }
            if (role != null || holder != null || (status == "doing" && leaseLeft > 0)) {
                Spacer(Modifier.height(4.dp))
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    if (role != null) Chip(role, p.tertiary)
                    if (holder != null) Muted(holder.substringBefore(":"))
                    if (status == "doing" && leaseLeft > 0) {
                        Muted(Strings.t("租约 ", "lease ") + "%d:%02d".format(leaseLeft / 60, leaseLeft % 60))
                    }
                }
            }
        }
    }

    if (showDetail) {
        CardDetailDialog(state, card) { showDetail = false }
    }
}

/**
 * 卡片详情 (spec §4.2): the body the compact card hides — labels, desc, checklist
 * with evidence, report, comments — plus every human action. Reject/confirm dialogs
 * stack exactly as they used to on the card.
 */
@Composable
private fun CardDetailDialog(
    state: PotState,
    card: JSONObject,
    onClose: () -> Unit,
) {
    val p = pal
    val status = card.optString("status")
    val role = card.optString("role").ifEmpty { null }
    val holder = card.optString("holder").ifEmpty { null }
    val report = card.optJSONObject("report")
    val leaseUntil = if (card.isNull("leaseUntil")) 0L else card.optLong("leaseUntil", 0L)
    val leaseLeft = (leaseUntil - System.currentTimeMillis() / 1000).coerceAtLeast(0L)
    val priority = card.optString("priority", "normal")
    var assignOpen by remember { mutableStateOf(false) }
    var showReject by remember { mutableStateOf(false) }
    var showDelete by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(card.optString("title"), fontSize = 16.sp, fontWeight = FontWeight.SemiBold) },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Chip(statusLabel(status), statusColor(status))
                    Chip(
                        priorityLabel(priority),
                        when (priority) {
                            "urgent" -> p.error
                            "low" -> p.secondary
                            else -> p.muted
                        },
                    )
                    cardLabels(card).forEach { Chip(it, p.secondary) }
                    if (role != null) Chip(role, p.tertiary)
                }
                Muted(Strings.t("更新于 ", "updated ") + stamp(updatedAt(card)))
                if (holder != null) {
                    Muted(Strings.t("持有：", "Held by: ") + holder.substringBefore(":"))
                }
                if (status == "doing" && leaseLeft > 0) {
                    Muted(Strings.t("租约 ", "lease ") + "%d:%02d".format(leaseLeft / 60, leaseLeft % 60))
                }
                val desc = card.optString("desc")
                if (desc.isNotBlank()) {
                    SectionTitle(Strings.t("描述", "DESCRIPTION"))
                    Text(desc, fontSize = 12.sp, color = p.fg)
                }
                val checklist = card.optJSONArray("checklist")
                if (checklist != null && checklist.length() > 0) {
                    SectionTitle(Strings.t("清单", "CHECKLIST"))
                    for (i in 0 until checklist.length()) {
                        val item = checklist.optJSONObject(i) ?: continue
                        val done = item.optBoolean("done")
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(
                                if (done) "✓" else "○",
                                fontSize = 12.sp,
                                color = if (done) p.muted else p.fg,
                            )
                            Column {
                                Text(
                                    item.optString("text"),
                                    fontSize = 12.sp,
                                    color = if (done) p.muted else p.fg,
                                    textDecoration = if (done) TextDecoration.LineThrough else null,
                                )
                                val evidence = item.optString("evidence")
                                if (done && evidence.isNotEmpty()) {
                                    Muted(Strings.t("证据：", "evidence: ") + evidence)
                                }
                            }
                        }
                    }
                }
                if (report != null) {
                    SectionTitle(Strings.t("报告", "REPORT"))
                    Text(report.optString("summary"), fontSize = 12.sp, color = p.muted)
                }
                val comments = card.optJSONArray("comments")
                if (comments != null && comments.length() > 0) {
                    SectionTitle(Strings.t("评论", "COMMENTS"))
                    for (i in 0 until comments.length()) {
                        val c = comments.optJSONObject(i) ?: continue
                        val at = c.optLong("at", 0L)
                        Column {
                            Muted(c.optString("by") + (if (at > 0) " · " + stamp(at) else ""))
                            Text(c.optString("text"), fontSize = 12.sp, color = p.fg)
                        }
                    }
                }
            }
        },
        confirmButton = {
            Row(
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (status != "done") {
                    Box {
                        MiniActionButton(Strings.t("改派", "Reassign"), p.muted) { assignOpen = true }
                        DropdownMenu(expanded = assignOpen, onDismissRequest = { assignOpen = false }) {
                            DropdownMenuItem(
                                text = { Text(Strings.t("不限（任何角色）", "Anyone (any role)")) },
                                onClick = {
                                    assignOpen = false
                                    state.assign(card, null)
                                },
                            )
                            state.roles.filter { !it.optBoolean("isTemplate") }.forEach { r ->
                                DropdownMenuItem(
                                    text = { Text(r.optString("id")) },
                                    onClick = {
                                        assignOpen = false
                                        state.assign(card, r.optString("id"))
                                    },
                                )
                            }
                        }
                    }
                }
                when (status) {
                    "review" -> {
                        Button(
                            onClick = {
                                onClose()
                                state.complete(card)
                            },
                            contentPadding = CardPadding,
                            colors = ButtonDefaults.buttonColors(containerColor = p.primary, contentColor = p.onPrimary),
                        ) { Text(Strings.t("✓ 完成", "✓ Done"), fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                        RejectButton { showReject = true }
                    }
                    "doing" -> {
                        MiniActionButton(Strings.t("续租", "Renew"), p.muted) { state.renew(card) }
                        RejectButton { showReject = true }
                    }
                    "blocked" -> RejectButton { showReject = true }
                }
                if (status != "done") {
                    MiniActionButton(Strings.t("删除", "Delete"), p.muted) { showDelete = true }
                }
                MiniActionButton(Strings.t("关闭", "Close"), p.muted, onClose)
            }
        },
    )

    if (showReject) {
        RejectDialog(state, card) { showReject = false }
    }
    if (showDelete) {
        AlertDialog(
            onDismissRequest = { showDelete = false },
            title = { Text(Strings.t("删除卡片", "Delete card")) },
            text = {
                Text(
                    Strings.t(
                        "「${card.optString("title")}」将被软删（不可从 UI 恢复）。",
                        "“${card.optString("title")}” will be soft-deleted (it cannot be restored from the UI).",
                    ),
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    showDelete = false
                    state.deleteCard(card)
                }) { Text(Strings.t("删除", "Delete"), color = p.error) }
            },
            dismissButton = {
                TextButton(onClick = { showDelete = false }) { Text(Strings.t("取消", "Cancel")) }
            },
        )
    }
}

/**
 * 归档 (user 2026-11-05): everything past the column's newest [VISIBLE_PER_COLUMN],
 * read-only, grouped 今天/昨天/本周/更早 and filterable by label/role. The VIEW
 * holds the overflow — the data layer is untouched, `deleted` stays the only
 * (soft) removal path.
 */
@Composable
private fun ArchiveDialog(
    state: PotState,
    status: String,
    zh: String,
    en: String,
    onClose: () -> Unit,
) {
    val p = pal
    val overflow =
        remember(state.cards, status) {
            state.cards
                .filter { it.optString("status") == status && !it.optBoolean("deleted") }
                .sortedByDescending { updatedAt(it) }
                .drop(VISIBLE_PER_COLUMN)
        }
    var labelFilter by remember { mutableStateOf<String?>(null) }
    var roleFilter by remember { mutableStateOf<String?>(null) }
    var labelOpen by remember { mutableStateOf(false) }
    var roleOpen by remember { mutableStateOf(false) }

    val labels = remember(overflow) { overflow.flatMap { cardLabels(it) }.distinct().sorted() }
    val roles =
        remember(overflow) {
            overflow.map { it.optString("role") }.filter { it.isNotEmpty() }.distinct().sorted()
        }
    val cards =
        overflow.filter {
            (labelFilter == null || cardLabels(it).contains(labelFilter)) &&
                (roleFilter == null || it.optString("role") == roleFilter)
        }
    val groups = cards.groupBy { dateBucket(updatedAt(it)) }

    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(Strings.t("「$zh」归档", "“$en” archive")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box {
                        OutlinedButton(onClick = { labelOpen = true }) {
                            Text(
                                Strings.t("标签：", "Label: ") + (labelFilter ?: Strings.t("全部", "all")),
                                fontSize = 12.sp,
                            )
                        }
                        DropdownMenu(expanded = labelOpen, onDismissRequest = { labelOpen = false }) {
                            DropdownMenuItem(
                                text = { Text(Strings.t("全部", "all")) },
                                onClick = {
                                    labelFilter = null
                                    labelOpen = false
                                },
                            )
                            labels.forEach { l ->
                                DropdownMenuItem(
                                    text = { Text(l) },
                                    onClick = {
                                        labelFilter = l
                                        labelOpen = false
                                    },
                                )
                            }
                        }
                    }
                    Box {
                        OutlinedButton(onClick = { roleOpen = true }) {
                            Text(
                                Strings.t("角色：", "Role: ") + (roleFilter ?: Strings.t("不限", "any")),
                                fontSize = 12.sp,
                            )
                        }
                        DropdownMenu(expanded = roleOpen, onDismissRequest = { roleOpen = false }) {
                            DropdownMenuItem(
                                text = { Text(Strings.t("不限", "any")) },
                                onClick = {
                                    roleFilter = null
                                    roleOpen = false
                                },
                            )
                            roles.forEach { r ->
                                DropdownMenuItem(
                                    text = { Text(r) },
                                    onClick = {
                                        roleFilter = r
                                        roleOpen = false
                                    },
                                )
                            }
                        }
                    }
                }
                Spacer(Modifier.height(10.dp))
                if (cards.isEmpty()) {
                    Muted(Strings.t("（没有更早的卡）", "(no older cards)"))
                }
                for (bucket in 0..3) {
                    val group = groups[bucket] ?: continue
                    SectionTitle("${bucketLabel(bucket)} · ${group.size}")
                    group.forEach { card ->
                        Row(
                            Modifier.fillMaxWidth().padding(vertical = 3.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            val role = card.optString("role").ifEmpty { null }
                            if (role != null) Chip(role, p.tertiary)
                            Text(
                                card.optString("title"),
                                Modifier.weight(1f),
                                color = p.fg,
                                fontSize = 12.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Muted(stamp(updatedAt(card)))
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                }
            }
        },
        confirmButton = {
            MiniActionButton(Strings.t("关闭", "Close"), p.muted, onClose)
        },
    )
}

private val CardPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 6.dp, vertical = 2.dp)

/** The role table's action column: fixed, so Edit/Del never get squeezed. */
private val ActionsWidth = 112.dp

/**
 * A small bordered action button. Bare `TextButton` text read as plain text
 * (user 2026-11-05, pointing at 编辑/删: 「差点看不出是按钮」) — the hairline pill
 * border in the label's own color is what says "button" without growing the row.
 */
@Composable
private fun MiniActionButton(
    label: String,
    color: Color,
    onClick: () -> Unit,
) {
    TextButton(
        onClick = onClick,
        contentPadding = CardPadding,
        border = BorderStroke(1.dp, color.copy(alpha = 0.55f)),
        colors = ButtonDefaults.textButtonColors(contentColor = color),
    ) {
        Text(label, fontSize = 11.sp)
    }
}

@Composable
private fun RejectButton(onClick: () -> Unit) {
    MiniActionButton(Strings.t("✗ 退回", "✗ Reject"), pal.error, onClick)
}

@Composable
private fun RejectDialog(
    state: PotState,
    card: JSONObject,
    onClose: () -> Unit,
) {
    var reason by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(Strings.t("退回卡片", "Reject card")) },
        text = {
            Column {
                Muted(
                    Strings.t(
                        "退回原因会写进卡片评论，角色开工前必读。",
                        "The reason goes into the card's comments — roles read it before starting.",
                    ),
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = reason,
                    onValueChange = { reason = it },
                    minLines = 2,
                    placeholder = { Text(Strings.t("例如：缺测试", "e.g. missing tests")) },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onClose()
                    state.reject(card, reason.ifBlank { Strings.t("（未填原因）", "(no reason given)") })
                },
            ) { Text(Strings.t("退回", "Reject")) }
        },
        dismissButton = {
            TextButton(onClick = onClose) { Text(Strings.t("取消", "Cancel")) }
        },
    )
}

@Composable
private fun CreateCardDialog(
    state: PotState,
    onClose: () -> Unit,
) {
    var title by remember { mutableStateOf("") }
    var desc by remember { mutableStateOf("") }
    var labels by remember { mutableStateOf("") }
    var priority by remember { mutableStateOf("normal") }
    var role by remember { mutableStateOf<String?>(null) }
    var priorityOpen by remember { mutableStateOf(false) }
    var roleOpen by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(Strings.t("新建卡片", "New card")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text(Strings.t("标题（目标）", "Title (the goal)")) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = desc,
                    onValueChange = { desc = it },
                    label = { Text(Strings.t("目标 + 回复格式 + 约束", "Goal + reply format + constraints")) },
                    // The bracket used to sit INSIDE the label and wrapped mid-way
                    // ("web=" / "网络 …"), user report 2026-11-04 — a hint belongs
                    // under the box, where it wraps as a line of its own.
                    supportingText = {
                        Text(
                            Strings.t(
                                "卡片必须自足：角色只看这张卡",
                                "The card must stand alone: a role sees only this card",
                            ),
                            fontSize = 10.sp,
                        )
                    },
                    minLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = labels,
                    onValueChange = { labels = it },
                    label = { Text(Strings.t("标签", "Labels")) },
                    supportingText = {
                        Text(
                            Strings.t(
                                "逗号分隔；需在角色的可认领范围内",
                                "Comma-separated; must fall inside the role's claimable labels",
                            ),
                            fontSize = 10.sp,
                        )
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box {
                        OutlinedButton(onClick = { priorityOpen = true }) {
                            Text(Strings.t("优先级：", "Priority: ") + priorityLabel(priority))
                        }
                        DropdownMenu(expanded = priorityOpen, onDismissRequest = { priorityOpen = false }) {
                            PRIORITIES.forEach {
                                DropdownMenuItem(text = { Text(priorityLabel(it)) }, onClick = {
                                    priority = it
                                    priorityOpen = false
                                })
                            }
                        }
                    }
                    Box {
                        OutlinedButton(onClick = { roleOpen = true }) {
                            Text(Strings.t("角色：", "Role: ") + (role ?: Strings.t("不限", "any")))
                        }
                        DropdownMenu(expanded = roleOpen, onDismissRequest = { roleOpen = false }) {
                            DropdownMenuItem(text = { Text(Strings.t("不限", "any")) }, onClick = {
                                role = null
                                roleOpen = false
                            })
                            state.roles.filter { !it.optBoolean("isTemplate") }.forEach { r ->
                                DropdownMenuItem(text = { Text(r.optString("id")) }, onClick = {
                                    role = r.optString("id")
                                    roleOpen = false
                                })
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = title.isNotBlank(),
                onClick = {
                    onClose()
                    state.createCard(
                        title.trim(),
                        desc,
                        labels.split(',', '，').map { it.trim() }.filter { it.isNotEmpty() },
                        priority,
                        role,
                    )
                },
            ) { Text(Strings.t("建卡", "Create")) }
        },
        dismissButton = {
            TextButton(onClick = onClose) { Text(Strings.t("取消", "Cancel")) }
        },
    )
}

// ── roles (spec §3.1: 定义在盘上, 人掌权) ──

@Composable
private fun RolesPanel(state: PotState) {
    val p = pal
    var editing by remember { mutableStateOf<JSONObject?>(null) }
    var creating by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<JSONObject?>(null) }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Spacer(Modifier.weight(1f))
            Button(onClick = { creating = true }) { Text(Strings.t("＋ 新建角色", "+ New role")) }
        }
        Spacer(Modifier.height(8.dp))
        // Weighted columns, not fixed dp (2026-11-04): the English headers are wider
        // than the Chinese ones and `can create` / `template` ran into each other at
        // 940dp. Weights share the row in both languages and at any window size.
        val widths =
            listOf(0.95f, 1.05f, 1.6f, 0.3f, 1.05f, 0.8f, 0.95f, 0.7f)
        val headers =
            listOf(
                Strings.t("标识", "id"),
                Strings.t("名称", "name"),
                Strings.t("工具", "tools"),
                Strings.t("并行", "wip"),
                Strings.t("可认领", "claims"),
                Strings.t("可建卡", "creates"),
                Strings.t("模板", "template"),
                Strings.t("创建者", "author"),
                "",
            )
        Row(
            Modifier.fillMaxWidth().padding(vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            headers.forEachIndexed { i, label ->
                Text(
                    label,
                    if (i < widths.size) Modifier.weight(widths[i]) else Modifier.width(ActionsWidth),
                    color = p.muted,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            state.roles.forEach { role ->
                val isTemplate = role.optBoolean("isTemplate")
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        role.optString("id"),
                        Modifier.weight(widths[0]),
                        color = p.fg,
                        fontSize = 12.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        role.optString("name"),
                        Modifier.weight(widths[1]),
                        color = p.fg,
                        fontSize = 12.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        toolsText(role),
                        Modifier.weight(widths[2]),
                        color = p.muted,
                        fontSize = 11.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text("${role.optInt("wip", 0)}", Modifier.weight(widths[3]), color = p.muted, fontSize = 11.sp)
                    Text(
                        canClaimText(role),
                        Modifier.weight(widths[4]),
                        color = p.muted,
                        fontSize = 11.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        if (role.optBoolean("canCreateCard")) "✓" else "—",
                        Modifier.weight(widths[5]),
                        color = p.muted,
                        fontSize = 11.sp,
                    )
                    // A template role IS the template; a derived one names its base.
                    if (isTemplate) {
                        Box(Modifier.weight(widths[6])) { Chip(Strings.t("模板", "template"), p.tertiary) }
                    } else {
                        Text(
                            role.optString("template"),
                            Modifier.weight(widths[6]),
                            color = p.muted,
                            fontSize = 11.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Text(
                        creatorText(role),
                        Modifier.weight(widths[7]),
                        color = p.muted,
                        fontSize = 11.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Row(Modifier.width(ActionsWidth), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        MiniActionButton(Strings.t("编辑", "Edit"), p.primary) { editing = role }
                        MiniActionButton(Strings.t("删", "Del"), p.error) { deleting = role }
                    }
                }
            }
        }
    }

    if (creating || editing != null) {
        RoleEditor(state, editing) {
            creating = false
            editing = null
        }
    }
    deleting?.let { role ->
        AlertDialog(
            onDismissRequest = { deleting = null },
            title = { Text(Strings.t("删除角色", "Delete role")) },
            text = {
                Text(
                    Strings.t(
                        "删除「${role.optString("id")}」？已有会话保留（只读），但该角色不能再认领。",
                        "Delete “${role.optString("id")}”? Existing sessions are kept (read-only), " +
                            "but the role can no longer claim cards.",
                    ),
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    val id = role.optString("id")
                    deleting = null
                    state.deleteRole(id)
                }) { Text(Strings.t("删除", "Delete"), color = p.error) }
            },
            dismissButton = {
                TextButton(onClick = { deleting = null }) { Text(Strings.t("取消", "Cancel")) }
            },
        )
    }
}

/** One string of an array of strings, or "" — JSONObject.optString on arrays is useless. */
private fun org.json.JSONArray.joinStrings(): String = (0 until length()).joinToString(",") { optString(it) }

/** Tool-group ids → the words the table shows (unknown ids pass through). */
private fun toolLabel(id: String): String =
    when (id) {
        "shell" -> Strings.t("终端", "shell")
        "files" -> Strings.t("文件", "files")
        "search" -> Strings.t("搜索", "search")
        "web" -> Strings.t("网络", "web")
        "screen" -> Strings.t("桌面", "screen")
        else -> id
    }

private fun toolsText(role: JSONObject): String {
    val arr = role.optJSONArray("tools") ?: return ""
    return (0 until arr.length())
        .map { toolLabel(arr.optString(it)) }
        .joinToString(Strings.t("，", ", "))
}

private fun creatorText(role: JSONObject): String =
    when (role.optString("createdBy")) {
        "human" -> Strings.t("人", "human")
        "planner" -> "Planner"
        else -> role.optString("createdBy")
    }

private fun priorityLabel(p: String): String =
    when (p) {
        "urgent" -> Strings.t("紧急", "urgent")
        "normal" -> Strings.t("普通", "normal")
        "low" -> Strings.t("低", "low")
        else -> p
    }

private fun canClaimText(role: JSONObject): String =
    when {
        role.isNull("canClaim") -> ""
        role.optBoolean("canClaim", false) && role.opt("canClaim") is Boolean ->
            if (role.optBoolean("canClaim")) Strings.t("全部", "all") else Strings.t("禁止", "none")
        else ->
            role.optJSONArray("canClaim")?.joinStrings()?.ifEmpty { Strings.t("全部", "all") } ?: ""
    }

@Composable
private fun RoleEditor(
    state: PotState,
    existing: JSONObject?,
    onClose: () -> Unit,
) {
    val isNew = existing == null
    var id by remember { mutableStateOf(existing?.optString("id") ?: "") }
    var name by remember { mutableStateOf(existing?.optString("name") ?: "") }
    var mission by remember { mutableStateOf(existing?.optString("mission") ?: "") }
    var tools by remember { mutableStateOf(existing?.optJSONArray("tools")?.joinStrings() ?: "") }
    var model by remember { mutableStateOf(existing?.optString("model") ?: "") }
    var wip by remember { mutableStateOf((existing?.optInt("wip") ?: 2).toString()) }
    var canClaim by remember { mutableStateOf(canClaimText(existing ?: JSONObject())) }
    var canCreateCard by remember { mutableStateOf(existing?.optBoolean("canCreateCard") ?: false) }
    var isTemplate by remember { mutableStateOf(existing?.optBoolean("isTemplate") ?: false) }
    var template by remember { mutableStateOf(existing?.optString("template") ?: "") }
    var templateOpen by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onClose,
        title = {
            Text(
                if (isNew) {
                    Strings.t("新建角色", "New role")
                } else {
                    Strings.t("编辑角色 ", "Edit role ") + existing?.optString("id")
                },
            )
        },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                if (isNew) {
                    OutlinedTextField(
                        id,
                        { id = it },
                        label = {
                            Text(Strings.t("id（小写字母/数字/下划线）", "id (lowercase letters / digits / _)"))
                        },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Spacer(Modifier.height(6.dp))
                }
                OutlinedTextField(
                    name,
                    { name = it },
                    label = { Text(Strings.t("名称", "Name")) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(
                    mission,
                    { mission = it },
                    label = { Text(Strings.t("使命（写进系统提示词）", "Mission (goes into the system prompt)")) },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(6.dp))
                // The legend lived in the label and wrapped mid-token
                // ("web=" / "网络 …"): it belongs under the box.
                OutlinedTextField(
                    tools,
                    { tools = it },
                    label = { Text(Strings.t("工具", "Tools")) },
                    supportingText = {
                        Text(
                            Strings.t(
                                "shell=终端 files=文件 search=搜索 web=网络 screen=桌面",
                                "shell, files, search, web, screen",
                            ),
                            fontSize = 10.sp,
                        )
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        wip,
                        { wip = it.filter(Char::isDigit) },
                        label = { Text(Strings.t("并行", "WIP")) },
                        singleLine = true,
                        modifier = Modifier.width(90.dp),
                    )
                    OutlinedTextField(
                        model,
                        { model = it },
                        label = { Text(Strings.t("模型（空=跟随全局）", "Model (blank = global)")) },
                        singleLine = true,
                        modifier = Modifier.weight(1f),
                    )
                }
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(
                    canClaim,
                    { canClaim = it },
                    label = { Text(Strings.t("可认领", "Can claim")) },
                    supportingText = {
                        Text(
                            Strings.t(
                                "标签逗号分隔；空=全部；false=禁止认领",
                                "Comma-separated labels; blank = all; false = none",
                            ),
                            fontSize = 10.sp,
                        )
                    },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(canCreateCard, { canCreateCard = it })
                    Text(Strings.t("可建卡", "Can create cards"), fontSize = 12.sp)
                    Spacer(Modifier.width(12.dp))
                    Checkbox(isTemplate, { isTemplate = it })
                    Text(Strings.t("模板", "Template"), fontSize = 12.sp)
                }
                Box {
                    OutlinedButton(onClick = { templateOpen = true }) {
                        Text("template：" + template.ifEmpty { Strings.t("（无）", "(none)") })
                    }
                    DropdownMenu(expanded = templateOpen, onDismissRequest = { templateOpen = false }) {
                        DropdownMenuItem(text = { Text(Strings.t("（无）", "(none)")) }, onClick = {
                            template = ""
                            templateOpen = false
                        })
                        state.roles.filter { it.optBoolean("isTemplate") }.forEach { r ->
                            DropdownMenuItem(text = { Text(r.optString("id")) }, onClick = {
                                template = r.optString("id")
                                templateOpen = false
                            })
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = id.isNotBlank() || !isNew,
                onClick = {
                    val fields =
                        JSONObject()
                            .put("name", name)
                            .put("mission", mission)
                            .put("tools", JSONArrayOf(tools))
                            .put("wip", wip.toIntOrNull() ?: 2)
                            .put("canClaim", canClaimValue(canClaim))
                            .put("canCreateCard", canCreateCard)
                            .put("isTemplate", isTemplate)
                    if (model.isNotBlank()) fields.put("model", model)
                    if (template.isNotBlank()) fields.put("template", template)
                    onClose()
                    if (isNew) {
                        fields.put("id", id)
                        state.createRole(fields)
                    } else {
                        state.updateRole(existing!!.optString("id"), fields)
                    }
                },
            ) {
                Text(if (isNew) Strings.t("创建", "Create") else Strings.t("保存", "Save"))
            }
        },
        dismissButton = {
            TextButton(onClick = onClose) { Text(Strings.t("取消", "Cancel")) }
        },
    )
}

private fun JSONArrayOf(csv: String) =
    org.json.JSONArray(csv.split(',', '，').map { it.trim() }.filter { it.isNotEmpty() })

private fun canClaimValue(text: String): Any {
    val t = text.trim()
    return when {
        t.isEmpty() -> org.json.JSONArray()
        t.equals("false", true) -> false
        else -> JSONArrayOf(t)
    }
}
