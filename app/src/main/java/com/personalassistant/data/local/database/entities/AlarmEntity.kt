package com.personalassistant.data.local.database.entities

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.time.LocalTime
import java.time.ZonedDateTime

@Entity(tableName = "alarms")
data class AlarmEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val title: String,
    val time: String, // Stored as HH:mm:ss format
    val days: String, // JSON array of integers
    val isEnabled: Boolean = true,
    val ringtoneUri: String? = null,
    val vibrationPattern: String, // JSON array of longs
    val snoozeDuration: Int = 300,
    val maxSnoozeCount: Int = 3,
    val alarmDuration: Int = 60,
    val createdAt: String, // ISO 8601 format
    val updatedAt: String // ISO 8601 format
) {
    companion object {
        private val gson = Gson()
        
        fun fromDomain(alarm: com.personalassistant.domain.entities.Alarm): AlarmEntity {
            return AlarmEntity(
                id = alarm.id,
                title = alarm.title,
                time = alarm.time.toString(),
                days = gson.toJson(alarm.days),
                isEnabled = alarm.isEnabled,
                ringtoneUri = alarm.ringtoneUri,
                vibrationPattern = gson.toJson(alarm.vibrationPattern),
                snoozeDuration = alarm.snoozeDuration,
                maxSnoozeCount = alarm.maxSnoozeCount,
                alarmDuration = alarm.alarmDuration,
                createdAt = alarm.createdAt.toString(),
                updatedAt = alarm.updatedAt.toString()
            )
        }
        
        fun toDomain(): com.personalassistant.domain.entities.Alarm {
            val daysType = object : TypeToken<List<Int>>() {}.type
            val vibrationType = object : TypeToken<List<Long>>() {}.type
            
            return com.personalassistant.domain.entities.Alarm(
                id = id,
                title = title,
                time = LocalTime.parse(time),
                days = gson.fromJson(days, daysType) ?: emptyList(),
                isEnabled = isEnabled,
                ringtoneUri = ringtoneUri,
                vibrationPattern = gson.fromJson(vibrationPattern, vibrationType) ?: emptyList(),
                snoozeDuration = snoozeDuration,
                maxSnoozeCount = maxSnoozeCount,
                alarmDuration = alarmDuration,
                createdAt = ZonedDateTime.parse(createdAt),
                updatedAt = ZonedDateTime.parse(updatedAt)
            )
        }
    }
}
