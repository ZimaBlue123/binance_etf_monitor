package com.Mavis.binanceetfmonitor

import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.ListView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 浏览历史报告 — 列出 output/reports 目录下的 markdown 文件,点击显示内容。
 *
 *  不做花哨的 Markdown 渲染:把 emoji 和粗体去掉,纯文本展示。
 *  真实手机上要专业渲染可后续集成 Markwon,这里以"能看"为先。
 */
class ReportActivity : AppCompatActivity() {

    private lateinit var listView: ListView
    private lateinit var contentView: TextView
    private var files: List<File> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_report)

        listView = findViewById(R.id.report_list)
        contentView = findViewById(R.id.report_content)

        listView.setOnItemClickListener { _: AdapterView<*>, _: View, position: Int, _: Long ->
            val f = files.getOrNull(position) ?: return@setOnItemClickListener
            showReport(f)
        }
    }

    override fun onResume() {
        super.onResume()
        loadReports()
    }

    private fun loadReports() {
        val reportsDir = File(filesDir, "project/output/reports")
        files = if (reportsDir.exists()) {
            (reportsDir.listFiles { f -> f.extension == "md" } ?: emptyArray())
                .sortedByDescending { it.lastModified() }
        } else {
            emptyList()
        }

        if (files.isEmpty()) {
            contentView.text = "还没有任何报告。\n回主页点『▶ 运行监控』生成第一份。"
            listView.adapter = null
            return
        }

        val df = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault())
        val labels = files.map { f ->
            val sizeKb = f.length() / 1024
            "${f.nameWithoutExtension.removePrefix("strategy_report_")}  ·  ${sizeKb}KB  ·  ${df.format(Date(f.lastModified()))}"
        }
        listView.adapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, labels)
        // 默认展示最新一份
        showReport(files.first())
    }

    private fun showReport(f: File) {
        try {
            val raw = f.readText(Charsets.UTF_8)
            // 简单去除 markdown 噪音
            val clean = raw
                .replace(Regex("""\*\*([^*]+)\*\*"""), "$1")  // 粗体
                .replace(Regex("""^#{1,6}\s*""", RegexOption.MULTILINE), "")  // 标题
                .replace(Regex("""`([^`]+)`"""), "$1")  // 行内 code
            contentView.text = clean
        } catch (t: Throwable) {
            contentView.text = "[读取失败] ${t.message}"
        }
    }
}