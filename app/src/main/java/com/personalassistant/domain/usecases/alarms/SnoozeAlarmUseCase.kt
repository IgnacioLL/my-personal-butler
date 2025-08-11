package com.personalassistant.domain.usecases.alarms

import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.repositories.AlarmRepository
import java.time.Duration
import javax.inject.Inject

class SnoozeAlarmUseCase @Inject constructor(
    private val alarmRepository: AlarmRepository
) {
    suspend operator fun invoke(alarm: Alarm, snoozeDuration: Duration? = null) {
        val duration = snoozeDuration ?: alarm.snoozeDuration
        val snoozeTime = java.time.Instant.now().plus(duration)
        
        // Create a temporary snooze alarm
        val snoozeAlarm = alarm.copy(
            id = -alarm.id, // Negative ID for snooze alarms
            nextTriggerTime = snoozeTime
        )
        
        alarmRepository.scheduleAlarmInSystem(snoozeAlarm)
    }
}
