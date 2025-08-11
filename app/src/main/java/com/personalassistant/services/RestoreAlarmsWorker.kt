package com.personalassistant.services

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.personalassistant.domain.repositories.AlarmRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.flow.first

@HiltWorker
class RestoreAlarmsWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val alarmRepository: AlarmRepository
) : CoroutineWorker(context, params) {
    
    override suspend fun doWork(): Result {
        return try {
            val alarms = alarmRepository.getAlarms().first()
            alarms.filter { it.isEnabled }.forEach { alarm ->
                alarmRepository.scheduleAlarmInSystem(alarm)
            }
            Result.success()
        } catch (e: Exception) {
            Result.failure()
        }
    }
}
