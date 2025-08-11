package com.personalassistant.presentation.compose.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.personalassistant.domain.entities.Alarm
import java.time.DayOfWeek
import java.time.Duration
import java.time.LocalTime

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AlarmDialog(
    onDismiss: () -> Unit,
    onConfirm: (Alarm) -> Unit,
    alarm: Alarm? = null,
    modifier: Modifier = Modifier
) {
    var title by remember { mutableStateOf(alarm?.title ?: "") }
    var time by remember { mutableStateOf(alarm?.time ?: LocalTime.of(7, 0)) }
    var isRepeating by remember { mutableStateOf(alarm?.isRepeating ?: false) }
    var selectedDays by remember { mutableStateOf(alarm?.days ?: emptySet()) }
    var snoozeDuration by remember { mutableStateOf(alarm?.snoozeDuration?.toMinutes()?.toInt() ?: 5) }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (alarm == null) "Add Alarm" else "Edit Alarm") },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Title input
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Alarm Title") },
                    modifier = Modifier.fillMaxWidth()
                )
                
                // Time picker (simplified - in real app would use TimePicker)
                Text("Time: ${time?.format(java.time.format.DateTimeFormatter.ofPattern("HH:mm"))}")
                Button(
                    onClick = { /* TODO: Show time picker */ },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Set Time")
                }
                
                // Repeating toggle
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Checkbox(
                        checked = isRepeating,
                        onCheckedChange = { isRepeating = it }
                    )
                    Text("Repeat")
                }
                
                // Day selection
                if (isRepeating) {
                    Text("Repeat on:", style = MaterialTheme.typography.bodyMedium)
                    DayOfWeek.values().forEach { day ->
                        Row(
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Checkbox(
                                checked = selectedDays.contains(day),
                                onCheckedChange = { checked ->
                                    selectedDays = if (checked) {
                                        selectedDays.toMutableSet().apply { add(day) }.toSet()
                                    } else {
                                        selectedDays.toMutableSet().apply { remove(day) }.toSet()
                                    }
                                }
                            )
                            Text(day.name.take(3))
                        }
                    }
                }
                
                // Snooze duration
                Text("Snooze duration: ${snoozeDuration} minutes")
                Slider(
                    value = snoozeDuration.toFloat(),
                    onValueChange = { snoozeDuration = it.toInt() },
                    valueRange = 1f..30f,
                    steps = 29
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val newAlarm = Alarm(
                        id = alarm?.id ?: 0,
                        title = title.ifEmpty { "Alarm" },
                        time = time ?: LocalTime.of(7, 0),
                        days = selectedDays,
                        isRepeating = isRepeating,
                        snoozeDuration = Duration.ofMinutes(snoozeDuration.toLong())
                    )
                    onConfirm(newAlarm)
                },
                enabled = title.isNotBlank()
            ) {
                Text(if (alarm == null) "Add" else "Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}
