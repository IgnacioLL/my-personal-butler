package com.personalassistant.domain.entities

import java.time.DayOfWeek
import java.time.Duration
import java.time.Instant
import java.time.LocalTime

data class Alarm(
    val id: Long = 0,
    val title: String,
    val time: LocalTime,
    val days: Set<DayOfWeek> = emptySet(),
    val isEnabled: Boolean = true,
    val ringtoneUri: String? = null,
    val vibrationPattern: IntArray? = null,
    val snoozeDuration: Duration = Duration.ofMinutes(5),
    val maxSnoozeCount: Int = 3,
    val alarmDuration: Int = 60, // Duration of alarm in seconds
    val createdAt: Instant = Instant.now(),
    val updatedAt: Instant = Instant.now(),
    val nextTriggerTime: Instant? = null,
    val isRepeating: Boolean = false
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (javaClass != other?.javaClass) return false

        other as Alarm

        if (id != other.id) return false
        if (title != other.title) return false
        if (time != other.time) return false
        if (days != other.days) return false
        if (isEnabled != other.isEnabled) return false
        if (ringtoneUri != other.ringtoneUri) return false
        if (vibrationPattern != null) {
            if (other.vibrationPattern == null || !vibrationPattern.contentEquals(other.vibrationPattern)) return false
        } else if (other.vibrationPattern != null) return false
        if (snoozeDuration != other.snoozeDuration) return false
        if (maxSnoozeCount != other.maxSnoozeCount) return false
        if (alarmDuration != other.alarmDuration) return false
        if (createdAt != other.createdAt) return false
        if (updatedAt != other.updatedAt) return false
        if (nextTriggerTime != other.nextTriggerTime) return false
        if (isRepeating != other.isRepeating) return false

        return true
    }

    override fun hashCode(): Int {
        var result = id.hashCode()
        result = 31 * result + title.hashCode()
        result = 31 * result + time.hashCode()
        result = 31 * result + days.hashCode()
        result = 31 * result + isEnabled.hashCode()
        result = 31 * result + (ringtoneUri?.hashCode() ?: 0)
        result = 31 * result + (vibrationPattern?.contentHashCode() ?: 0)
        result = 31 * result + snoozeDuration.hashCode()
        result = 31 * result + maxSnoozeCount
        result = 31 * result + alarmDuration
        result = 31 * result + createdAt.hashCode()
        result = 31 * result + updatedAt.hashCode()
        result = 31 * result + (nextTriggerTime?.hashCode() ?: 0)
        result = 31 * result + isRepeating.hashCode()
        return result
    }
}
