package com.Mavis.binanceetfmonitor

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * 用户设置 + 基金列表持久化。
 *
 *  - 调度时间存在 SharedPreferences(简单键值)
 *  - 基金列表(etf_products)以 JSON 数组形式覆盖到 filesDir/project/config/etf_products.json
 *    这样 Python 端 reload 时就读到用户改过的列表
 */
object SettingsStore {

    private const val PREFS = "etf_monitor_prefs"
    private const val KEY_HOUR = "schedule_hour"
    private const val KEY_MINUTE = "schedule_minute"
    private const val KEY_WEEKDAYS_ONLY = "schedule_weekdays_only"

    // 默认每个工作日 14:30
    const val DEFAULT_HOUR = 14
    const val DEFAULT_MINUTE = 30
    const val DEFAULT_WEEKDAYS_ONLY = true

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun getScheduleHour(ctx: Context): Int = prefs(ctx).getInt(KEY_HOUR, DEFAULT_HOUR)
    fun getScheduleMinute(ctx: Context): Int = prefs(ctx).getInt(KEY_MINUTE, DEFAULT_MINUTE)
    fun getWeekdaysOnly(ctx: Context): Boolean = prefs(ctx).getBoolean(KEY_WEEKDAYS_ONLY, DEFAULT_WEEKDAYS_ONLY)

    fun setSchedule(ctx: Context, hour: Int, minute: Int, weekdaysOnly: Boolean) {
        val h = hour.coerceIn(0, 23)
        val m = minute.coerceIn(0, 59)
        prefs(ctx).edit()
            .putInt(KEY_HOUR, h)
            .putInt(KEY_MINUTE, m)
            .putBoolean(KEY_WEEKDAYS_ONLY, weekdaysOnly)
            .apply()
    }

    /**
     * 基金列表文本:每行一条,支持以下格式
     *   000001 华夏成长
     *   000001,华夏成长
     *   000001, 华夏成长
     *   {"code":"000001","name":"华夏成长"}
     *
     * 返回 JSON 数组字符串,可以直接写回 etf_products.json
     */
    fun parseFundTextToJson(text: String): String {
        val out = JSONArray()
        text.lineSequence()
            .map { it.trim() }
            .filter { it.isNotEmpty() && !it.startsWith("#") }
            .forEach { line ->
                val item = parseLine(line) ?: return@forEach
                out.put(item)
            }
        return out.toString(2)
    }

    private fun parseLine(line: String): JSONObject? {
        // 尝试 JSON
        if (line.startsWith("{")) {
            return try {
                val o = JSONObject(line)
                if (o.has("code")) o else null
            } catch (_: Throwable) { null }
        }
        // code[, ]name 或 code[ \t]+name
        val parts = line.split(Regex("[,;\\t]+")).map { it.trim() }.filter { it.isNotEmpty() }
        if (parts.isEmpty()) return null
        val code = parts[0]
        if (!code.matches(Regex("^[0-9A-Za-z]{4,8}$"))) return null
        val name = if (parts.size > 1) parts.drop(1).joinToString(" ") else ""
        return JSONObject().put("code", code).put("name", name)
    }

    /**
     * 读 etf_products.json(filesDir 优先,assets 兜底) → 多行文本。
     * 每行格式: code,name
     */
    fun loadFundListText(ctx: Context): String {
        val file = File(ctx.filesDir, "project/config/etf_products.json")
        if (!file.exists()) {
            // 兜底:从 assets 默认列表
            return loadDefaultFundListTextFromAssets(ctx)
        }
        return try {
            val arr = JSONArray(file.readText(Charsets.UTF_8))
            if (arr.length() == 0) {
                // 文件存在但是空(用户清空后保存),回退到默认
                loadDefaultFundListTextFromAssets(ctx)
            } else {
                buildString {
                    for (i in 0 until arr.length()) {
                        val o = arr.getJSONObject(i)
                        val code = o.optString("code", "")
                        val name = o.optString("name", "")
                        if (code.isNotEmpty()) append(code).append(",").append(name).append('\n')
                    }
                }
            }
        } catch (t: Throwable) {
            loadDefaultFundListTextFromAssets(ctx)
        }
    }

    /**
     * 从 assets/project/config/etf_products.json 读默认列表(总是有内容)
     */
    fun loadDefaultFundListTextFromAssets(ctx: Context): String {
        return try {
            ctx.assets.open("project/config/etf_products.json").use { input ->
                val raw = input.readBytes().toString(Charsets.UTF_8)
                val arr = JSONArray(raw)
                buildString {
                    for (i in 0 until arr.length()) {
                        val o = arr.getJSONObject(i)
                        val code = o.optString("code", "")
                        val name = o.optString("name", "")
                        if (code.isNotEmpty()) append(code).append(",").append(name).append('\n')
                    }
                }
            }
        } catch (t: Throwable) {
            ""
        }
    }

    /**
     * 把用户编辑的文本转 JSON 写回 filesDir/project/config/etf_products.json。
     * @return 成功写入的条目数。空文本会被拒绝,要求至少 1 条。
     */
    fun saveFundList(ctx: Context, text: String): Int {
        val json = parseFundTextToJson(text)
        val arr = JSONArray(json)
        require(arr.length() > 0) {
            "监控列表不能为空 — 如要清空,请点设置页的『恢复默认』按钮"
        }
        val file = File(ctx.filesDir, "project/config/etf_products.json")
        file.parentFile?.mkdirs()
        file.writeText(json, Charsets.UTF_8)
        return arr.length()
    }

    /**
     * 把默认列表从 assets 恢复到 filesDir(用户点了"恢复默认"按钮)
     */
    fun restoreDefaultFundList(ctx: Context): Int {
        val defaultText = loadDefaultFundListTextFromAssets(ctx)
        if (defaultText.isBlank()) return 0
        return saveFundList(ctx, defaultText)
    }
}