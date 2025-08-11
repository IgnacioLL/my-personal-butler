package com.personalassistant.domain.repositories

import com.personalassistant.domain.entities.Alarm
import kotlinx.coroutines.flow.Flow

interface AlarmRepository {
    suspend fun createAlarm(alarm: Alarm): Long
    suspend fun getAlarms(): Flow<List<Alarm>>
    suspend fun getAlarmById(id: Long): Alarm?
    suspend fun updateAlarm(alarm: Alarm)
    suspend fun deleteAlarm(id: Long)
    suspend fun enableAlarm(id: Long)
    suspend fun disableAlarm(id: Long)
    suspend fun getNextAlarm(): Alarm?
    suspend fun scheduleAlarmInSystem(alarm: Alarm)
    suspend fun cancelAlarmInSystem(alarmId: Long)
    suspend fun rescheduleAlarm(alarm: Alarm)
}
