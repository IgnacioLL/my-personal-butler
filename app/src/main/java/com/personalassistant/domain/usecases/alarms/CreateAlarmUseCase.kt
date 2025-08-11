package com.personalassistant.domain.usecases.alarms

import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.repositories.AlarmRepository
import javax.inject.Inject

class CreateAlarmUseCase @Inject constructor(
    private val alarmRepository: AlarmRepository
) {
    suspend operator fun invoke(alarm: Alarm): Long {
        return alarmRepository.createAlarm(alarm)
    }
}
