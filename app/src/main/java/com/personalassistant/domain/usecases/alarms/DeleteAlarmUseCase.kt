package com.personalassistant.domain.usecases.alarms

import com.personalassistant.domain.repositories.AlarmRepository
import javax.inject.Inject

class DeleteAlarmUseCase @Inject constructor(
    private val alarmRepository: AlarmRepository
) {
    suspend operator fun invoke(alarmId: Long) {
        alarmRepository.deleteAlarm(alarmId)
    }
}
