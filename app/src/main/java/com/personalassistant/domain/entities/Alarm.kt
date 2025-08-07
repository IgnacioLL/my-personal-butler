package com.personalassistant.domain.entities

import java.time.LocalTime
import java.time.ZonedDateTime

data class Alarm(
    val id: Long = 0,
    val title: String,
    val time: LocalTime,
    val days: List<Int> = emptyList(), // 1=Monday, 2=Tuesday, etc.
    val isEnabled: Boolean = true,
    val ringtoneUri: String? = null,
    val vibrationPattern: List<Long> = emptyList(), // Vibration pattern in milliseconds
    val snoozeDuration: Int = 300, // in seconds
    val maxSnoozeCount: Int = 3,
    val alarmDuration: Int = 60, // Duration of alarm in seconds
    val createdAt: ZonedDateTime = ZonedDateTime.now(),
    val updatedAt: ZonedDateTime = ZonedDateTime.now()
)
