package pot.launcher

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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
    Row(
        Modifier.fillMaxSize().padding(horizontal = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        COLUMNS.forEach { (status, zh, en) ->
            val cards = state.cards.filter { it.optString("status") == status && !it.optBoolean("deleted") }
            Column(
                // Equal shares, no horizontal scroll: this box runs at 150% DPI,
                // so the 1180px window is only ~787dp wide — six fixed 176dp
                // columns would push the last two columns off screen.
                Modifier.weight(1f).fillMaxHeight()
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
                    Muted("${cards.size}")
                }
                Spacer(Modifier.height(8.dp))
                Column(
                    Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    cards.forEach { card -> BoardCard(state, card) }
                    if (cards.isEmpty()) {
                        Text("—", color = p.muted.copy(alpha = 0.5f), fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun BoardCard(
    state: PotState,
    card: JSONObject,
) {
    val p = pal
    val status = card.optString("status")
    val role = card.optString("role").ifEmpty { null }
    val holder = card.optString("holder").ifEmpty { null }
    val report = card.optJSONObject("report")
    val leaseUntil = if (card.isNull("leaseUntil")) 0L else card.optLong("leaseUntil", 0L)
    val leaseLeft = (leaseUntil - System.currentTimeMillis() / 1000).coerceAtLeast(0L)
    var assignOpen by remember { mutableStateOf(false) }
    var showReject by remember { mutableStateOf(false) }
    var showDelete by remember { mutableStateOf(false) }

    Surface(
        shape = RoundedCornerShape(10.dp),
        color = p.surfaceVariant,
        shadowElevation = 1.dp,
    ) {
        Column(Modifier.padding(9.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Text(
                    card.optString("title"),
                    modifier = Modifier.weight(1f),
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = p.fg,
                    maxLines = 3,
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
                Box(Modifier.padding(top = 4.dp).width(7.dp).height(7.dp).background(dot, RoundedCornerShape(99.dp)))
            }
            Spacer(Modifier.height(5.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                val labels = card.optJSONArray("labels")
                if (labels != null) {
                    for (i in 0 until minOf(labels.length(), 3)) {
                        Chip(labels.optString(i), p.secondary)
                    }
                    if (labels.length() > 3) Chip("+${labels.length() - 3}", p.muted)
                }
                if (role != null) Chip(role, p.tertiary)
            }
            if (holder != null) {
                Spacer(Modifier.height(4.dp))
                Muted(Strings.t("持有：", "Held by: ") + holder.substringBefore(":"))
            }
            if (status == "doing" && leaseLeft > 0) {
                Spacer(Modifier.height(2.dp))
                Muted(Strings.t("租约 ", "lease ") + "%d:%02d".format(leaseLeft / 60, leaseLeft % 60))
            }
            if (status == "review" && report != null) {
                Spacer(Modifier.height(5.dp))
                Text(
                    report.optString("summary").take(120),
                    fontSize = 11.sp,
                    color = p.muted,
                    maxLines = 4,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Spacer(Modifier.height(7.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (status != "done") {
                    Box {
                        TextButton(onClick = { assignOpen = true }, contentPadding = CardPadding) {
                            Text(Strings.t("改派", "Reassign"), fontSize = 11.sp, color = p.muted)
                        }
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
                            onClick = { state.complete(card) },
                            contentPadding = CardPadding,
                            colors = ButtonDefaults.buttonColors(containerColor = p.primary, contentColor = p.onPrimary),
                        ) { Text(Strings.t("✓ 完成", "✓ Done"), fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                        RejectButton { showReject = true }
                    }
                    "doing" -> {
                        TextButton(onClick = { state.renew(card) }, contentPadding = CardPadding) {
                            Text(Strings.t("续租", "Renew"), fontSize = 11.sp, color = p.muted)
                        }
                        RejectButton { showReject = true }
                    }
                    "blocked" -> RejectButton { showReject = true }
                }
                if (status != "done") {
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = { showDelete = true }, contentPadding = CardPadding) {
                        Text(Strings.t("删除", "Delete"), fontSize = 11.sp, color = p.muted)
                    }
                }
            }
        }
    }

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

private val CardPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 6.dp, vertical = 2.dp)

/** The role table's action column: fixed, so Edit/Del never get squeezed. */
private val ActionsWidth = 112.dp

@Composable
private fun RejectButton(onClick: () -> Unit) {
    val p = pal
    TextButton(onClick = onClick, contentPadding = CardPadding) {
        Text(Strings.t("✗ 退回", "✗ Reject"), fontSize = 11.sp, color = p.error)
    }
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
                        TextButton(onClick = { editing = role }, contentPadding = CardPadding) {
                            Text(Strings.t("编辑", "Edit"), fontSize = 11.sp)
                        }
                        TextButton(onClick = { deleting = role }, contentPadding = CardPadding) {
                            Text(Strings.t("删", "Del"), fontSize = 11.sp, color = p.error)
                        }
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
