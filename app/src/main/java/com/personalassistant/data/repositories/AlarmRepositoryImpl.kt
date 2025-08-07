package com.personalassistant.data.repositories

import com.personalassistant.data.local.database.dao.AlarmDao
import com.personalassistant.data.local.database.entities.AlarmEntity
import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.repositories.AlarmRepository
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject

class AlarmRepositoryImpl @Inject constructor(
    private val alarmDao: AlarmDao
) : AlarmRepository {
    
    override suspend fun getAlarms(): List<Alarm> {
        return alarmDao.getAllAlarms().map { it.toDomain() }
    }
    
    override suspend fun getAlarmsFlow(): Flow<List<Alarm>> {
        return alarmDao.getAllAlarmsFlow().map { entities ->
            entities.map { it.toDomain() }
        }
    }
    
    override suspend fun getAlarmById(id: Long): Alarm? {
        return alarmDao.getAlarmById(id)?.toDomain()
    }
    
    override suspend fun getEnabledAlarms(): List<Alarm> {
        return alarmDao.getEnabledAlarms().map { it.toDomain() }
    }
    
    override suspend fun createAlarm(alarm: Alarm): Long {
        val entity = AlarmEntity.fromDomain(alarm)
        return alarmDao.insertAlarm(entity)
    }
    
    override suspend fun updateAlarm(alarm: Alarm): Boolean {
        val entity = AlarmEntity.fromDomain(alarm)
        return alarmDao.updateAlarm(entity) > 0
    }
    
    override suspend fun deleteAlarm(id: Long): Boolean {
        return alarmDao.deleteAlarmById(id) > 0
    }
    
    override suspend fun enableAlarm(id: Long): Boolean {
        return alarmDao.enableAlarm(id) > 0
    }
    
    override suspend fun disableAlarm(id: Long): Boolean {
        return alarmDao.disableAlarm(id) > 0
    }
}
