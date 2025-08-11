package com.personalassistant.services

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class BootReceiver : BroadcastReceiver() {
    
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            // Schedule work to restore alarms
            val workRequest = OneTimeWorkRequestBuilder<RestoreAlarmsWorker>()
                .setInitialDelay(30, TimeUnit.SECONDS) // Wait for system to be ready
                .build()
            
            WorkManager.getInstance(context).enqueue(workRequest)
        }
    }
}
