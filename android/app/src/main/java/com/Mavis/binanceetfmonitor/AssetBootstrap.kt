package com.Mavis.binanceetfmonitor

import android.content.Context
import android.util.Log
import java.io.File
import java.io.FileOutputStream

/**
 * 把 APK 内嵌的 assets/project 解包到 filesDir/project。
 *
 *  原因:Chaquopy 里的 android_asset 路径在某些 Android 版本 / API 上
 *  拿不到(实测小米的 Android 14 上直接报 FileNotFoundError),而 Android
 *  原生 AssetManager 永远稳。所以 bootstrap 放在 Kotlin 端。
 */
object AssetBootstrap {

    private const val TAG = "AssetBootstrap"
    private const val ASSETS_SUBDIR = "project"
    private const val MARKER = ".bootstrap_done"

    /**
     * @return true 表示本次或之前已 bootstrap 成功(目录就绪)
     */
    fun ensureProjectExtracted(context: Context, workDir: File): Boolean {
        if (!workDir.exists()) workDir.mkdirs()

        val mainScript = File(workDir, "binance_etf_configurable.py")
        val marker = File(workDir, MARKER)
        if (marker.exists() && mainScript.exists()) {
            Log.i(TAG, "already bootstrapped at ${workDir.absolutePath}")
            return true
        }

        Log.i(TAG, "extracting assets/$ASSETS_SUBDIR -> ${workDir.absolutePath}")
        val am = context.assets
        val root = ASSETS_SUBDIR
        var copied = 0
        try {
            copyDir(am, root, workDir)
            // 重新统计:从 workDir 顶层开始
            copied = workDir.walkTopDown().count { it.isFile }
        } catch (t: Throwable) {
            Log.e(TAG, "extraction failed", t)
            return false
        }

        // 给 .sh 文件可执行位(虽然 Chaquopy 跑不了,留着兼容命令行调用)
        workDir.walkTopDown()
            .filter { it.isFile && it.name.endsWith(".sh") }
            .forEach { f -> f.setReadable(true, false); f.setWritable(true, false); f.setExecutable(true, false) }

        marker.writeText("bootstrapped at ${System.currentTimeMillis()}\n", Charsets.UTF_8)
        Log.i(TAG, "extracted $copied entries")
        return true
    }

    private fun copyDir(am: android.content.res.AssetManager, assetPath: String, dstDir: File) {
        if (!dstDir.exists()) dstDir.mkdirs()
        val list = am.list(assetPath) ?: return
        if (list.isEmpty()) {
            // 是文件,AssetManager.list 对文件返回空数组
            val out = File(dstDir, File(assetPath).name)
            am.open(assetPath).use { input ->
                FileOutputStream(out).use { output ->
                    input.copyTo(output)
                }
            }
            return
        }
        for (name in list) {
            val childAsset = "$assetPath/$name"
            val childDst = File(dstDir, name)
            // 递归 — AssetManager.list 对子目录会返回其中的文件/目录名
            val childList = am.list(childAsset) ?: emptyArray()
            if (childList.isNotEmpty()) {
                if (!childDst.exists()) childDst.mkdirs()
                copyDir(am, childAsset, childDst)
            } else {
                // 可能是文件,或空目录。AssetManager 没法区分,直接当文件拷
                am.open(childAsset).use { input ->
                    FileOutputStream(childDst).use { output ->
                        input.copyTo(output)
                    }
                }
            }
        }
    }

    /** 确保 output/{reports,logs,data} 子目录存在 */
    fun ensureOutputDirs(workDir: File) {
        for (sub in listOf("reports", "logs", "data")) {
            val d = File(workDir, "output/$sub")
            if (!d.exists()) d.mkdirs()
        }
    }
}