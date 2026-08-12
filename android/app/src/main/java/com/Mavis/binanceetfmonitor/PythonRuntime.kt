package com.Mavis.binanceetfmonitor

import android.content.Context
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.util.concurrent.Callable
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

/**
 * Python 运行时管理 — Chaquopy 单例封装。
 *
 *  关键改动:
 *  - 用单独的 Executor 跑 Python,Future.get(timeout) 拿结果
 *  - 超时强制返回 -2,UI 永远能解锁
 *  - assets 解包在 Kotlin 端(AssetManager 走原 API,稳定)
 */
object PythonRuntime {

    private const val TAG = "PythonRuntime"
    private val pyExecutor = Executors.newSingleThreadExecutor { r ->
        Thread(r, "etf-monitor-py").apply { isDaemon = true }
    }

    @Volatile
    private var started: Boolean = false

    @Synchronized
    fun ensureStarted(app: android.app.Application) {
        if (started) return
        if (!Python.isStarted()) {
            AndroidPlatform(app)
            Python.start(AndroidPlatform(app))
            Log.i(TAG, "Chaquopy Python interpreter started")
        }
        started = true
    }

    /**
     * 跑一次监控。整段阻塞但有硬超时。
     *
     * @param timeoutSec 硬超时,到点后 Python 端内部继续运行,但 UI 立即解锁
     *                   真实运行经验:正常 30-90s,卡死 240s 内必须放手
     */
    fun runMonitor(
        context: Context,
        workDir: File,
        timeoutSec: Int,
        onLine: (String) -> Unit,
        onDone: (Int) -> Unit,
    ) {
        // 1. Kotlin 端 bootstrap(主线程内做,失败立即返回)
        if (!AssetBootstrap.ensureProjectExtracted(context, workDir)) {
            onLine("[ERROR] assets 解包失败,请重装 APK\n")
            onDone(-1)
            return
        }
        AssetBootstrap.ensureOutputDirs(workDir)
        onLine("[bootstrap] 项目目录就绪: ${workDir.absolutePath}\n")

        // 2. Python 端执行 — 丢到独立线程,Future.get 限时等
        val future: Future<Int> = pyExecutor.submit(Callable {
            try {
                val py = Python.getInstance()
                val runner = py.getModule("runner")
                val callback = RunnerCallback(onLine)
                runner.callAttr(
                    "run_with_callback",
                    workDir.absolutePath,
                    "",
                    callback,
                    timeoutSec,
                ).toInt()
            } catch (t: Throwable) {
                Log.e(TAG, "run failed", t)
                onLine("[ERROR] Python run 异常: ${t.message}\n")
                onLine(Log.getStackTraceString(t))
                -1
            }
        })

        try {
            val rc = future.get(timeoutSec.toLong() + 30, TimeUnit.SECONDS)
            onDone(rc)
        } catch (te: TimeoutException) {
            // Kotlin 端超时 — 强制中断 Future,UI 解锁
            future.cancel(true)
            onLine("\n[ERROR] Kotlin 端超时(${timeoutSec + 30}s),强制结束。\n")
            onLine("[提示] 排查方向:网络被墙 / API 限流 / pandas 阻塞\n")
            onDone(-2)
        } catch (ie: InterruptedException) {
            future.cancel(true)
            Thread.currentThread().interrupt()
            onLine("\n[ERROR] 任务被中断\n")
            onDone(-3)
        } catch (t: Throwable) {
            Log.e(TAG, "future failed", t)
            future.cancel(true)
            onLine("[ERROR] ${t.message}\n")
            onDone(-1)
        }
    }
}