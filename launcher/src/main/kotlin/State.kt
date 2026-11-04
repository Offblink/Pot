package pot.launcher

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

fun JSONArray.objList(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }

fun List<String>.toJsonArray(): JSONArray = JSONArray(this)

/**
 * UI state + the human actions (spec §3.5) as thin async wrappers over the hub
 * API. Every mutation refreshes the board so a failed write (stale_version,
 * already_held, bad_transition) lands back on real data, never on a ghost.
 */
class PotState(
    val host: HostManager,
) {
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    var cards by mutableStateOf<List<JSONObject>>(emptyList())
        private set
    var roles by mutableStateOf<List<JSONObject>>(emptyList())
        private set
    var snack by mutableStateOf("")
    var model by mutableStateOf<JSONObject?>(null)
        private set

    fun toast(msg: String) {
        snack = msg
    }

    fun refreshBoard() {
        if (host.status != HostStatus.RUNNING) {
            cards = emptyList()
            roles = emptyList()
            return
        }
        scope.launch {
            runCatching {
                val j = host.hubGet("/api/board")
                cards = j.optJSONArray("cards")?.objList() ?: emptyList()
                roles = j.optJSONArray("roles")?.objList() ?: emptyList()
            }
        }
    }

    fun loadModel() {
        if (host.status != HostStatus.RUNNING) return
        scope.launch { runCatching { model = host.webuiGet("/model") } }
    }

    /** Last language code this process wrote; `null` = never written. */
    private var pushedLang: String? = null

    /**
     * Hand the launcher's language to the host, which owns config.json (and its
     * lock) — `ui_lang` is what /lang.js serves to the WebUI, so this is the other
     * half of the one switch.
     *
     * The skip is decided by what WE wrote, not only by the polled status: `info`
     * lags up to one poll interval, and a flip-and-flip-back inside that window
     * would otherwise read the stale value and leave config.json on the first
     * language. With nothing written yet, the host's own value is the truth, so
     * starting a host whose config already matches is not a write.
     */
    fun pushLang(code: String) {
        if (host.status != HostStatus.RUNNING) return
        val hostCode = host.info?.optString("ui_lang")
        if (code == pushedLang || (pushedLang == null && hostCode == code)) return
        act {
            host.hubPost("/api/host/lang", JSONObject().put("lang", code))
            pushedLang = code
        }
    }

    private fun act(block: suspend () -> Unit) {
        scope.launch {
            try {
                block()
            } catch (e: ApiError) {
                toast("${e.code}: ${e.message}")
            } catch (e: Exception) {
                toast(e.message ?: Strings.t("出错了", "Something went wrong"))
            }
            refreshBoard()
        }
    }

    fun createCard(
        title: String,
        desc: String,
        labels: List<String>,
        priority: String,
        role: String?,
    ) = act {
        val body = JSONObject().put("title", title).put("desc", desc).put("priority", priority)
        if (labels.isNotEmpty()) body.put("labels", labels.toJsonArray())
        if (role != null) body.put("role", role)
        host.hubPost("/api/board/create", body)
    }

    fun complete(card: JSONObject) = act {
        host.hubPost(
            "/api/board/complete",
            JSONObject().put("card_id", card.getString("id")).put("if_version", card.getInt("ifVersion")),
        )
    }

    fun reject(
        card: JSONObject,
        reason: String,
    ) = act {
        host.hubPost(
            "/api/board/reject",
            JSONObject()
                .put("card_id", card.getString("id"))
                .put("reason", reason)
                .put("if_version", card.getInt("ifVersion")),
        )
    }

    fun assign(
        card: JSONObject,
        role: String?,
    ) = act {
        val body =
            JSONObject().put("card_id", card.getString("id")).put("if_version", card.getInt("ifVersion"))
        if (role == null) body.put("role", JSONObject.NULL) else body.put("role", role)
        host.hubPost("/api/board/assign", body)
    }

    fun renew(card: JSONObject) = act {
        host.hubPost(
            "/api/board/renew",
            JSONObject().put("card_id", card.getString("id")).put("if_version", card.getInt("ifVersion")),
        )
    }

    fun deleteCard(card: JSONObject) = act {
        host.hubPost(
            "/api/board/delete",
            JSONObject().put("card_id", card.getString("id")).put("if_version", card.getInt("ifVersion")),
        )
    }

    // ── roles (human-only privilege ground, spec §3.1) ──

    fun createRole(fields: JSONObject) =
        act {
            host.hubPost("/api/roles/create", fields)
        }

    fun updateRole(
        id: String,
        fields: JSONObject,
    ) = act {
        host.hubPost("/api/roles/update", fields.put("id", id))
    }

    fun deleteRole(id: String) =
        act {
            host.hubPost("/api/roles/delete", JSONObject().put("id", id))
        }

    // ── model settings (WebUI routes, loopback exempt) ──

    fun saveModel(
        apiKey: String?,
        endpoint: String?,
        modelName: String?,
    ) = act {
        val body = JSONObject()
        if (!apiKey.isNullOrBlank()) body.put("api_key", apiKey)
        if (!endpoint.isNullOrBlank()) body.put("endpoint", endpoint)
        if (!modelName.isNullOrBlank()) body.put("model", modelName)
        if (body.length() > 0) host.webuiPost("/configure", body)
        model = host.webuiGet("/model")
    }

    fun switchModel(name: String) =
        act {
            host.webuiPost("/model", JSONObject().put("model", name))
            model = host.webuiGet("/model")
        }
}
