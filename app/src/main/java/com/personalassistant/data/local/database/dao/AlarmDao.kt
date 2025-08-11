package com.personalassistant.data.local.database.dao

import androidx.room.*
import com.personalassistant.data.local.database.entities.AlarmEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface AlarmDao {
    @Insert
    suspend fun insert(alarm: AlarmEntity): Long
    
    @Query("SELECT * FROM alarms ORDER BY time ASC")
    fun getAllAlarms(): Flow<List<AlarmEntity>>
    
    @Query("SELECT * FROM alarms WHERE id = :id")
    suspend fun getAlarmById(id: Long): AlarmEntity?
    
    @Update
    suspend fun update(alarm: AlarmEntity)
    
    @Delete
    suspend fun delete(alarm: AlarmEntity)
    
    @Query("SELECT * FROM alarms WHERE isEnabled = 1 ORDER BY nextTriggerTime ASC LIMIT 1")
    suspend fun getNextEnabledAlarm(): AlarmEntity?
    
    @Query("SELECT * FROM alarms WHERE isEnabled = 1 AND nextTriggerTime IS NOT NULL ORDER BY nextTriggerTime ASC")
    suspend fun getEnabledAlarmsWithNextTrigger(): List<AlarmEntity>
    
    @Query("SELECT * FROM alarms WHERE isEnabled = 1")
    suspend fun getEnabledAlarms(): List<AlarmEntity>
}
