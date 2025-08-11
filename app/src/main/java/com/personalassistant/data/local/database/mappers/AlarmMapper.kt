package com.personalassistant.data.local.database.mappers

import com.personalassistant.data.local.database.entities.AlarmEntity
import com.personalassistant.domain.entities.Alarm
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.time.DayOfWeek
import java.time.Duration
import java.time.Instant
import java.time.LocalTime

class AlarmMapper {
    
    fun toEntity(alarm: Alarm): AlarmEntity {
        return AlarmEntity(
            id = alarm.id,
            title = alarm.title,
            time = alarm.time.toString(),
            days = Gson().toJson(alarm.days.map { it.name }),
            isEnabled = alarm.isEnabled,
            ringtoneUri = alarm.ringtoneUri,
            vibrationPattern = alarm.vibrationPattern?.let { Gson().toJson(it.toList()) },
            snoozeDuration = alarm.snoozeDuration.toMillis(),
            maxSnoozeCount = alarm.maxSnoozeCount,
            alarmDuration = alarm.alarmDuration,
            createdAt = alarm.createdAt.toString(),
            updatedAt = alarm.updatedAt.toString(),
            nextTriggerTime = alarm.nextTriggerTime?.toString(),
            isRepeating = alarm.isRepeating
        )
    }
    
    fun toDomain(entity: AlarmEntity): Alarm {
        return Alarm(
            id = entity.id,
            title = entity.title,
            time = LocalTime.parse(entity.time),
            days = parseDaysFromJson(entity.days),
            isEnabled = entity.isEnabled,
            ringtoneUri = entity.ringtoneUri,
            vibrationPattern = entity.vibrationPattern?.let { parseVibrationPatternFromJson(it) },
            snoozeDuration = Duration.ofMillis(entity.snoozeDuration),
            maxSnoozeCount = entity.maxSnoozeCount,
            alarmDuration = entity.alarmDuration,
            createdAt = Instant.parse(entity.createdAt),
            updatedAt = Instant.parse(entity.updatedAt),
            nextTriggerTime = entity.nextTriggerTime?.let { Instant.parse(it) },
            isRepeating = entity.isRepeating
        )
    }
    
    private fun parseDaysFromJson(daysJson: String): Set<DayOfWeek> {
        return try {
            val type = object : TypeToken<List<String>>() {}.type
            val dayNames: List<String> = Gson().fromJson(daysJson, type)
            dayNames.map { DayOfWeek.valueOf(it) }.toSet()
        } catch (e: Exception) {
            emptySet()
        }
    }
    
    private fun parseVibrationPatternFromJson(patternJson: String): IntArray {
        return try {
            val type = object : TypeToken<List<Int>>() {}.type
            val pattern: List<Int> = Gson().fromJson(patternJson, type)
            pattern.toIntArray()
        } catch (e: Exception) {
            intArrayOf(0, 1000, 500, 1000) // Default pattern
        }
    }
}
