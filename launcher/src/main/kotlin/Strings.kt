package pot.launcher

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** The two languages Pot ships. `code` is what config.json's `ui_lang` holds. */
enum class Lang(
    val code: String,
    val label: String,
) {
    ZH("zh", "中文"),
    EN("en", "English"),
    ;

    companion object {
        fun of(code: String?): Lang = entries.firstOrNull { it.code == code } ?: ZH
    }
}

/**
 * One switch for both halves of the product (spec §74): the launcher's own text
 * comes from here, and the chosen code is written into config.json `ui_lang`, which
 * /lang.js serves to the WebUI on its next load.
 *
 * Strings sit at the call site as (Chinese, English) pairs — `Strings.t("看板", "Board")`.
 * That is deliberate: a key table needs a second lookup that can silently miss, while
 * a pair cannot exist in one language only. Reading `lang` (a snapshot state) inside
 * `t` makes every composable that renders text recompose when the language flips.
 */
object Strings {
    var lang by mutableStateOf(Lang.ZH)

    fun t(
        zh: String,
        en: String,
    ): String = if (lang == Lang.EN) en else zh
}
