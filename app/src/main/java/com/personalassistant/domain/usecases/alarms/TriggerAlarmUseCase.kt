package com.personalassistant.domain.usecases.alarms

import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.repositories.AlarmRepository
import javax.inject.Inject

class TriggerAlarmUseCase @Inject constructor(
    private val alarmRepository: AlarmRepository
) {
    suspend operator fun invoke(alarm: Alarm) {
        // This use case can be used for manual alarm triggering
        // The actual triggering is handled by the AlarmService
        // This could be used for testing or manual override
    }
}
