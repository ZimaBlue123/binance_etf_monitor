package com.Mavis.binanceetfmonitor

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * 主界面 — 一键运行监控,不再需要 Termux。
 *
 *  设计:
 *  - 启动时确保 Chaquopy 已初始化(App.onCreate 已处理)
 *  - "▶ 运行监控" 触发 Python 端 bootstrap + run,流式回显到 output TextView
 *  - "📄 报告" 跳转 ReportActivity 浏览历史报告
 *  - "⏰ 启用每日 06:00 自动" 注册 WorkManager 周期任务
 *  - 状态栏显示:工作目录、报告目录、最近一次运行时间和退出码
 */
class MainActivity : AppCompatActivity() {

    private lateinit var statusView: TextView
    private lateinit var outputView: TextView
    private lateinit var runButton: Button
    private lateinit var viewReportsButton: Button
    private lateinit var scheduleButton: Button
    private lateinit var clearButton: Button
    private lateinit var settingsButton: Button

    private val ioExecutor = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusView = findViewById(R.id.status)
        outputView = findViewById(R.id.output)
        runButton = findViewById(R.id.run_monitor)
        viewReportsButton = findViewById(R.id.view_reports)
        scheduleButton = findViewById(R.id.toggle_schedule)
        clearButton = findViewById(R.id.clear_output)
        settingsButton = findViewById(R.id.open_settings)

        runButton.setOnClickListener { startMonitor() }
        viewReportsButton.setOnClickListener {
            startActivity(Intent(this, ReportActivity::class.java))
        }
        scheduleButton.setOnClickListener { toggleSchedule() }
        settingsButton.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        clearButton.setOnClickListener { outputView.text = "" }

        refreshStatus()
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
    }

    override fun onDestroy() {
        super.onDestroy()
        ioExecutor.shutdownNow()
    }

    private fun projectRoot(): File = File(filesDir, "project")

    private fun refreshStatus() {
        val workDir = projectRoot()
        val mainExists = File(workDir, "binance_etf_configurable.py").exists()
        val reportsDir = File(workDir, "output/reports")
        val reportCount = if (reportsDir.exists()) reportsDir.listFiles { f -> f.extension == "md" }?.size ?: 0 else 0
        val lastLog = readLastRunMarker()
        val scheduled = MonitorWorker.isScheduled(this)
        val fundFile = File(workDir, "config/etf_products.json")
        val fundCount = if (fundFile.exists()) {
            try { org.json.JSONArray(fundFile.readText(Charsets.UTF_8)).length() } catch (_: Throwable) { 0 }
        } else 0
        val sh = SettingsStore.getScheduleHour(this)
        val sm = SettingsStore.getScheduleMinute(this)
        val sw = SettingsStore.getWeekdaysOnly(this)
        val nextTrigger = if (scheduled) ScheduleHelper.formatNextTrigger(sh, sm, sw) else "未启用"
        val weekdaysLabel = if (sw) "工作日" else "每天"

        statusView.text = buildString {
            append("工作目录: ").append(workDir.absolutePath).append('\n')
            append("主程序:    ").append(if (mainExists) "已就绪 ✓" else "未就绪 ✗").append('\n')
            append("报告数量:  ").append(reportCount).append(" 个 .md 报告\n")
            append("监控基金:  ").append(fundCount).append(" 只 (设置页可改)\n")
            append("定时状态:  ").append(if (scheduled) "✓ 已启用" else "未启用").append('\n')
            if (scheduled) {
                append("           ").append(weekdaysLabel).append(" ")
                    .append(sh).append(":")
                    .append("%02d".format(sm))
                    .append(" → ").append(nextTrigger).append('\n')
            }
            if (lastLog != null) {
                append("上次运行:  ").append(lastLog).append('\n')
            }
        }

        scheduleButton.text = if (scheduled) "⏰ 定时: 已启用" else "⏰ 定时: 未启用"
        runButton.isEnabled = !isRunning.get()
    }

    private val isRunning = java.util.concurrent.atomic.AtomicBoolean(false)

    private fun startMonitor() {
        if (!isRunning.compareAndSet(false, true)) {
            Toast.makeText(this, "已有任务在跑", Toast.LENGTH_SHORT).show()
            return
        }
        runButton.isEnabled = false

        val workDir = projectRoot()
        val stamp = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).apply {
            timeZone = TimeZone.getTimeZone("Asia/Shanghai")
        }.format(Date())
        appendOutput("\n========== [$stamp] 开始运行监控 ==========\n")

        ioExecutor.execute {
            // 1) 跑前清理昨日产物(显式串接,UI 能看到清理条数)
            try {
                AssetBootstrap.ensureProjectExtracted(this@MainActivity, workDir)
                AssetBootstrap.ensureOutputDirs(workDir)
                val result = CleanupHelper.cleanupYesterday(workDir)
                val msg = "[cleanup] 删了 ${result.deletedReports} 个旧报告,清理 ${result.prunedHistoryDates} 个历史日期"
                runOnUiThread { appendOutput("$msg\n") }
            } catch (t: Throwable) {
                runOnUiThread { appendOutput("[cleanup] 清理失败(忽略): ${t.message}\n") }
            }

            // 2) 紧接着自动继续跑监控(阻塞,有超时)
            PythonRuntime.runMonitor(
                context = this@MainActivity,
                workDir = workDir,
                timeoutSec = 240,  // 4 分钟硬超时,卡死必返回
                onLine = { line -> runOnUiThread { appendOutput(line) } },
                onDone = { exitCode ->
                    runOnUiThread {
                        isRunning.set(false)
                        runButton.isEnabled = true
                        val msg = when (exitCode) {
                            0 -> "✓ 监控完成"
                            -2 -> "✗ 超时强制结束 (code=-2)"
                            -1 -> "✗ 运行异常 (code=-1)"
                            else -> "✗ 退出 code=$exitCode"
                        }
                        appendOutput("[$msg]\n\n")
                        writeLastRunMarker(exitCode)
                        refreshStatus()
                        Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
                    }
                },
            )
        }
    }

    private fun toggleSchedule() {
        val scheduled = MonitorWorker.isScheduled(this)
        if (scheduled) {
            // 入口:点主页"⏰ 定时"快捷切换;更精细去设置页
            ScheduleHelper.cancel(this)
            Toast.makeText(this, "已删除定时任务(去设置页重新配置)", Toast.LENGTH_SHORT).show()
        } else {
            ScheduleHelper.schedule(this)
            val h = SettingsStore.getScheduleHour(this)
            val m = SettingsStore.getScheduleMinute(this)
            val w = if (SettingsStore.getWeekdaysOnly(this)) "工作日" else "每天"
            Toast.makeText(this, "已启用 $w $h:${"%02d".format(m)} 跑监控", Toast.LENGTH_LONG).show()
        }
        refreshStatus()
    }

    /**
     * 计算离今天 06:00 还有多久(毫秒)。已废弃,改用 ScheduleHelper。
     */
    @Suppress("unused")
    private fun initialDelayFor6AM_DEPRECATED(): Long {
        val now = System.currentTimeMillis()
        val tz = TimeZone.getTimeZone("Asia/Shanghai")
        val dateOnly = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).apply {
            timeZone = tz
        }.format(now)
        val sixAMToday: Long = SimpleDateFormat("yyyy-MM-dd 06:00:00", Locale.getDefault()).apply {
            timeZone = tz
        }.parse("$dateOnly 06:00:00")?.time ?: (now + 60_000L)
        return (sixAMToday - now).coerceAtLeast(60_000L)
    }

    private fun appendOutput(s: String) {
        outputView.append(s)
        // 滚动到底 — 用 post 把滚动放到 layout 之后
        outputView.post {
            val parent = outputView.parent as android.widget.ScrollView
            parent.fullScroll(android.view.View.FOCUS_DOWN)
        }
    }

    private fun writeLastRunMarker(exitCode: Int) {
        try {
            val marker = File(projectRoot(), ".last_run")
            val stamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).apply {
                timeZone = TimeZone.getTimeZone("Asia/Shanghai")
            }.format(Date())
            marker.writeText("$stamp exit=$exitCode\n", Charsets.UTF_8)
        } catch (_: Throwable) {
            // 静默
        }
    }

    private fun readLastRunMarker(): String? = try {
        val marker = File(projectRoot(), ".last_run")
        if (marker.exists()) marker.readText(Charsets.UTF_8).trim() else null
    } catch (_: Throwable) {
        null
    }
}