package com.Mavis.binanceetfmonitor

import android.content.Context
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.TimeUnit

/**
 * 调度工具:把 SharedPreferences 里的(小时, 分钟, 是否仅工作日)转成
 * WorkManager PeriodicWorkRequest 的初始延迟。
 *
 * 设计:
 *  - WorkManager PeriodicWorkRequest 的周期最小是 15 分钟,只支持固定周期
 *  - 我们用 [1, TimeUnit.DAYS] + setInitialDelay 精挑到下一个工作日的指定时刻
 *  - 工作日判定:周一~周五;若今天就是工作日但已过设定时间,推到明天
 *  - 内部判定粒度精确到分钟
 */
object ScheduleHelper {

    private val tz: TimeZone get() = TimeZone.getTimeZone("Asia/Shanghai")

    /**
     * 注册(替换)周期任务。
     * ExistingPeriodicWorkPolicy.UPDATE:用户改时间后立即生效,不等当前周期跑完。
     */
    fun schedule(context: Context) {
        val h = SettingsStore.getScheduleHour(context)
        val m = SettingsStore.getScheduleMinute(context)
        val weekdaysOnly = SettingsStore.getWeekdaysOnly(context)
        val initialDelay = computeInitialDelayMs(h, m, weekdaysOnly)

        val req = PeriodicWorkRequestBuilder<MonitorWorker>(1, TimeUnit.DAYS)
            .setInitialDelay(initialDelay, TimeUnit.MILLISECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            MonitorWorker.NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            req,
        )
    }

    /**
     * 取消周期任务(用户主动删定时)
     */
    fun cancel(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(MonitorWorker.NAME)
    }

    fun isScheduled(context: Context): Boolean = MonitorWorker.isScheduled(context)

    /**
     * 计算到下次触发的延迟毫秒数。
     * - 周末模式(weekdaysOnly=true):下一个周一~周五的 h:m
     * - 每天模式(weekdaysOnly=false):明天的 h:m
     * - 当天未过 h:m 且为工作日:今天 h:m
     */
    fun computeInitialDelayMs(hour: Int, minute: Int, weekdaysOnly: Boolean): Long {
        val now = Calendar.getInstance(tz)
        val target = (now.clone() as Calendar).apply {
            set(Calendar.HOUR_OF_DAY, hour)
            set(Calendar.MINUTE, minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }

        // 推进到下一个合适的时刻
        var daysToAdd = 0
        repeat(8) {  // 最多循环 8 天,够从周日跨到周一
            val candidate = (now.clone() as Calendar).apply {
                add(Calendar.DAY_OF_YEAR, daysToAdd)
                set(Calendar.HOUR_OF_DAY, hour)
                set(Calendar.MINUTE, minute)
                set(Calendar.SECOND, 0)
                set(Calendar.MILLISECOND, 0)
            }
            if (weekdaysOnly) {
                val dow = candidate.get(Calendar.DAY_OF_WEEK)
                val isWeekend = (dow == Calendar.SATURDAY || dow == Calendar.SUNDAY)
                if (!isWeekend && candidate.timeInMillis > now.timeInMillis) {
                    return candidate.timeInMillis - now.timeInMillis
                }
            } else {
                if (candidate.timeInMillis > now.timeInMillis) {
                    return candidate.timeInMillis - now.timeInMillis
                }
            }
            daysToAdd++
        }
        // 兜底:返回 1 天
        return TimeUnit.DAYS.toMillis(1)
    }

    /**
     * 给人看的"下次触发时间"预览。
     */
    fun formatNextTrigger(hour: Int, minute: Int, weekdaysOnly: Boolean): String {
        val now = Calendar.getInstance(tz)
        var daysToAdd = 0
        val target = Calendar.getInstance(tz)
        repeat(8) {
            target.timeInMillis = now.timeInMillis
            target.add(Calendar.DAY_OF_YEAR, daysToAdd)
            target.set(Calendar.HOUR_OF_DAY, hour)
            target.set(Calendar.MINUTE, minute)
            target.set(Calendar.SECOND, 0)
            target.set(Calendar.MILLISECOND, 0)
            val isWeekend = (target.get(Calendar.DAY_OF_WEEK) == Calendar.SATURDAY ||
                target.get(Calendar.DAY_OF_WEEK) == Calendar.SUNDAY)
            if (target.timeInMillis > now.timeInMillis && (!weekdaysOnly || !isWeekend)) {
                return SimpleDateFormat("yyyy-MM-dd HH:mm (E)", Locale.getDefault())
                    .apply { timeZone = tz }
                    .format(target.time)
            }
            daysToAdd++
        }
        return "无法计算"
    }
}