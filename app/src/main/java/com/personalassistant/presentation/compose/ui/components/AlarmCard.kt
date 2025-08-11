package com.personalassistant.presentation.compose.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.personalassistant.domain.entities.Alarm
import java.time.format.DateTimeFormatter

@Composable
fun AlarmCard(
    alarm: Alarm,
    onToggle: (Alarm) -> Unit,
    onEdit: (Alarm) -> Unit,
    onDelete: (Alarm) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Time display
            Column(
                modifier = Modifier.weight(1f)
            ) {
                Text(
                    text = alarm.time.format(DateTimeFormatter.ofPattern("HH:mm")),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold
                )
                
                Text(
                    text = alarm.title,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                
                if (alarm.isRepeating && alarm.days.isNotEmpty()) {
                    Text(
                        text = formatDays(alarm.days),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            
            // Toggle switch
            Switch(
                checked = alarm.isEnabled,
                onCheckedChange = { onToggle(alarm) }
            )
            
            // Action buttons
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                IconButton(onClick = { onEdit(alarm) }) {
                    Text("Edit")
                }
                
                IconButton(onClick = { onDelete(alarm) }) {
                    Text("Delete")
                }
            }
        }
    }
}

@Composable
private fun formatDays(days: Set<java.time.DayOfWeek>): String {
    if (days.isEmpty()) return "Once"
    
    val dayNames = days.map { 
        it.name.lowercase().replaceFirstChar { it.uppercase() }
    }
    return dayNames.joinToString(", ")
}
