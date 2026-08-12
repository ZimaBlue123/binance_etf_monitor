package com.Mavis.binanceetfmonitor

import android.app.Application

/**
 * 启动 Chaquopy Python 解释器。必须在任何 Activity.onCreate 之前完成。
 */
class App : Application() {
    override fun onCreate() {
        super.onCreate()
        PythonRuntime.ensureStarted(this)
    }
}