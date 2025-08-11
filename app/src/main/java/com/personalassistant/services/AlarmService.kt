package com.personalassistant.services

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.media.MediaPlayer
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import android.util.Log
import androidx.core.app.NotificationCompat
import com.personalassistant.R
import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.repositories.AlarmRepository
import com.personalassistant.presentation.activities.AlarmActivity
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.runBlocking
import javax.inject.Inject

@AndroidEntryPoint
class AlarmService : Service() {
    
    @Inject
    lateinit var alarmRepository: AlarmRepository
    
    private val notificationManager: NotificationManager by lazy {
        getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    }
    
    private val mediaPlayer: MediaPlayer by lazy { MediaPlayer() }
    private val vibrator: Vibrator by lazy {
        getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
    }
    
    private var currentAlarm: Alarm? = null
    private var snoozeCount = 0
    
    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            AlarmReceiver.ACTION_TRIGGER_ALARM -> handleAlarmTrigger(intent)
            AlarmReceiver.ACTION_SNOOZE_ALARM -> handleAlarmSnooze(intent)
            AlarmReceiver.ACTION_DISMISS_ALARM -> handleAlarmDismiss(intent)
        }
        return START_STICKY
    }
    
    private fun handleAlarmTrigger(intent: Intent) {
        val alarmId = intent.getLongExtra(AlarmReceiver.EXTRA_ALARM_ID, -1L)
        if (alarmId == -1L) return
        
        runBlocking {
            currentAlarm = alarmRepository.getAlarmById(alarmId)
            currentAlarm?.let { alarm ->
                startForeground(ALARM_NOTIFICATION_ID, createAlarmNotification(alarm))
                playAlarmSound(alarm)
                startVibration(alarm)
                showAlarmActivity(alarm)
            }
        }
    }
    
    private fun handleAlarmSnooze(intent: Intent) {
        currentAlarm?.let { alarm ->
            if (snoozeCount < alarm.maxSnoozeCount) {
                snoozeCount++
                val snoozeTime = java.time.Instant.now().plus(alarm.snoozeDuration)
                
                // Schedule snooze alarm
                val snoozeAlarm = alarm.copy(
                    id = -snoozeCount.toLong(), // Negative ID for snooze alarms
                    nextTriggerTime = snoozeTime
                )
                
                runBlocking {
                    alarmRepository.scheduleAlarmInSystem(snoozeAlarm)
                }
                
                stopAlarm()
            }
        }
    }
    
    private fun handleAlarmDismiss(intent: Intent) {
        stopAlarm()
        stopSelf()
    }
    
    private fun playAlarmSound(alarm: Alarm) {
        try {
            mediaPlayer.reset()
            if (alarm.ringtoneUri != null) {
                mediaPlayer.setDataSource(this, Uri.parse(alarm.ringtoneUri))
            } else {
                // Use default alarm sound
                mediaPlayer.setDataSource(this, Settings.System.DEFAULT_ALARM_ALERT_URI)
            }
            mediaPlayer.isLooping = true
            mediaPlayer.prepare()
            mediaPlayer.start()
        } catch (e: Exception) {
            Log.e(TAG, "Error playing alarm sound", e)
        }
    }
    
    private fun startVibration(alarm: Alarm) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val vibrationEffect = if (alarm.vibrationPattern != null) {
                VibrationEffect.createWaveform(alarm.vibrationPattern.map { it.toLong() }.toLongArray(), -1)
            } else {
                VibrationEffect.createOneShot(1000, VibrationEffect.DEFAULT_AMPLITUDE)
            }
            vibrator.vibrate(vibrationEffect)
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(1000)
        }
    }
    
    private fun stopAlarm() {
        try {
            if (mediaPlayer.isPlaying) {
                mediaPlayer.stop()
            }
            mediaPlayer.release()
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping media player", e)
        }
        
        try {
            vibrator.cancel()
        } catch (e: Exception) {
            Log.e(TAG, "Error canceling vibration", e)
        }
        
        stopForeground(true)
    }
    
    private fun showAlarmActivity(alarm: Alarm) {
        val intent = Intent(this, AlarmActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(AlarmReceiver.EXTRA_ALARM_ID, alarm.id)
        }
        startActivity(intent)
    }
    
    private fun createAlarmNotification(alarm: Alarm): Notification {
        val snoozeIntent = Intent(this, AlarmReceiver::class.java).apply {
            action = AlarmReceiver.ACTION_SNOOZE_ALARM
            putExtra(AlarmReceiver.EXTRA_ALARM_ID, alarm.id)
        }
        val snoozePendingIntent = PendingIntent.getBroadcast(
            this,
            alarm.id.toInt(),
            snoozeIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val dismissIntent = Intent(this, AlarmReceiver::class.java).apply {
            action = AlarmReceiver.ACTION_DISMISS_ALARM
            putExtra(AlarmReceiver.EXTRA_ALARM_ID, alarm.id)
        }
        val dismissPendingIntent = PendingIntent.getBroadcast(
            this,
            alarm.id.toInt(),
            dismissIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        return NotificationCompat.Builder(this, CHANNEL_ALARM)
            .setContentTitle(alarm.title)
            .setContentText("Time to wake up!")
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(false)
            .setOngoing(true)
            .addAction(android.R.drawable.ic_menu_revert, "Snooze", snoozePendingIntent)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Dismiss", dismissPendingIntent)
            .build()
    }
    
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ALARM,
                "Alarms",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Alarm notifications"
                enableLights(true)
                lightColor = Color.RED
                enableVibration(true)
            }
            notificationManager.createNotificationChannel(channel)
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        stopAlarm()
    }
    
    override fun onBind(intent: Intent?): IBinder? = null
    
    companion object {
        private const val TAG = "AlarmService"
        private const val ALARM_NOTIFICATION_ID = 1001
        const val CHANNEL_ALARM = "alarm_channel"
    }
}
