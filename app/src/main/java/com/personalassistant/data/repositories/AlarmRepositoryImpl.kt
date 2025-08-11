package com.personalassistant.data.repositories

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.work.WorkManager
import com.personalassistant.data.local.database.dao.AlarmDao
import com.personalassistant.data.local.database.entities.AlarmEntity
import com.personalassistant.data.local.database.mappers.AlarmMapper
import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.repositories.AlarmRepository
import com.personalassistant.services.AlarmReceiver
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AlarmRepositoryImpl @Inject constructor(
    private val alarmDao: AlarmDao,
    private val alarmManager: AlarmManager,
    private val context: Context,
    private val workManager: WorkManager
) : AlarmRepository {
    
    private val mapper = AlarmMapper()
    
    override suspend fun createAlarm(alarm: Alarm): Long {
        // Save to database first
        val alarmId = alarmDao.insert(mapper.toEntity(alarm))
        
        // Schedule in Android's AlarmManager
        val alarmWithId = alarm.copy(id = alarmId)
        scheduleAlarmInSystem(alarmWithId)
        
        return alarmId
    }
    
    override suspend fun getAlarms(): Flow<List<Alarm>> {
        return alarmDao.getAllAlarms().map { entities ->
            entities.map { mapper.toDomain(it) }
        }
    }
    
    override suspend fun getAlarmById(id: Long): Alarm? {
        val entity = alarmDao.getAlarmById(id)
        return entity?.let { mapper.toDomain(it) }
    }
    
    override suspend fun updateAlarm(alarm: Alarm) {
        alarmDao.update(mapper.toEntity(alarm))
        rescheduleAlarm(alarm)
    }
    
    override suspend fun deleteAlarm(id: Long) {
        cancelAlarmInSystem(id)
        val alarm = alarmDao.getAlarmById(id)
        alarm?.let { alarmDao.delete(it) }
    }
    
    override suspend fun enableAlarm(id: Long) {
        val alarm = alarmDao.getAlarmById(id)
        alarm?.let {
            alarmDao.update(it.copy(isEnabled = true))
            rescheduleAlarm(mapper.toDomain(it))
        }
    }
    
    override suspend fun disableAlarm(id: Long) {
        val alarm = alarmDao.getAlarmById(id)
        alarm?.let {
            alarmDao.update(it.copy(isEnabled = false))
            cancelAlarmInSystem(id)
        }
    }
    
    override suspend fun getNextAlarm(): Alarm? {
        val nextAlarmEntity = alarmDao.getNextEnabledAlarm()
        return nextAlarmEntity?.let { mapper.toDomain(it) }
    }
    
    override suspend fun scheduleAlarmInSystem(alarm: Alarm) {
        if (!alarm.isEnabled) return
        
        val triggerTime = calculateNextTriggerTime(alarm)
        val pendingIntent = createAlarmPendingIntent(alarm.id)
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            alarmManager.setExactAndAllowWhileIdle(
                AlarmManager.RTC_WAKEUP,
                triggerTime.toEpochMilli(),
                pendingIntent
            )
        } else {
            alarmManager.setExact(
                AlarmManager.RTC_WAKEUP,
                triggerTime.toEpochMilli(),
                pendingIntent
            )
        }
        
        // Update next trigger time in database
        val updatedAlarm = alarm.copy(nextTriggerTime = triggerTime)
        alarmDao.update(mapper.toEntity(updatedAlarm))
    }
    
    override suspend fun cancelAlarmInSystem(alarmId: Long) {
        val pendingIntent = createAlarmPendingIntent(alarmId)
        alarmManager.cancel(pendingIntent)
    }
    
    override suspend fun rescheduleAlarm(alarm: Alarm) {
        cancelAlarmInSystem(alarm.id)
        if (alarm.isEnabled) {
            scheduleAlarmInSystem(alarm)
        }
    }
    
    private fun calculateNextTriggerTime(alarm: Alarm): Instant {
        val now = Instant.now()
        val today = now.atZone(ZoneId.systemDefault()).toLocalDate()
        val targetTime = alarm.time
        
        // Calculate next occurrence
        var nextDate = today
        while (nextDate.atTime(targetTime).atZone(ZoneId.systemDefault()).toInstant().isBefore(now)) {
            nextDate = nextDate.plusDays(1)
        }
        
        // Handle recurring alarms
        if (alarm.isRepeating && alarm.days.isNotEmpty()) {
            nextDate = findNextRecurringDate(today, targetTime, alarm.days)
        }
        
        return nextDate.atTime(targetTime).atZone(ZoneId.systemDefault()).toInstant()
    }
    
    private fun findNextRecurringDate(
        fromDate: LocalDate,
        targetTime: LocalTime,
        days: Set<DayOfWeek>
    ): LocalDate {
        var currentDate = fromDate
        repeat(7) { // Check next 7 days
            if (days.contains(currentDate.dayOfWeek)) {
                val candidateTime = currentDate.atTime(targetTime)
                    .atZone(ZoneId.systemDefault()).toInstant()
                if (candidateTime.isAfter(Instant.now())) {
                    return currentDate
                }
            }
            currentDate = currentDate.plusDays(1)
        }
        return fromDate.plusDays(7) // Fallback
    }
    
    private fun createAlarmPendingIntent(alarmId: Long): PendingIntent {
        val intent = Intent(context, AlarmReceiver::class.java).apply {
            action = AlarmReceiver.ACTION_ALARM_TRIGGER
            putExtra(AlarmReceiver.EXTRA_ALARM_ID, alarmId)
        }
        
        return PendingIntent.getBroadcast(
            context,
            alarmId.toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }
}
