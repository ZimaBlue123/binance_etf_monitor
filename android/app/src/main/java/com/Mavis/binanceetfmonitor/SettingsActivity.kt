package com.Mavis.binanceetfmonitor

import android.app.AlertDialog
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/**
 * 设置页:两个子模块
 *  1. 定时任务 — 时间 + 是否仅工作日 + 保存/取消
 *  2. 基金列表 — 文本框 + 保存 + 复制粘贴
 */
class SettingsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)
        title = "设置"

        bindSchedule()
        bindFundList()
    }

    // ---- 定时任务 ----
    private lateinit var hourInput: EditText
    private lateinit var minuteInput: EditText
    private lateinit var weekdaysOnly: CheckBox
    private lateinit var nextTrigger: TextView
    private lateinit var saveScheduleButton: Button
    private lateinit var cancelScheduleButton: Button
    private lateinit var scheduleStatus: TextView

    private fun bindSchedule() {
        hourInput = findViewById(R.id.schedule_hour)
        minuteInput = findViewById(R.id.schedule_minute)
        weekdaysOnly = findViewById(R.id.schedule_weekdays_only)
        nextTrigger = findViewById(R.id.schedule_next_trigger)
        saveScheduleButton = findViewById(R.id.schedule_save)
        cancelScheduleButton = findViewById(R.id.schedule_cancel)
        scheduleStatus = findViewById(R.id.schedule_status)

        hourInput.inputType = InputType.TYPE_CLASS_NUMBER
        minuteInput.inputType = InputType.TYPE_CLASS_NUMBER

        // 初始值
        hourInput.setText(SettingsStore.getScheduleHour(this).toString())
        minuteInput.setText(SettingsStore.getScheduleMinute(this).toString())
        weekdaysOnly.isChecked = SettingsStore.getWeekdaysOnly(this)

        refreshScheduleStatus()

        saveScheduleButton.setOnClickListener { saveSchedule() }
        cancelScheduleButton.setOnClickListener { confirmDeleteSchedule() }

        // 输入时实时刷新下次触发预览
        val refresh = View.OnFocusChangeListener { _, _ -> refreshScheduleStatus() }
        hourInput.onFocusChangeListener = refresh
        minuteInput.onFocusChangeListener = refresh
        weekdaysOnly.setOnCheckedChangeListener { _, _ -> refreshScheduleStatus() }
    }

    private fun refreshScheduleStatus() {
        val h = hourInput.text.toString().toIntOrNull()?.coerceIn(0, 23) ?: SettingsStore.DEFAULT_HOUR
        val m = minuteInput.text.toString().toIntOrNull()?.coerceIn(0, 59) ?: SettingsStore.DEFAULT_MINUTE
        val w = weekdaysOnly.isChecked
        nextTrigger.text = "下次触发: ${ScheduleHelper.formatNextTrigger(h, m, w)}"
        val scheduled = ScheduleHelper.isScheduled(this)
        scheduleStatus.text = if (scheduled) "状态: 定时任务已启用" else "状态: 未启用定时"
    }

    private fun saveSchedule() {
        val h = hourInput.text.toString().toIntOrNull()?.coerceIn(0, 23) ?: return run {
            Toast.makeText(this, "小时必须是 0-23", Toast.LENGTH_SHORT).show()
        }
        val m = minuteInput.text.toString().toIntOrNull()?.coerceIn(0, 59) ?: return run {
            Toast.makeText(this, "分钟必须是 0-59", Toast.LENGTH_SHORT).show()
        }
        val w = weekdaysOnly.isChecked
        SettingsStore.setSchedule(this, h, m, w)
        ScheduleHelper.schedule(this)
        refreshScheduleStatus()
        Toast.makeText(this, "已保存:$h:$m " + (if (w) "(工作日)" else "(每天)"), Toast.LENGTH_LONG).show()
    }

    private fun confirmDeleteSchedule() {
        if (!ScheduleHelper.isScheduled(this)) {
            Toast.makeText(this, "当前没有启用的定时任务", Toast.LENGTH_SHORT).show()
            return
        }
        AlertDialog.Builder(this)
            .setTitle("删除定时任务?")
            .setMessage("确认要取消定时任务吗?取消后只手动点『运行监控』才会跑。")
            .setPositiveButton("删除") { _, _ ->
                ScheduleHelper.cancel(this)
                refreshScheduleStatus()
                Toast.makeText(this, "已删除定时任务", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("再想想", null)
            .show()
    }

    // ---- 基金列表 ----
    private lateinit var fundInput: EditText
    private lateinit var fundCountText: TextView
    private lateinit var fundSaveButton: Button
    private lateinit var fundPasteButton: Button
    private lateinit var fundClearButton: Button
    private lateinit var fundRestoreButton: Button

    private fun bindFundList() {
        fundInput = findViewById(R.id.fund_input)
        fundCountText = findViewById(R.id.fund_count)
        fundSaveButton = findViewById(R.id.fund_save)
        fundPasteButton = findViewById(R.id.fund_paste)
        fundClearButton = findViewById(R.id.fund_clear)
        fundRestoreButton = findViewById(R.id.fund_restore)

        fundInput.setText(SettingsStore.loadFundListText(this))
        refreshFundCount()

        fundSaveButton.setOnClickListener {
            try {
                val n = SettingsStore.saveFundList(this, fundInput.text.toString())
                refreshFundCount()
                Toast.makeText(this, "已保存 $n 只基金到监控列表", Toast.LENGTH_SHORT).show()
            } catch (t: Throwable) {
                Toast.makeText(this, "保存失败: ${t.message}", Toast.LENGTH_LONG).show()
            }
        }

        fundPasteButton.setOnClickListener {
            val cm = getSystemService(android.content.ClipboardManager::class.java)
            val clip = cm?.primaryClip
            val text = clip?.getItemAt(0)?.text?.toString().orEmpty()
            if (text.isBlank()) {
                Toast.makeText(this, "剪贴板为空", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            // 追加到现有内容(若用户已有数据,加换行)
            val current = fundInput.text.toString()
            fundInput.setText(if (current.isBlank()) text else "$current\n$text")
            fundInput.setSelection(fundInput.text.length)
            refreshFundCount()
            Toast.makeText(this, "已粘贴 ${text.lineSequence().count()} 行", Toast.LENGTH_SHORT).show()
        }

        fundClearButton.setOnClickListener {
            AlertDialog.Builder(this)
                .setTitle("清空基金列表?")
                .setMessage("清空只是『在编辑框里清掉』,没保存。\n真要恢复出厂默认,点右边的『恢复默认』。")
                .setPositiveButton("清空") { _, _ ->
                    fundInput.setText("")
                    refreshFundCount()
                }
                .setNegativeButton("取消", null)
                .show()
        }

        fundRestoreButton.setOnClickListener {
            AlertDialog.Builder(this)
                .setTitle("恢复默认基金列表?")
                .setMessage("这会覆盖你目前编辑的列表,恢复到 APK 内嵌的默认 30+ 只基金。继续?")
                .setPositiveButton("恢复") { _, _ ->
                    val n = SettingsStore.restoreDefaultFundList(this)
                    fundInput.setText(SettingsStore.loadFundListText(this))
                    refreshFundCount()
                    Toast.makeText(this, "已恢复默认 $n 只基金", Toast.LENGTH_SHORT).show()
                }
                .setNegativeButton("取消", null)
                .show()
        }
    }

    private fun refreshFundCount() {
        val text = fundInput.text.toString()
        val n = text.lineSequence().count { it.isNotBlank() }
        fundCountText.text = "当前 $n 条记录(每行: 基金代码,基金名称 — 复制粘贴后记得点保存)"
    }
}