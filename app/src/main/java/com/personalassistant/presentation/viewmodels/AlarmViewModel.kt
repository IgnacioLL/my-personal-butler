package com.personalassistant.presentation.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.usecases.alarms.*
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.time.DayOfWeek
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import javax.inject.Inject

@HiltViewModel
class AlarmViewModel @Inject constructor(
    private val getAlarmsUseCase: GetAlarmsUseCase,
    private val createAlarmUseCase: CreateAlarmUseCase,
    private val updateAlarmUseCase: UpdateAlarmUseCase,
    private val deleteAlarmUseCase: DeleteAlarmUseCase,
    private val snoozeAlarmUseCase: SnoozeAlarmUseCase
) : ViewModel() {
    
    private val _uiState = MutableStateFlow<AlarmUiState>(AlarmUiState.Loading)
    val uiState: StateFlow<AlarmUiState> = _uiState.asStateFlow()
    
    private val _currentAlarm = MutableStateFlow<Alarm?>(null)
    val currentAlarm: StateFlow<Alarm?> = _currentAlarm.asStateFlow()
    
    init {
        loadAlarms()
    }
    
    fun loadAlarms() {
        viewModelScope.launch {
            try {
                _uiState.value = AlarmUiState.Loading
                getAlarmsUseCase().collect { alarms ->
                    _uiState.value = AlarmUiState.Success(alarms)
                }
            } catch (e: Exception) {
                _uiState.value = AlarmUiState.Error("Failed to load alarms: ${e.message}")
            }
        }
    }
    
    fun createAlarm(
        title: String,
        time: String,
        days: Set<DayOfWeek> = emptySet(),
        isRepeating: Boolean = false
    ) {
        viewModelScope.launch {
            try {
                val timeParts = time.split(":")
                val hour = timeParts[0].toInt()
                val minute = timeParts[1].toInt()
                val localTime = LocalTime.of(hour, minute)
                
                val alarm = Alarm(
                    title = title,
                    time = localTime,
                    days = days,
                    isRepeating = isRepeating
                )
                
                createAlarmUseCase(alarm)
                loadAlarms() // Refresh the list
            } catch (e: Exception) {
                _uiState.value = AlarmUiState.Error("Failed to create alarm: ${e.message}")
            }
        }
    }
    
    fun updateAlarm(alarm: Alarm) {
        viewModelScope.launch {
            try {
                updateAlarmUseCase(alarm)
                loadAlarms() // Refresh the list
            } catch (e: Exception) {
                _uiState.value = AlarmUiState.Error("Failed to update alarm: ${e.message}")
            }
        }
    }
    
    fun deleteAlarm(alarmId: Long) {
        viewModelScope.launch {
            try {
                deleteAlarmUseCase(alarmId)
                loadAlarms() // Refresh the list
            } catch (e: Exception) {
                _uiState.value = AlarmUiState.Error("Failed to delete alarm: ${e.message}")
            }
        }
    }
    
    fun toggleAlarm(alarm: Alarm) {
        val updatedAlarm = alarm.copy(isEnabled = !alarm.isEnabled)
        updateAlarm(updatedAlarm)
    }
    
    fun snoozeAlarm(alarm: Alarm) {
        viewModelScope.launch {
            try {
                snoozeAlarmUseCase(alarm)
            } catch (e: Exception) {
                _uiState.value = AlarmUiState.Error("Failed to snooze alarm: ${e.message}")
            }
        }
    }
    
    fun loadAlarm(alarmId: Long) {
        viewModelScope.launch {
            try {
                // For now, we'll get it from the current list
                // In the future, we could add a getAlarmById use case
                val alarms = getAlarmsUseCase().first()
                val alarm = alarms.find { it.id == alarmId }
                _currentAlarm.value = alarm
            } catch (e: Exception) {
                _uiState.value = AlarmUiState.Error("Failed to load alarm: ${e.message}")
            }
        }
    }
    
    fun dismissAlarm() {
        _currentAlarm.value = null
    }
    
    fun formatTime(time: LocalTime): String {
        return time.format(DateTimeFormatter.ofPattern("HH:mm"))
    }
    
    fun formatDays(days: Set<DayOfWeek>): String {
        if (days.isEmpty()) return "Once"
        
        val dayNames = days.map { it.name.lowercase().capitalize() }
        return dayNames.joinToString(", ")
    }
    
    private fun String.capitalize(): String {
        return if (isNotEmpty()) {
            this[0].uppercase() + substring(1)
        } else {
            this
        }
    }
}

sealed class AlarmUiState {
    object Loading : AlarmUiState()
    data class Success(val alarms: List<Alarm>) : AlarmUiState()
    data class Error(val message: String) : AlarmUiState()
}

