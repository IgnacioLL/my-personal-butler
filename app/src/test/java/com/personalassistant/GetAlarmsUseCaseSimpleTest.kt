package com.personalassistant

import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.repositories.AlarmRepository
import com.personalassistant.domain.usecases.alarms.GetAlarmsUseCase
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.Before
import org.junit.Test
import org.mockito.Mock
import org.mockito.MockitoAnnotations
import org.mockito.kotlin.whenever
import java.time.LocalTime
import java.time.ZonedDateTime
import kotlin.test.assertEquals

class GetAlarmsUseCaseSimpleTest {
    
    @Mock
    private lateinit var mockAlarmRepository: AlarmRepository
    
    private lateinit var getAlarmsUseCase: GetAlarmsUseCase
    
    @Before
    fun setup() {
        MockitoAnnotations.openMocks(this)
        getAlarmsUseCase = GetAlarmsUseCase(mockAlarmRepository)
    }
    
    @Test
    fun `invoke returns all alarms`() = runTest {
        // Given
        val expectedAlarms = listOf(
            Alarm(
                id = 1L,
                title = "Morning Alarm",
                time = LocalTime.of(7, 0),
                days = listOf(1, 2, 3, 4, 5), // Monday to Friday
                isEnabled = true
            ),
            Alarm(
                id = 2L,
                title = "Weekend Alarm",
                time = LocalTime.of(9, 0),
                days = listOf(6, 7), // Saturday and Sunday
                isEnabled = true
            )
        )
        
        whenever(mockAlarmRepository.getAlarms()).thenReturn(expectedAlarms)
        
        // When
        val result = getAlarmsUseCase()
        
        // Then
        assertEquals(expectedAlarms, result)
        assertEquals(2, result.size)
    }
    
    @Test
    fun `getEnabledAlarms returns only enabled alarms`() = runTest {
        // Given
        val enabledAlarms = listOf(
            Alarm(id = 1L, title = "Enabled Alarm", time = LocalTime.of(7, 0), isEnabled = true)
        )
        
        whenever(mockAlarmRepository.getEnabledAlarms()).thenReturn(enabledAlarms)
        
        // When
        val result = getAlarmsUseCase.getEnabledAlarms()
        
        // Then
        assertEquals(enabledAlarms, result)
        assertEquals(1, result.size)
    }
    
    @Test
    fun `getAlarmsForDay returns alarms for specific day`() = runTest {
        // Given
        val allAlarms = listOf(
            Alarm(
                id = 1L,
                title = "Monday Alarm",
                time = LocalTime.of(7, 0),
                days = listOf(1), // Monday only
                isEnabled = true
            ),
            Alarm(
                id = 2L,
                title = "Daily Alarm",
                time = LocalTime.of(8, 0),
                days = emptyList(), // Daily (empty list)
                isEnabled = true
            ),
            Alarm(
                id = 3L,
                title = "Tuesday Alarm",
                time = LocalTime.of(9, 0),
                days = listOf(2), // Tuesday only
                isEnabled = true
            )
        )
        
        whenever(mockAlarmRepository.getAlarms()).thenReturn(allAlarms)
        
        // When
        val mondayAlarms = getAlarmsUseCase.getAlarmsForDay(1) // Monday
        val tuesdayAlarms = getAlarmsUseCase.getAlarmsForDay(2) // Tuesday
        
        // Then
        assertEquals(2, mondayAlarms.size) // Monday alarm + daily alarm
        assertEquals(2, tuesdayAlarms.size) // Tuesday alarm + daily alarm
    }
    
    @Test
    fun `getAlarmsForTime returns alarms at specific time`() = runTest {
        // Given
        val enabledAlarms = listOf(
            Alarm(id = 1L, title = "7 AM Alarm", time = LocalTime.of(7, 0), isEnabled = true),
            Alarm(id = 2L, title = "8 AM Alarm", time = LocalTime.of(8, 0), isEnabled = true),
            Alarm(id = 3L, title = "Another 7 AM Alarm", time = LocalTime.of(7, 0), isEnabled = true)
        )
        
        whenever(mockAlarmRepository.getEnabledAlarms()).thenReturn(enabledAlarms)
        
        // When
        val sevenAMAlarms = getAlarmsUseCase.getAlarmsForTime(LocalTime.of(7, 0))
        val eightAMAlarms = getAlarmsUseCase.getAlarmsForTime(LocalTime.of(8, 0))
        
        // Then
        assertEquals(2, sevenAMAlarms.size)
        assertEquals(1, eightAMAlarms.size)
    }
}
