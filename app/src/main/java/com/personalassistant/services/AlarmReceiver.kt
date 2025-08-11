package com.personalassistant.services

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log

class AlarmReceiver : BroadcastReceiver() {
    
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            ACTION_ALARM_TRIGGER -> {
                val alarmId = intent.getLongExtra(EXTRA_ALARM_ID, -1L)
                if (alarmId != -1L) {
                    startAlarmService(context, alarmId)
                }
            }
            ACTION_SNOOZE_ALARM -> {
                val alarmId = intent.getLongExtra(EXTRA_ALARM_ID, -1L)
                if (alarmId != -1L) {
                    startAlarmService(context, alarmId, ACTION_SNOOZE_ALARM)
                }
            }
            ACTION_DISMISS_ALARM -> {
                val alarmId = intent.getLongExtra(EXTRA_ALARM_ID, -1L)
                if (alarmId != -1L) {
                    startAlarmService(context, alarmId, ACTION_DISMISS_ALARM)
                }
            }
        }
    }
    
    private fun startAlarmService(context: Context, alarmId: Long, action: String = ACTION_TRIGGER_ALARM) {
        val serviceIntent = Intent(context, AlarmService::class.java).apply {
            this.action = action
            putExtra(EXTRA_ALARM_ID, alarmId)
        }
        
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent)
            } else {
                context.startService(serviceIntent)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start AlarmService", e)
        }
    }
    
    companion object {
        private const val TAG = "AlarmReceiver"
        
        const val ACTION_ALARM_TRIGGER = "com.personalassistant.TRIGGER_ALARM"
        const val ACTION_TRIGGER_ALARM = "com.personalassistant.TRIGGER_ALARM"
        const val ACTION_SNOOZE_ALARM = "com.personalassistant.SNOOZE_ALARM"
        const val ACTION_DISMISS_ALARM = "com.personalassistant.DISMISS_ALARM"
        const val EXTRA_ALARM_ID = "alarm_id"
    }
}
