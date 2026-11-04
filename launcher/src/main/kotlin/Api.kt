package pot.launcher

import org.json.JSONObject
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

/** An HTTP call that came back 4xx/5xx: [code] is the status, message the hub's error. */
class ApiError(val code: Int, message: String) : Exception(message)

/**
 * The loopback API client (spec §4 方案 A): the hub answers `/api/...` with a
 * token (query for GET, body for POST) and `{"error": "<code>: <detail>"}` on
 * business failures; the WebUI answers settings routes without a token for
 * loopback clients.
 */
object Api {
    private val client: HttpClient =
        HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(4)).build()

    fun get(url: String): JSONObject = request("GET", url, null)

    fun post(url: String, body: JSONObject): JSONObject = request("POST", url, body)

    private fun request(
        method: String,
        url: String,
        body: JSONObject?,
    ): JSONObject {
        val builder =
            HttpRequest
                .newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(10))
                .header("Accept", "application/json")
        if (body != null) {
            builder.header("Content-Type", "application/json")
            builder.method(method, HttpRequest.BodyPublishers.ofString(body.toString()))
        } else {
            builder.method(method, HttpRequest.BodyPublishers.noBody())
        }
        val resp = client.send(builder.build(), HttpResponse.BodyHandlers.ofString())
        val text = resp.body().ifBlank { "{}" }
        val json = runCatching { JSONObject(text) }.getOrNull() ?: JSONObject()
        if (resp.statusCode() >= 400) {
            throw ApiError(resp.statusCode(), json.optString("error", text.take(300)))
        }
        return json
    }
}
