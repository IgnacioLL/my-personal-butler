package com.personalassistant.data.local.database.dao

import androidx.room.*
import com.personalassistant.data.local.database.entities.AlarmEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface AlarmDao {
    @Query("SELECT * FROM alarms ORDER BY time ASC")
    suspend fun getAllAlarms(): List<AlarmEntity>
    
    @Query("SELECT * FROM alarms ORDER BY time ASC")
    fun getAllAlarmsFlow(): Flow<List<AlarmEntity>>
    
    @Query("SELECT * FROM alarms WHERE id = :id")
    suspend fun getAlarmById(id: Long): AlarmEntity?
    
    @Query("SELECT * FROM alarms WHERE isEnabled = 1 ORDER BY time ASC")
    suspend fun getEnabledAlarms(): List<AlarmEntity>
    
    @Query("SELECT * FROM alarms WHERE isEnabled = 1 ORDER BY time ASC")
    fun getEnabledAlarmsFlow(): Flow<List<AlarmEntity>>
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAlarm(alarm: AlarmEntity): Long
    
    @Update
    suspend fun updateAlarm(alarm: AlarmEntity): Int
    
    @Delete
    suspend fun deleteAlarm(alarm: AlarmEntity): Int
    
    @Query("DELETE FROM alarms WHERE id = :id")
    suspend fun deleteAlarmById(id: Long): Int
    
    @Query("UPDATE alarms SET isEnabled = 1 WHERE id = :id")
    suspend fun enableAlarm(id: Long): Int
    
    @Query("UPDATE alarms SET isEnabled = 0 WHERE id = :id")
    suspend fun disableAlarm(id: Long): Int
    
    @Query("SELECT COUNT(*) FROM alarms")
    suspend fun getAlarmCount(): Int
    
    @Query("SELECT COUNT(*) FROM alarms WHERE isEnabled = 1")
    suspend fun getEnabledAlarmCount(): Int
}
