package com.Mavis.binanceetfmonitor

import android.os.Handler
import android.os.Looper

/**
 * 把 Python 端的 stdout 流式回调桥接到 Kotlin UI 线程。
 *
 *  - Python 端:从 sys.stdout 写出每行后,调用这个 proxy 的 emit(line) 方法
 *  - Kotlin 端:把所有调用通过 Handler 切回主线程,触发 onLine 回调
 *
 *  Chaquopy 会自动把这个类作为 Python 类型暴露,所以 `runner.run_with_callback(..., callback)`
 *  在 Python 里能直接 callback.emit(line) 调过来。
 */
class RunnerCallback(
    private val onLine: (String) -> Unit,
) {
    private val mainHandler = Handler(Looper.getMainLooper())

    /** Python 调用入口 */
    @Suppress("unused")
    fun emit(line: String) {
        mainHandler.post { onLine(line) }
    }

    /** Python 可选:任务结束时调一下,带 exit code */
    @Suppress("unused")
    fun finished(exitCode: Int) {
        mainHandler.post { /* noop, caller 监听 run_with_callback 的返回值 */ }
    }
}