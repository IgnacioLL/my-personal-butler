package com.personalassistant.domain.usecases.alarms

import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.repositories.AlarmRepository
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject

class GetAlarmsUseCase @Inject constructor(
    private val alarmRepository: AlarmRepository
) {
    
    /**
     * Get all alarms
     * @return List of all alarms ordered by time
     */
    suspend operator fun invoke(): List<Alarm> {
        return alarmRepository.getAlarms()
    }
    
    /**
     * Get all alarms as a Flow for reactive updates
     * @return Flow of all alarms ordered by time
     */
    fun getAlarmsFlow(): Flow<List<Alarm>> {
        return alarmRepository.getAlarmsFlow()
    }
    
    /**
     * Get a specific alarm by ID
     * @param id The alarm ID
     * @return The alarm if found, null otherwise
     */
    suspend fun getAlarmById(id: Long): Alarm? {
        return alarmRepository.getAlarmById(id)
    }
    
    /**
     * Get only enabled alarms
     * @return List of enabled alarms ordered by time
     */
    suspend fun getEnabledAlarms(): List<Alarm> {
        return alarmRepository.getEnabledAlarms()
    }
    
    /**
     * Get alarms for a specific day of the week
     * @param dayOfWeek Day of week (1=Monday, 2=Tuesday, etc.)
     * @return List of alarms for the specified day
     */
    suspend fun getAlarmsForDay(dayOfWeek: Int): List<Alarm> {
        return alarmRepository.getAlarms().filter { alarm ->
            alarm.days.contains(dayOfWeek) || alarm.days.isEmpty()
        }
    }
    
    /**
     * Get alarms that should trigger at a specific time
     * @param time The time to check (in LocalTime format)
     * @return List of alarms that should trigger at the specified time
     */
    suspend fun getAlarmsForTime(time: java.time.LocalTime): List<Alarm> {
        return alarmRepository.getEnabledAlarms().filter { alarm ->
            alarm.time == time
        }
    }
}
