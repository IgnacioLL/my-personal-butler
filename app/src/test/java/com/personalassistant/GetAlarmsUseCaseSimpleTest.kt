package com.personalassistant

import com.personalassistant.domain.entities.Alarm
import com.personalassistant.domain.usecases.alarms.GetAlarmsUseCase
import com.personalassistant.domain.repositories.AlarmRepository
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.Test
import org.junit.Assert.*
import org.mockito.Mockito.mock
import org.mockito.Mockito.`when`
import java.time.LocalTime
import java.time.DayOfWeek

class GetAlarmsUseCaseSimpleTest {
    
    @Test
    fun `test get alarms returns list of alarms`() = runTest {
        // Given
        val mockRepository = mock<AlarmRepository>()
        val testAlarms = listOf(
            Alarm(
                id = 1L,
                title = "Wake up",
                time = LocalTime.of(7, 0),
                days = setOf(DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, DayOfWeek.THURSDAY, DayOfWeek.FRIDAY),
                isRepeating = true
            ),
            Alarm(
                id = 2L,
                title = "Weekend alarm",
                time = LocalTime.of(9, 0),
                days = setOf(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY),
                isRepeating = true
            )
        )
        
        `when`(mockRepository.getAlarms()).thenReturn(flowOf(testAlarms))
        
        val useCase = GetAlarmsUseCase(mockRepository)
        
        // When
        val result = useCase()
        
        // Then
        result.collect { alarms ->
            assertEquals(2, alarms.size)
            assertEquals("Wake up", alarms[0].title)
            assertEquals("Weekend alarm", alarms[1].title)
            assertTrue(alarms[0].isRepeating)
            assertTrue(alarms[1].isRepeating)
        }
    }
    
    @Test
    fun `test get alarms returns empty list when no alarms`() = runTest {
        // Given
        val mockRepository = mock<AlarmRepository>()
        `when`(mockRepository.getAlarms()).thenReturn(flowOf(emptyList()))
        
        val useCase = GetAlarmsUseCase(mockRepository)
        
        // When
        val result = useCase()
        
        // Then
        result.collect { alarms ->
            assertTrue(alarms.isEmpty())
        }
    }
}
