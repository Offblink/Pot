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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject

/** 角色页（spec §4.2 / 裁决 37）: the launcher's main page — the role table.
 * The board itself lives in the WebUI scene (裁决 36): columns, archive, card
 * detail and card creation all moved there. */
@Composable
fun BoardPage(state: PotState) {
    Column(Modifier.fillMaxSize()) {
        RolesPanel(state)
    }
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
        role.opt("canClaim") is Boolean ->
            if (role.optBoolean("canClaim")) Strings.t("不限", "any") else Strings.t("禁止", "none")
        else ->
            role.optJSONArray("canClaim")?.joinStrings()?.ifEmpty { Strings.t("不限", "any") } ?: ""
    }
// 2026-11-06: 「全部」曾同时是空数组的 UI 文案和一个普通标签字面量（数据层
// board.py 只做子集比较、无特判），编辑器往返还会把文案写回数据（空数组 →
// 显示「全部」→ 保存成 ["全部"]）。文案改「不限」；canClaimValue 把显示词
// 映回真值，不让任何文案再落成标签。

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
                                "标签逗号分隔；空=不限；false=禁止认领",
                                "Comma-separated labels; blank = any; false = none",
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
        t.equals("false", true) || t.equals("禁止", true) || t.equals("none", true) -> false
        // Display tokens map back to values — never become literal labels.
        // 「全部」/all: the old UI wrote it for an empty array, so bare legacy
        // occurrences are contamination, not a label anyone chose.
        t.equals("不限", true) || t.equals("any", true) ||
            t.equals("全部", true) || t.equals("all", true) -> org.json.JSONArray()
        else -> JSONArrayOf(t)
    }
}
