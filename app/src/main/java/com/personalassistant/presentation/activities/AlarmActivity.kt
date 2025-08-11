package com.personalassistant.presentation.activities

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.personalassistant.presentation.compose.ui.theme.PersonalAssistantTheme
import com.personalassistant.presentation.viewmodels.AlarmViewModel
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class AlarmActivity : ComponentActivity() {
    
    private val viewModel: AlarmViewModel by viewModels()
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        val alarmId = intent.getLongExtra("alarm_id", -1L)
        if (alarmId != -1L) {
            viewModel.loadAlarm(alarmId)
        }
        
        setContent {
            PersonalAssistantTheme {
                AlarmScreen(
                    alarm = viewModel.currentAlarm.collectAsState().value,
                    onSnooze = { alarm -> viewModel.snoozeAlarm(alarm) },
                    onDismiss = { 
                        viewModel.dismissAlarm()
                        finish()
                    }
                )
            }
        }
        
        // Keep screen on
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
}

@Composable
fun AlarmScreen(
    alarm: com.personalassistant.domain.entities.Alarm?,
    onSnooze: (com.personalassistant.domain.entities.Alarm) -> Unit,
    onDismiss: () -> Unit
) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(32.dp)
        ) {
            // Time display
            Text(
                text = alarm?.time?.format(java.time.format.DateTimeFormatter.ofPattern("HH:mm")) ?: "00:00",
                style = MaterialTheme.typography.displayLarge,
                color = MaterialTheme.colorScheme.primary
            )
            
            // Title
            Text(
                text = alarm?.title ?: "Alarm",
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.onSurface
            )
            
            // Action buttons
            Row(
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Button(
                    onClick = { alarm?.let { onSnooze(it) } },
                    modifier = Modifier.size(120.dp, 48.dp)
                ) {
                    Text("Snooze")
                }
                
                Button(
                    onClick = onDismiss,
                    modifier = Modifier.size(120.dp, 48.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text("Dismiss")
                }
            }
        }
    }
}
