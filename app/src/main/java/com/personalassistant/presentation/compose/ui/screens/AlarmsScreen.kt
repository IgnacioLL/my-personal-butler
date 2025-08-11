package com.personalassistant.presentation.compose.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.personalassistant.domain.entities.Alarm
import com.personalassistant.presentation.compose.ui.components.AlarmCard
import com.personalassistant.presentation.compose.ui.components.AlarmDialog
import com.personalassistant.presentation.viewmodels.AlarmViewModel
import com.personalassistant.presentation.viewmodels.AlarmUiState
import java.time.DayOfWeek

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AlarmsScreen(
    viewModel: AlarmViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    var showDialog by remember { mutableStateOf(false) }
    var editingAlarm by remember { mutableStateOf<Alarm?>(null) }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Alarms") }
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { 
                    editingAlarm = null
                    showDialog = true 
                }
            ) {
                Icon(Icons.Default.Add, contentDescription = "Add Alarm")
            }
        }
    ) { paddingValues ->
        when (uiState) {
            is AlarmUiState.Loading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
            
            is AlarmUiState.Success -> {
                val alarms = (uiState as AlarmUiState.Success).alarms
                
                if (alarms.isEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(paddingValues),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "No alarms set",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(paddingValues),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(alarms) { alarm ->
                            AlarmCard(
                                alarm = alarm,
                                onToggle = { viewModel.toggleAlarm(it) },
                                onEdit = { 
                                    editingAlarm = it
                                    showDialog = true 
                                },
                                onDelete = { viewModel.deleteAlarm(it.id) }
                            )
                        }
                    }
                }
            }
            
            is AlarmUiState.Error -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        Text(
                            text = "Error loading alarms",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.error
                        )
                        Text(
                            text = (uiState as AlarmUiState.Error).message,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Button(
                            onClick = { viewModel.loadAlarms() }
                        ) {
                            Text("Retry")
                        }
                    }
                }
            }
        }
    }
    
    // Alarm Dialog
    if (showDialog) {
        AlarmDialog(
            alarm = editingAlarm,
            onDismiss = { showDialog = false },
            onConfirm = { alarm ->
                if (editingAlarm != null) {
                    // Update existing alarm
                    viewModel.updateAlarm(alarm)
                } else {
                    // Create new alarm
                    viewModel.createAlarm(
                        alarm.title,
                        "${alarm.time.hour.toString().padStart(2, '0')}:${alarm.time.minute.toString().padStart(2, '0')}",
                        alarm.days,
                        alarm.isRepeating
                    )
                }
                showDialog = false
            }
        )
    }
}
