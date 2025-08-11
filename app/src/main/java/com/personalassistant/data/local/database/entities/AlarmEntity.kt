package com.personalassistant.data.local.database.entities

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "alarms")
data class AlarmEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val title: String,
    val time: String, // ISO time format
    val days: String, // JSON array of days
    val isEnabled: Boolean,
    val ringtoneUri: String?,
    val vibrationPattern: String?, // JSON array
    val snoozeDuration: Long, // milliseconds
    val maxSnoozeCount: Int,
    val alarmDuration: Int = 60, // Duration of alarm in seconds
    val createdAt: String, // ISO instant
    val updatedAt: String, // ISO instant
    val nextTriggerTime: String? = null, // ISO instant
    val isRepeating: Boolean = false
)
