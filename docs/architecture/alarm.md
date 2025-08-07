# Alarm Module Architecture

## Overview
The Alarm module provides a comprehensive alarm system with voice control integration, reliable scheduling, and reliable background processing. It follows Clean Architecture principles with MVVM pattern and integrates with the LLM system for natural language processing.

## Architecture Layers

### 1. Presentation Layer (UI)

#### Components
- **AlarmsScreen.kt**: Main Compose UI for alarm management
- **AlarmCard.kt**: Individual alarm display component
- **AlarmDialog.kt**: Create/edit alarm dialog
- **AlarmRingtonePicker.kt**: Ringtone selection component
- **AlarmNotification.kt**: Alarm notification UI

#### Features
- Material Design 3 (Material You) components
- Dark/Light theme support
- Accessibility features
- Haptic feedback
- Voice command integration

#### UI States
```kotlin
sealed class AlarmUiState {
    object Loading : AlarmUiState()
    data class Success(val alarms: List<Alarm>) : AlarmUiState()
    data class Error(val message: String) : AlarmUiState()
}
```

### 2. Domain Layer

#### Entities
```kotlin
data class Alarm(
    val id: Long = 0,
    val title: String,
    val time: LocalTime,
    val days: Set<DayOfWeek> = emptySet(),
    val isEnabled: Boolean = true,
    val ringtoneUri: String? = null,
    val vibrationPattern: IntArray? = null,
    val snoozeDuration: Duration = Duration.ofMinutes(5),
    val maxSnoozeCount: Int = 3,

    val createdAt: Instant = Instant.now(),
    val updatedAt: Instant = Instant.now()
)
```

#### Use Cases
- **CreateAlarmUseCase.kt**: Create new alarms
- **GetAlarmsUseCase.kt**: Retrieve alarm list
- **UpdateAlarmUseCase.kt**: Update existing alarms
- **DeleteAlarmUseCase.kt**: Delete alarms
- **TriggerAlarmUseCase.kt**: Handle alarm triggering
- **SnoozeAlarmUseCase.kt**: Handle snooze functionality
- **ParseVoiceCommandUseCase.kt**: Parse voice commands for alarms

#### Repository Interface
```kotlin
interface AlarmRepository {
    suspend fun createAlarm(alarm: Alarm): Long
    suspend fun getAlarms(): Flow<List<Alarm>>
    suspend fun getAlarmById(id: Long): Alarm?
    suspend fun updateAlarm(alarm: Alarm)
    suspend fun deleteAlarm(id: Long)
    suspend fun enableAlarm(id: Long)
    suspend fun disableAlarm(id: Long)
    suspend fun getNextAlarm(): Alarm?
}
```

### 3. Data Layer

#### Local Database (Room)
```kotlin
@Entity(tableName = "alarms")
data class AlarmEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val title: String,
    val time: String, // ISO time format
    val days: String, // JSON array of days
    val isEnabled: Boolean,
    val ringtoneUri: String?,
    val vibrationPattern: String?, // JSON array
    val snoozeDuration: Long, // milliseconds
    val maxSnoozeCount: Int,

    val createdAt: String, // ISO instant
    val updatedAt: String // ISO instant
)
```

#### DAO
```kotlin
@Dao
interface AlarmDao {
    @Insert
    suspend fun insert(alarm: AlarmEntity): Long
    
    @Query("SELECT * FROM alarms ORDER BY time ASC")
    fun getAllAlarms(): Flow<List<AlarmEntity>>
    
    @Query("SELECT * FROM alarms WHERE id = :id")
    suspend fun getAlarmById(id: Long): AlarmEntity?
    
    @Update
    suspend fun update(alarm: AlarmEntity)
    
    @Delete
    suspend fun delete(alarm: AlarmEntity)
    
    @Query("SELECT * FROM alarms WHERE isEnabled = 1 ORDER BY time ASC LIMIT 1")
    suspend fun getNextEnabledAlarm(): AlarmEntity?
}
```

#### Repository Implementation
```kotlin
@Singleton
class AlarmRepositoryImpl @Inject constructor(
    private val alarmDao: AlarmDao,
    private val alarmManager: AlarmManager,
    private val context: Context,
    private val workManager: WorkManager
) : AlarmRepository {
    // Implementation details
}
```

### 4. Service Layer

#### AlarmService.kt
```kotlin
@AndroidEntryPoint
class AlarmService : Service() {
    private val alarmManager: AlarmManager by lazy {
        getSystemService(Context.ALARM_SERVICE) as AlarmManager
    }
    
    private val mediaPlayer: MediaPlayer by lazy { MediaPlayer() }
    private val vibrator: Vibrator by lazy {
        getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_TRIGGER_ALARM -> handleAlarmTrigger(intent)
            ACTION_SNOOZE_ALARM -> handleAlarmSnooze(intent)
            ACTION_DISMISS_ALARM -> handleAlarmDismiss(intent)
        }
        return START_STICKY
    }
    
    private fun handleAlarmTrigger(intent: Intent) {
        val alarmId = intent.getLongExtra(EXTRA_ALARM_ID, -1)
        // Trigger alarm logic
    }
}
```

#### WorkManager Integration
```kotlin
class AlarmWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {
    
    override suspend fun doWork(): Result {
        val alarmId = inputData.getLong(KEY_ALARM_ID, -1)
        // Handle alarm logic
        return Result.success()
    }
}
```

### 5. Voice Command Integration

#### Voice Command Parser
```kotlin
class AlarmVoiceCommandParser @Inject constructor(
    private val openAIApi: OpenAIApi
) {
    suspend fun parseAlarmCommand(command: String): AlarmCommand {
        val prompt = buildAlarmPrompt(command)
        val response = openAIApi.processCommand(prompt)
        return parseAlarmResponse(response)
    }
    
    private fun buildAlarmPrompt(command: String): String {
        return """
        Parse the following voice command for alarm creation:
        Command: "$command"
        
        Extract the following information:
        - Time (24-hour format)
        - Days of week (if recurring)
        - Alarm title/label
        - Snooze preferences

        
        Return as JSON:
        {
            "time": "HH:MM",
            "days": ["MONDAY", "TUESDAY"],
            "title": "Wake up",
            "snoozeDuration": 5,

        }
        """.trimIndent()
    }
}
```

#### Supported Voice Commands
- "Wake me up at 7 AM"
- "Set alarm for 6:30 tomorrow"
- "Alarm in 30 minutes"
- "Daily alarm at 8 AM"
- "Weekday alarm at 7:30"
- "Snooze alarm"
- "Dismiss alarm"
- "Turn off alarm"



### 7. Notification System

#### Alarm Notification
```kotlin
class AlarmNotificationManager @Inject constructor(
    private val context: Context,
    private val notificationManager: NotificationManager
) {
    fun showAlarmNotification(alarm: Alarm) {
        val notification = NotificationCompat.Builder(context, CHANNEL_ALARM)
            .setContentTitle(alarm.title)
            .setContentText("Time to wake up!")
            .setSmallIcon(R.drawable.ic_alarm)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(false)
            .setOngoing(true)
            .addAction(R.drawable.ic_snooze, "Snooze", createSnoozePendingIntent(alarm.id))
            .addAction(R.drawable.ic_dismiss, "Dismiss", createDismissPendingIntent(alarm.id))
            .build()
        
        notificationManager.notify(alarm.id.toInt(), notification)
    }
}
```

### 8. Permissions and Manifest

#### Required Permissions
```xml
<uses-permission android:name="android.permission.SCHEDULE_EXACT_ALARM" />
<uses-permission android:name="android.permission.USE_EXACT_ALARM" />
<uses-permission android:name="android.permission.VIBRATE" />
<uses-permission android:name="android.permission.WAKE_LOCK" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
```

#### Manifest Components
```xml
<service
    android:name=".services.AlarmService"
    android:exported="false"
    android:foregroundServiceType="dataSync" />

<receiver
    android:name=".services.BootReceiver"
    android:exported="false">
    <intent-filter>
        <action android:name="android.intent.action.BOOT_COMPLETED" />
    </intent-filter>
</receiver>
```

### 9. Dependency Injection

#### Hilt Module
```kotlin
@Module
@InstallIn(SingletonComponent::class)
object AlarmModule {
    
    @Provides
    @Singleton
    fun provideAlarmDao(database: AppDatabase): AlarmDao {
        return database.alarmDao()
    }
    
    @Provides
    @Singleton
    fun provideAlarmRepository(
        alarmDao: AlarmDao,
        alarmManager: AlarmManager,
        context: Context,
        workManager: WorkManager
    ): AlarmRepository {
        return AlarmRepositoryImpl(alarmDao, alarmManager, context, workManager)
    }
    
    @Provides
    @Singleton
    fun provideAlarmVoiceCommandParser(
        openAIApi: OpenAIApi
    ): AlarmVoiceCommandParser {
        return AlarmVoiceCommandParser(openAIApi)
    }
}
```

### 10. Testing Strategy

#### Unit Tests
- **AlarmRepositoryTest.kt**: Repository logic testing
- **AlarmUseCaseTest.kt**: Use case testing
- **AlarmVoiceCommandParserTest.kt**: Voice command parsing
- **AlarmNotificationManagerTest.kt**: Notification testing

#### Integration Tests
- **AlarmServiceTest.kt**: Service integration testing
- **AlarmDatabaseTest.kt**: Database operations testing

#### UI Tests
- **AlarmsScreenTest.kt**: Compose UI testing
- **AlarmCardTest.kt**: Component testing

### 11. Error Handling

#### Alarm Exceptions
```kotlin
sealed class AlarmException : Exception() {
    data class InvalidTimeException(val time: String) : AlarmException()
    data class DuplicateAlarmException(val alarm: Alarm) : AlarmException()
    data class AlarmTriggerException(val alarmId: Long) : AlarmException()
    data class VoiceParseException(val command: String) : AlarmException()
}
```

#### Error Recovery
- Retry mechanisms for failed operations
- Graceful degradation for advanced features
- User-friendly error messages
- Logging for debugging

### 12. Performance Considerations

#### Optimization Strategies
- Efficient database queries with indices
- Background processing with WorkManager
- Battery optimization exceptions
- Memory management for MediaPlayer
- Efficient alarm scheduling

#### Monitoring
- Performance metrics tracking
- Battery usage monitoring
- Crash reporting
- User analytics

### 13. Security and Privacy

#### Data Protection
- Local storage only (no cloud sync for alarms)
- Encrypted database
- Secure alarm triggering
- Privacy-compliant voice processing

#### Access Control
- App-level security
- Permission validation
- Secure service communication

## Implementation Timeline

### Phase 1: Core Alarm System (Week 1-2)
- Basic alarm creation and management
- AlarmService implementation
- Database setup
- Basic UI

### Phase 2: Voice Integration (Week 3)
- Voice command parsing
- LLM integration
- Command execution

### Phase 3: Advanced Features (Week 4)
- Advanced scheduling
- Multiple alarm management
- Enhanced UI/UX

### Phase 4: Polish and Testing (Week 5)
- UI/UX improvements
- Comprehensive testing
- Performance optimization

## Success Metrics

- **Reliability**: 99.9% alarm trigger success rate
- **Performance**: <100ms voice command processing
- **User Experience**: Intuitive voice commands
- **Battery Impact**: <5% additional battery usage
- **Accuracy**: 95% voice command parsing accuracy
