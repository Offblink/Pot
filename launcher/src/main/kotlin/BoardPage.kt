package pot.launcher

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.layout.widthIn
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

private val COLUMNS =
    listOf(
        "backlog" to "待规划",
        "todo" to "待办",
        "doing" to "进行中",
        "review" to "待验收",
        "done" to "已完成",
        "blocked" to "受阻",
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
            TabPill("看板", tab == 0) { tab = 0 }
            TabPill("角色", tab == 1) { tab = 1 }
            Spacer(Modifier.weight(1f))
            Muted("${state.cards.count { !it.optBoolean("deleted") }} 张卡")
            Button(onClick = { showCreate = true }, enabled = state.host.status == HostStatus.RUNNING) {
                Text("＋ 新建卡")
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
        COLUMNS.forEach { (status, label) ->
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
                    Text(label, color = statusColor(status), fontSize = 12.sp, fontFamily = FontFamily.Monospace)
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
                Muted("持有：" + holder.substringBefore(":"))
            }
            if (status == "doing" && leaseLeft > 0) {
                Spacer(Modifier.height(2.dp))
                Muted("租约 " + "%d:%02d".format(leaseLeft / 60, leaseLeft % 60))
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
                            Text("改派", fontSize = 11.sp, color = p.muted)
                        }
                        DropdownMenu(expanded = assignOpen, onDismissRequest = { assignOpen = false }) {
                            DropdownMenuItem(
                                text = { Text("不限（任何角色）") },
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
                        ) { Text("✓ 完成", fontSize = 11.sp, fontWeight = FontWeight.Bold) }
                        RejectButton { showReject = true }
                    }
                    "doing" -> {
                        TextButton(onClick = { state.renew(card) }, contentPadding = CardPadding) {
                            Text("续租", fontSize = 11.sp, color = p.muted)
                        }
                        RejectButton { showReject = true }
                    }
                    "blocked" -> RejectButton { showReject = true }
                }
                if (status != "done") {
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = { showDelete = true }, contentPadding = CardPadding) {
                        Text("删除", fontSize = 11.sp, color = p.muted)
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
            title = { Text("删除卡片") },
            text = { Text("「${card.optString("title")}」将被软删（不可从 UI 恢复）。") },
            confirmButton = {
                TextButton(onClick = {
                    showDelete = false
                    state.deleteCard(card)
                }) { Text("删除", color = p.error) }
            },
            dismissButton = { TextButton(onClick = { showDelete = false }) { Text("取消") } },
        )
    }
}

private val CardPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 6.dp, vertical = 2.dp)

@Composable
private fun RejectButton(onClick: () -> Unit) {
    val p = pal
    TextButton(onClick = onClick, contentPadding = CardPadding) {
        Text("✗ 退回", fontSize = 11.sp, color = p.error)
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
        title = { Text("退回卡片") },
        text = {
            Column {
                Muted("退回原因会写进卡片评论，角色开工前必读。")
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = reason,
                    onValueChange = { reason = it },
                    minLines = 2,
                    placeholder = { Text("例如：缺测试") },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onClose()
                    state.reject(card, reason.ifBlank { "（未填原因）" })
                },
            ) { Text("退回") }
        },
        dismissButton = { TextButton(onClick = onClose) { Text("取消") } },
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
        title = { Text("新建卡片") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("标题（目标）") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = desc,
                    onValueChange = { desc = it },
                    label = { Text("目标 + 回复格式 + 约束（卡片必须自足）") },
                    minLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = labels,
                    onValueChange = { labels = it },
                    label = { Text("标签（逗号分隔；需在角色的可认领范围内）") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box {
                        OutlinedButton(onClick = { priorityOpen = true }) { Text("优先级：" + priorityLabel(priority)) }
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
                        OutlinedButton(onClick = { roleOpen = true }) { Text("角色：" + (role ?: "不限")) }
                        DropdownMenu(expanded = roleOpen, onDismissRequest = { roleOpen = false }) {
                            DropdownMenuItem(text = { Text("不限") }, onClick = {
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
            ) { Text("建卡") }
        },
        dismissButton = { TextButton(onClick = onClose) { Text("取消") } },
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
            Button(onClick = { creating = true }) { Text("＋ 新建角色") }
        }
        Spacer(Modifier.height(8.dp))
        Row(
            Modifier.fillMaxWidth().padding(vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf("标识" to 120, "名称" to 130, "工具" to 190, "并行" to 40, "可认领" to 150, "可建卡" to 60, "模板" to 110, "创建者" to 70, "" to 90)
                .forEach { (label, w) -> Text(label, Modifier.width(w.dp), color = p.muted, fontSize = 10.sp, fontFamily = FontFamily.Monospace) }
        }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            state.roles.forEach { role ->
                val isTemplate = role.optBoolean("isTemplate")
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(role.optString("id"), Modifier.width(120.dp), color = p.fg, fontSize = 12.sp)
                    Text(role.optString("name"), Modifier.width(130.dp), color = p.fg, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        toolsText(role),
                        Modifier.width(190.dp),
                        color = p.muted,
                        fontSize = 11.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text("${role.optInt("wip", 0)}", Modifier.width(40.dp), color = p.muted, fontSize = 11.sp)
                    Text(canClaimText(role), Modifier.width(150.dp), color = p.muted, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(if (role.optBoolean("canCreateCard")) "✓" else "—", Modifier.width(60.dp), color = p.muted, fontSize = 11.sp)
                    Text(role.optString("template"), Modifier.width(110.dp), color = p.muted, fontSize = 11.sp)
                    Text(creatorText(role), Modifier.width(70.dp), color = p.muted, fontSize = 11.sp)
                    Row(Modifier.width(90.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        TextButton(onClick = { editing = role }, contentPadding = CardPadding) { Text("编辑", fontSize = 11.sp) }
                        TextButton(onClick = { deleting = role }, contentPadding = CardPadding) {
                            Text("删", fontSize = 11.sp, color = p.error)
                        }
                    }
                    if (isTemplate) Chip("模板", p.tertiary)
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
            title = { Text("删除角色") },
            text = { Text("删除「${role.optString("id")}」？已有会话保留（只读），但该角色不能再认领。") },
            confirmButton = {
                TextButton(onClick = {
                    val id = role.optString("id")
                    deleting = null
                    state.deleteRole(id)
                }) { Text("删除", color = p.error) }
            },
            dismissButton = { TextButton(onClick = { deleting = null }) { Text("取消") } },
        )
    }
}

/** One string of an array of strings, or "" — JSONObject.optString on arrays is useless. */
private fun org.json.JSONArray.joinStrings(): String = (0 until length()).joinToString(",") { optString(it) }

/** Tool-group ids → the Chinese words the table shows (unknown ids pass through). */
private val TOOL_LABELS =
    mapOf(
        "shell" to "终端",
        "files" to "文件",
        "search" to "搜索",
        "web" to "网络",
        "screen" to "桌面",
    )

private fun toolsText(role: JSONObject): String {
    val arr = role.optJSONArray("tools") ?: return ""
    return (0 until arr.length())
        .map { TOOL_LABELS[arr.optString(it)] ?: arr.optString(it) }
        .joinToString("，")
}

private fun creatorText(role: JSONObject): String =
    when (role.optString("createdBy")) {
        "human" -> "人"
        "planner" -> "Planner"
        else -> role.optString("createdBy")
    }

private fun priorityLabel(p: String): String =
    when (p) {
        "urgent" -> "紧急"
        "normal" -> "普通"
        "low" -> "低"
        else -> p
    }

private fun canClaimText(role: JSONObject): String =
    when {
        role.isNull("canClaim") -> ""
        role.optBoolean("canClaim", false) && role.opt("canClaim") is Boolean -> if (role.optBoolean("canClaim")) "全部" else "禁止"
        else -> role.optJSONArray("canClaim")?.joinStrings()?.ifEmpty { "全部" } ?: ""
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
        title = { Text(if (isNew) "新建角色" else "编辑角色 ${existing?.optString("id")}") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                if (isNew) {
                    OutlinedTextField(id, { id = it }, label = { Text("id（小写字母/数字/下划线）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(6.dp))
                }
                OutlinedTextField(name, { name = it }, label = { Text("名称") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(mission, { mission = it }, label = { Text("使命（写进系统提示词）") }, minLines = 2, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(tools, { tools = it }, label = { Text("工具（shell=终端 files=文件 search=搜索 web=网络 screen=桌面）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(wip, { wip = it.filter(Char::isDigit) }, label = { Text("并行") }, singleLine = true, modifier = Modifier.width(90.dp))
                    OutlinedTextField(model, { model = it }, label = { Text("模型（空=跟随全局）") }, singleLine = true, modifier = Modifier.weight(1f))
                }
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(canClaim, { canClaim = it }, label = { Text("可认领（标签逗号分隔；空=全部；false=禁止认领）") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(canCreateCard, { canCreateCard = it })
                    Text("可建卡", fontSize = 12.sp)
                    Spacer(Modifier.width(12.dp))
                    Checkbox(isTemplate, { isTemplate = it })
                    Text("模板", fontSize = 12.sp)
                }
                Box {
                    OutlinedButton(onClick = { templateOpen = true }) { Text("template：" + template.ifEmpty { "（无）" }) }
                    DropdownMenu(expanded = templateOpen, onDismissRequest = { templateOpen = false }) {
                        DropdownMenuItem(text = { Text("（无）") }, onClick = {
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
            ) { Text(if (isNew) "创建" else "保存") }
        },
        dismissButton = { TextButton(onClick = onClose) { Text("取消") } },
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
