package com.Mavis.binanceetfmonitor

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * WorkManager 周期任务 — 每日定时跑监控。
 *
 *  关键改动:
 *  - 跑前清理昨日的报告 (.md / .txt)
 *  - 跑前清理历史数据文件里 yesterday 之前的条目
 *  - 跑前同步用户编辑过的 etf_products.json(如果 SettingsStore.saveFundList 已经写)
 *  - 静默 callback,后台跑
 *  - 周末由 ScheduleHelper.computeInitialDelayMs 提前过滤,到 Worker 这层就只管跑
 */
class MonitorWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val ctx = applicationContext
        val workDir = File(ctx.filesDir, "project")

        if (!AssetBootstrap.ensureProjectExtracted(ctx, workDir)) {
            return Result.retry()
        }
        AssetBootstrap.ensureOutputDirs(workDir)

        // 周末保险(虽然 ScheduleHelper 已经过滤,这里再判一次)
        if (SettingsStore.getWeekdaysOnly(ctx)) {
            val dow = Calendar.getInstance(TimeZone.getTimeZone("Asia/Shanghai"))
                .get(Calendar.DAY_OF_WEEK)
            if (dow == Calendar.SATURDAY || dow == Calendar.SUNDAY) {
                Log.i(TAG, "周末,跳过本次执行")
                return Result.success()
            }
        }

        // 1) 跑前清理昨日产物(阻塞,通常 < 50ms)
        val cleanup = CleanupHelper.cleanupYesterday(workDir)
        Log.i(TAG, "cleanup -> ${cleanup.deletedReports} reports deleted, ${cleanup.prunedHistoryDates} history dates pruned")

        // 2) 串接跑监控(静默 callback,后台)
        val sentinel = object {
            @Suppress("unused")
            fun emit(line: String) { /* drop */ }
        }

        return try {
            PythonRuntime.ensureStarted(ctx as android.app.Application)
            val py = com.chaquo.python.Python.getInstance()
            val runner = py.getModule("runner")
            val exitCode: Int = runner.callAttr(
                "run_with_callback",
                workDir.absolutePath,
                "",
                sentinel,
                240,
            ).toInt()
            if (exitCode == 0) {
                Result.success()
            } else {
                Result.retry()
            }
        } catch (t: Throwable) {
            Log.e(TAG, "auto run failed", t)
            Result.retry()
        }
    }

    companion object {
        const val NAME = "monitor_daily"
        private const val TAG = "MonitorWorker"

        fun isScheduled(ctx: Context): Boolean {
            val infos = androidx.work.WorkManager.getInstance(ctx)
                .getWorkInfosForUniqueWork(NAME)
                .get()
            return infos.any {
                it.state == androidx.work.WorkInfo.State.ENQUEUED ||
                    it.state == androidx.work.WorkInfo.State.RUNNING
            }
        }

        fun cancel(ctx: Context) {
            androidx.work.WorkManager.getInstance(ctx).cancelUniqueWork(NAME)
        }
    }
}

/**
 * 清理昨日的产物:reports 下的 md/txt,fund_history 中 yesterday 之前的日期。
 */
object CleanupHelper {

    private val tz: TimeZone get() = TimeZone.getTimeZone("Asia/Shanghai")

    data class CleanupResult(val deletedReports: Int, val prunedHistoryDates: Int)

    /**
     * 清理昨日及更早的产物。返回删除的报告数 + 清理的历史日期数。
     * 同步阻塞,通常 < 50ms。
     */
    fun cleanupYesterday(workDir: File): CleanupResult {
        val yesterday = yesterdayStamp()
        val n1 = cleanupReports(workDir, yesterday)
        val n2 = cleanupFundHistory(workDir, yesterday)
        return CleanupResult(n1, n2)
    }

    private fun yesterdayStamp(): String {
        val cal = Calendar.getInstance(tz)
        cal.add(Calendar.DAY_OF_YEAR, -1)
        return SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).apply {
            timeZone = tz
        }.format(cal.time)
    }

    private fun cleanupReports(workDir: File, yesterday: String): Int {
        val reportsDir = File(workDir, "output/reports")
        if (!reportsDir.exists()) return 0
        val deleted = mutableListOf<String>()
        reportsDir.listFiles()?.forEach { f ->
            // strategy_report_2024-01-15.md / strategy_report_2024-01-15.txt
            val name = f.name
            val match = Regex("""strategy_report_(\d{4}-\d{2}-\d{2})\.(md|txt)""").matchEntire(name)
            if (match != null) {
                val dateStr = match.groupValues[1]
                if (dateStr < yesterday) {
                    if (f.delete()) deleted += name
                }
            }
        }
        if (deleted.isNotEmpty()) {
            Log.i("CleanupHelper", "删除过期报告: ${deleted.joinToString(",")}")
        }
        return deleted.size
    }

    private fun cleanupFundHistory(workDir: File, yesterday: String): Int {
        val histFile = File(workDir, "output/data/fund_history.json")
        if (!histFile.exists()) return 0
        return try {
            val raw = histFile.readText(Charsets.UTF_8)
            if (raw.isBlank()) return 0
            val root = JSONObject(raw)
            val keysToScrub = listOf("daily_pct", "nav")
            var pruned = 0
            for (k in keysToScrub) {
                if (!root.has(k)) continue
                val dict = root.getJSONObject(k)
                val it = dict.keys()
                val toDelete = mutableListOf<String>()
                while (it.hasNext()) {
                    val date = it.next()
                    if (date < yesterday) toDelete.add(date)
                }
                for (d in toDelete) {
                    dict.remove(d)
                    pruned++
                }
            }
            if (pruned > 0) {
                histFile.writeText(root.toString(2), Charsets.UTF_8)
                Log.i("CleanupHelper", "清理 fund_history 中 $yesterday 之前的 $pruned 个日期条目")
            }
            pruned
        } catch (t: Throwable) {
            Log.w("CleanupHelper", "fund_history 清理失败: ${t.message}")
            0
        }
    }
}