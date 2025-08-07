package com.personalassistant.domain.repositories

import com.personalassistant.domain.entities.Alarm
import kotlinx.coroutines.flow.Flow

interface AlarmRepository {
    suspend fun getAlarms(): List<Alarm>
    suspend fun getAlarmsFlow(): Flow<List<Alarm>>
    suspend fun getAlarmById(id: Long): Alarm?
    suspend fun getEnabledAlarms(): List<Alarm>
    suspend fun createAlarm(alarm: Alarm): Long
    suspend fun updateAlarm(alarm: Alarm): Boolean
    suspend fun deleteAlarm(id: Long): Boolean
    suspend fun enableAlarm(id: Long): Boolean
    suspend fun disableAlarm(id: Long): Boolean
}
