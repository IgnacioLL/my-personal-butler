package com.personalassistant

import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.repositories.AlarmRepository
import com.personalassistant.domain.usecases.alarms.GetAlarmsUseCase
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Before
import org.junit.Test
import org.junit.Assert.assertEquals
import org.mockito.Mock
import org.mockito.MockitoAnnotations
import org.mockito.kotlin.whenever
import java.time.DayOfWeek
import java.time.LocalTime
import java.time.ZonedDateTime

class GetAlarmsUseCaseTest {
    
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
                days = setOf(DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY, DayOfWeek.FRIDAY),
                isEnabled = true
            ),
            Alarm(
                id = 2L,
                title = "Weekend Alarm",
                time = LocalTime.of(9, 0),
                days = setOf(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY),
                isEnabled = true
            )
        )
        
        whenever(mockAlarmRepository.getAlarms()).thenReturn(flowOf(expectedAlarms))
        
        // When
        val result = getAlarmsUseCase()
        
        // Then
        assertEquals(expectedAlarms, result.first())
    }
    
    @Test
    fun `invoke returns empty list when no alarms`() = runTest {
        // Given
        val emptyAlarms = emptyList<Alarm>()
        
        whenever(mockAlarmRepository.getAlarms()).thenReturn(flowOf(emptyAlarms))
        
        // When
        val result = getAlarmsUseCase()
        
        // Then
        assertEquals(emptyAlarms, result.first())
    }
}
