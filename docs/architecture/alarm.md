# Alarm Module Architecture

## Overview
The Alarm module provides a comprehensive alarm system with voice control integration, reliable scheduling, and reliable background processing. It follows Clean Architecture principles with MVVM pattern and integrates with the LLM system for natural language processing. The system uses Android's native AlarmManager for reliable alarm scheduling while maintaining a local database for alarm metadata and user preferences.

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
    val alarmDuration: Int = 60, // Duration of alarm in seconds
    val createdAt: Instant = Instant.now(),
    val updatedAt: Instant = Instant.now()
)
```

#### Use Cases
- **CreateAlarmUseCase.kt**: Create new alarms and schedule them in Android's AlarmManager
- **GetAlarmsUseCase.kt**: Retrieve alarm list from local database (since Android doesn't provide direct access to scheduled alarms)
- **UpdateAlarmUseCase.kt**: Update existing alarms and reschedule in AlarmManager
- **DeleteAlarmUseCase.kt**: Delete alarms and cancel from AlarmManager
- **TriggerAlarmUseCase.kt**: Handle alarm triggering
- **SnoozeAlarmUseCase.kt**: Handle snooze functionality with AlarmManager rescheduling
- **ParseVoiceCommandUseCase.kt**: Parse voice commands for alarms

#### Repository Interface
```kotlin
interface AlarmRepository {
    suspend fun getAlarms(): Flow<List<Alarm>>
    suspend fun getAlarmById(id: Long): Alarm?
    suspend fun updateAlarm(alarm: Alarm)
    suspend fun deleteAlarm(id: Long)
    suspend fun enableAlarm(id: Long)
    suspend fun disableAlarm(id: Long)
    suspend fun getNextAlarm(): Alarm?
    suspend fun scheduleAlarmInSystem(alarm: Alarm)
    suspend fun cancelAlarmInSystem(alarmId: Long)
    suspend fun rescheduleAlarm(alarm: Alarm)
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
    val alarmDuration: Int = 60, // Duration of alarm in seconds
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
    
    @Query("SELECT * FROM alarms WHERE isEnabled = 1 ORDER BY nextTriggerTime ASC LIMIT 1")
    suspend fun getNextEnabledAlarm(): AlarmEntity?
    
    @Query("SELECT * FROM alarms WHERE isEnabled = 1 AND nextTriggerTime IS NOT NULL ORDER BY nextTriggerTime ASC")
    suspend fun getEnabledAlarmsWithNextTrigger(): List<AlarmEntity>
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
    
    override suspend fun createAlarm(alarm: Alarm): Long {
        // Save to database first
        val alarmId = alarmDao.insert(alarm.toEntity())
        
        // Schedule in Android's AlarmManager
        val alarmWithId = alarm.copy(id = alarmId)
        scheduleAlarmInSystem(alarmWithId)
        
        return alarmId
    }
    
    override suspend fun getAlarms(): Flow<List<Alarm>> {
        return alarmDao.getAllAlarms().map { entities ->
            entities.map { it.toDomain() }
        }
    }
    
    override suspend fun updateAlarm(alarm: Alarm) {
        alarmDao.update(alarm.toEntity())
        rescheduleAlarm(alarm)
    }
    
    override suspend fun deleteAlarm(id: Long) {
        cancelAlarmInSystem(id)
        val alarm = alarmDao.getAlarmById(id)
        alarm?.let { alarmDao.delete(it) }
    }
    
    override suspend fun enableAlarm(id: Long) {
        val alarm = alarmDao.getAlarmById(id)
        alarm?.let {
            alarmDao.update(it.copy(isEnabled = true))
            rescheduleAlarm(it.toDomain())
        }
    }
    
    override suspend fun disableAlarm(id: Long) {
        val alarm = alarmDao.getAlarmById(id)
        alarm?.let {
            alarmDao.update(it.copy(isEnabled = false))
            cancelAlarmInSystem(id)
        }
    }
    
    override suspend fun getNextAlarm(): Alarm? {
        val nextAlarmEntity = alarmDao.getNextEnabledAlarm()
        return nextAlarmEntity?.toDomain()
    }
    
    override suspend fun scheduleAlarmInSystem(alarm: Alarm) {
        if (!alarm.isEnabled) return
        
        val triggerTime = calculateNextTriggerTime(alarm)
        val pendingIntent = createAlarmPendingIntent(alarm.id)
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            alarmManager.setExactAndAllowWhileIdle(
                AlarmManager.RTC_WAKEUP,
                triggerTime.toEpochMilli(),
                pendingIntent
            )
        } else {
            alarmManager.setExact(
                AlarmManager.RTC_WAKEUP,
                triggerTime.toEpochMilli(),
                pendingIntent
            )
        }
        
        // Update next trigger time in database
        val updatedAlarm = alarm.copy(nextTriggerTime = triggerTime)
        alarmDao.update(updatedAlarm.toEntity())
    }
    
    override suspend fun cancelAlarmInSystem(alarmId: Long) {
        val pendingIntent = createAlarmPendingIntent(alarmId)
        alarmManager.cancel(pendingIntent)
    }
    
    override suspend fun rescheduleAlarm(alarm: Alarm) {
        cancelAlarmInSystem(alarm.id)
        if (alarm.isEnabled) {
            scheduleAlarmInSystem(alarm)
        }
    }
    
    private fun calculateNextTriggerTime(alarm: Alarm): Instant {
        val now = Instant.now()
        val today = now.atZone(ZoneId.systemDefault()).toLocalDate()
        val targetTime = alarm.time
        
        // Calculate next occurrence
        var nextDate = today
        while (nextDate.atTime(targetTime).atZone(ZoneId.systemDefault()).toInstant().isBefore(now)) {
            nextDate = nextDate.plusDays(1)
        }
        
        // Handle recurring alarms
        if (alarm.isRepeating && alarm.days.isNotEmpty()) {
            nextDate = findNextRecurringDate(today, targetTime, alarm.days)
        }
        
        return nextDate.atTime(targetTime).atZone(ZoneId.systemDefault()).toInstant()
    }
    
    private fun findNextRecurringDate(
        fromDate: LocalDate,
        targetTime: LocalTime,
        days: Set<DayOfWeek>
    ): LocalDate {
        var currentDate = fromDate
        repeat(7) { // Check next 7 days
            if (days.contains(currentDate.dayOfWeek)) {
                val candidateTime = currentDate.atTime(targetTime)
                    .atZone(ZoneId.systemDefault()).toInstant()
                if (candidateTime.isAfter(Instant.now())) {
                    return currentDate
                }
            }
            currentDate = currentDate.plusDays(1)
        }
        return fromDate.plusDays(7) // Fallback
    }
    
    private fun createAlarmPendingIntent(alarmId: Long): PendingIntent {
        val intent = Intent(context, AlarmReceiver::class.java).apply {
            action = ACTION_ALARM_TRIGGER
            putExtra(EXTRA_ALARM_ID, alarmId)
        }
        
        return PendingIntent.getBroadcast(
            context,
            alarmId.toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }
}
```

### 4. Service Layer

#### AlarmReceiver.kt (BroadcastReceiver)
```kotlin
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            ACTION_ALARM_TRIGGER -> {
                val alarmId = intent.getLongExtra(EXTRA_ALARM_ID, -1)
                if (alarmId != -1) {
                    startAlarmService(context, alarmId)
                }
            }
        }
    }
    
    private fun startAlarmService(context: Context, alarmId: Long) {
        val serviceIntent = Intent(context, AlarmService::class.java).apply {
            action = ACTION_TRIGGER_ALARM
            putExtra(EXTRA_ALARM_ID, alarmId)
        }
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }
}
```

#### AlarmService.kt
```kotlin
@AndroidEntryPoint
class AlarmService : Service() {
    private val alarmRepository: AlarmRepository by inject()
    private val notificationManager: NotificationManager by lazy {
        getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    }
    
    private val mediaPlayer: MediaPlayer by lazy { MediaPlayer() }
    private val vibrator: Vibrator by lazy {
        getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
    }
    
    private var currentAlarm: Alarm? = null
    private var snoozeCount = 0
    
    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
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
        if (alarmId == -1) return
        
        runBlocking {
            currentAlarm = alarmRepository.getAlarmById(alarmId)
            currentAlarm?.let { alarm ->
                startForeground(ALARM_NOTIFICATION_ID, createAlarmNotification(alarm))
                playAlarmSound(alarm)
                startVibration(alarm)
                showAlarmActivity(alarm)
            }
        }
    }
    
    private fun handleAlarmSnooze(intent: Intent) {
        currentAlarm?.let { alarm ->
            if (snoozeCount < alarm.maxSnoozeCount) {
                snoozeCount++
                val snoozeTime = Instant.now().plus(alarm.snoozeDuration)
                
                // Schedule snooze alarm
                val snoozeAlarm = alarm.copy(
                    id = -snoozeCount, // Negative ID for snooze alarms
                    nextTriggerTime = snoozeTime
                )
                
                runBlocking {
                    alarmRepository.scheduleAlarmInSystem(snoozeAlarm)
                }
                
                stopAlarm()
            }
        }
    }
    
    private fun handleAlarmDismiss(intent: Intent) {
        stopAlarm()
        stopSelf()
    }
    
    private fun playAlarmSound(alarm: Alarm) {
        try {
            mediaPlayer.reset()
            if (alarm.ringtoneUri != null) {
                mediaPlayer.setDataSource(this, Uri.parse(alarm.ringtoneUri))
            } else {
                // Use default alarm sound
                mediaPlayer.setDataSource(this, Settings.System.DEFAULT_ALARM_ALERT_URI)
            }
            mediaPlayer.isLooping = true
            mediaPlayer.prepare()
            mediaPlayer.start()
        } catch (e: Exception) {
            Log.e(TAG, "Error playing alarm sound", e)
        }
    }
    
    private fun startVibration(alarm: Alarm) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val vibrationEffect = if (alarm.vibrationPattern != null) {
                VibrationEffect.createWaveform(alarm.vibrationPattern, -1)
            } else {
                VibrationEffect.createOneShot(1000, VibrationEffect.DEFAULT_AMPLITUDE)
            }
            vibrator.vibrate(vibrationEffect)
        } else {
            @Suppress("DEPRECATION")
            vibrator.vibrate(1000)
        }
    }
    
    private fun stopAlarm() {
        mediaPlayer.stop()
        mediaPlayer.release()
        vibrator.cancel()
        stopForeground(true)
    }
    
    private fun showAlarmActivity(alarm: Alarm) {
        val intent = Intent(this, AlarmActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(EXTRA_ALARM_ID, alarm.id)
        }
        startActivity(intent)
    }
    
    private fun createAlarmNotification(alarm: Alarm): Notification {
        val snoozeIntent = Intent(this, AlarmReceiver::class.java).apply {
            action = ACTION_SNOOZE_ALARM
            putExtra(EXTRA_ALARM_ID, alarm.id)
        }
        val snoozePendingIntent = PendingIntent.getBroadcast(
            this,
            alarm.id.toInt(),
            snoozeIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val dismissIntent = Intent(this, AlarmReceiver::class.java).apply {
            action = ACTION_DISMISS_ALARM
            putExtra(EXTRA_ALARM_ID, alarm.id)
        }
        val dismissPendingIntent = PendingIntent.getBroadcast(
            this,
            alarm.id.toInt(),
            dismissIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        return NotificationCompat.Builder(this, CHANNEL_ALARM)
            .setContentTitle(alarm.title)
            .setContentText("Time to wake up!")
            .setSmallIcon(R.drawable.ic_alarm)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(false)
            .setOngoing(true)
            .addAction(R.drawable.ic_snooze, "Snooze", snoozePendingIntent)
            .addAction(R.drawable.ic_dismiss, "Dismiss", dismissPendingIntent)
            .build()
    }
    
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ALARM,
                "Alarms",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Alarm notifications"
                enableLights(true)
                lightColor = Color.RED
                enableVibration(true)
            }
            notificationManager.createNotificationChannel(channel)
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        stopAlarm()
    }
    
    companion object {
        private const val TAG = "AlarmService"
        private const val ALARM_NOTIFICATION_ID = 1001
        const val CHANNEL_ALARM = "alarm_channel"
        
        const val ACTION_TRIGGER_ALARM = "com.personalassistant.TRIGGER_ALARM"
        const val ACTION_SNOOZE_ALARM = "com.personalassistant.SNOOZE_ALARM"
        const val ACTION_DISMISS_ALARM = "com.personalassistant.DISMISS_ALARM"
        const val EXTRA_ALARM_ID = "alarm_id"
    }
}
```

#### WorkManager Integration for Recurring Alarms
```kotlin
class RecurringAlarmWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {
    
    private val alarmRepository: AlarmRepository by inject()
    
    override suspend fun doWork(): Result {
        val alarmId = inputData.getLong(KEY_ALARM_ID, -1)
        if (alarmId == -1) return Result.failure()
        
        try {
            val alarm = alarmRepository.getAlarmById(alarmId)
            alarm?.let { 
                if (it.isRepeating && it.isEnabled) {
                    // Reschedule for next occurrence
                    alarmRepository.rescheduleAlarm(it)
                }
            }
            return Result.success()
        } catch (e: Exception) {
            return Result.failure()
        }
    }
    
    companion object {
        const val KEY_ALARM_ID = "alarm_id"
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
            "isRepeating": true
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

### 6. Alarm Activity for Full-Screen Display
```kotlin
@AndroidEntryPoint
class AlarmActivity : ComponentActivity() {
    private val viewModel: AlarmViewModel by viewModels()
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        val alarmId = intent.getLongExtra(EXTRA_ALARM_ID, -1)
        if (alarmId != -1) {
            viewModel.loadAlarm(alarmId)
        }
        
        setContent {
            PersonalAssistantTheme {
                AlarmScreen(
                    alarm = viewModel.currentAlarm.collectAsState().value,
                    onSnooze = { viewModel.snoozeAlarm() },
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
```

### 7. Notification System

#### Alarm Notification Manager
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

### 8. Alarm Scheduling Strategy

#### Scheduling Approach
The alarm system uses Android's AlarmManager for reliable scheduling:

1. **Exact Alarms**: Uses `setExactAndAllowWhileIdle()` for precise timing (Android 6.0+)
2. **Wake Lock**: Automatically acquires wake lock when alarm triggers
3. **Recurring Alarms**: Reschedules after each trigger for recurring alarms
4. **Snooze Handling**: Creates temporary alarms for snooze functionality

#### Alarm Persistence
- **Local Database**: Stores alarm metadata, preferences, and next trigger time
- **AlarmManager**: Handles actual scheduling and wake-up functionality
- **Boot Recovery**: Restores all enabled alarms after device reboot

### 9. Permissions and Manifest

#### Required Permissions
```xml
<uses-permission android:name="android.permission.SCHEDULE_EXACT_ALARM" />
<uses-permission android:name="android.permission.USE_EXACT_ALARM" />
<uses-permission android:name="android.permission.VIBRATE" />
<uses-permission android:name="android.permission.WAKE_LOCK" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
<uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
<uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
```

#### Manifest Components
```xml
<service
    android:name=".services.AlarmService"
    android:exported="false"
    android:foregroundServiceType="dataSync" />

<receiver
    android:name=".services.AlarmReceiver"
    android:exported="false" />

<receiver
    android:name=".services.BootReceiver"
    android:exported="false">
    <intent-filter>
        <action android:name="android.intent.action.BOOT_COMPLETED" />
    </intent-filter>
</receiver>

<activity
    android:name=".presentation.activities.AlarmActivity"
    android:exported="false"
    android:launchMode="singleTop"
    android:theme="@style/Theme.PersonalAssistant.Fullscreen" />
```

### 10. Boot Recovery
```kotlin
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            // Schedule work to restore alarms
            val workRequest = OneTimeWorkRequestBuilder<RestoreAlarmsWorker>()
                .setInitialDelay(30, TimeUnit.SECONDS) // Wait for system to be ready
                .build()
            
            WorkManager.getInstance(context).enqueue(workRequest)
        }
    }
}

class RestoreAlarmsWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {
    
    private val alarmRepository: AlarmRepository by inject()
    
    override suspend fun doWork(): Result {
        try {
            val alarms = alarmRepository.getAlarms().first()
            alarms.filter { it.isEnabled }.forEach { alarm ->
                alarmRepository.scheduleAlarmInSystem(alarm)
            }
            return Result.success()
        } catch (e: Exception) {
            return Result.failure()
        }
    }
}
```

### 11. Dependency Injection

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
    fun provideAlarmManager(context: Context): AlarmManager {
        return context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
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

### 12. Testing Strategy

#### Unit Tests
- **AlarmRepositoryTest.kt**: Repository logic testing with mocked AlarmManager
- **AlarmUseCaseTest.kt**: Use case testing
- **AlarmVoiceCommandParserTest.kt**: Voice command parsing
- **AlarmNotificationManagerTest.kt**: Notification testing

#### Integration Tests
- **AlarmServiceTest.kt**: Service integration testing
- **AlarmDatabaseTest.kt**: Database operations testing
- **AlarmManagerIntegrationTest.kt**: Android AlarmManager integration

#### UI Tests
- **AlarmsScreenTest.kt**: Compose UI testing
- **AlarmCardTest.kt**: Component testing

### 13. Error Handling

#### Alarm Exceptions
```kotlin
sealed class AlarmException : Exception() {
    data class InvalidTimeException(val time: String) : AlarmException()
    data class DuplicateAlarmException(val alarm: Alarm) : AlarmException()
    data class AlarmTriggerException(val alarmId: Long) : AlarmException()
    data class VoiceParseException(val command: String) : AlarmException()
    data class SchedulingException(val alarm: Alarm, val cause: Throwable) : AlarmException()
}
```

#### Error Recovery
- Retry mechanisms for failed scheduling operations
- Graceful degradation for advanced features
- User-friendly error messages
- Comprehensive logging for debugging
- Fallback to inexact alarms if exact alarms fail

### 14. Performance Considerations

#### Optimization Strategies
- Efficient database queries with indices on `nextTriggerTime` and `isEnabled`
- Background processing with WorkManager for recurring alarm rescheduling
- Battery optimization exceptions for alarm services
- Memory management for MediaPlayer and Vibrator
- Efficient alarm scheduling with batch operations

#### Monitoring
- Performance metrics tracking for alarm scheduling
- Battery usage monitoring
- Crash reporting
- User analytics for alarm usage patterns

### 15. Security and Privacy

#### Data Protection
- Local storage only (no cloud sync for alarms)
- Encrypted database for alarm data
- Secure alarm triggering with proper intent validation
- Privacy-compliant voice processing

#### Access Control
- App-level security with proper permission validation
- Secure service communication
- Protected broadcast intents

## Success Metrics

- **Reliability**: 99.9% alarm trigger success rate using Android's AlarmManager
- **Performance**: <100ms voice command processing
- **User Experience**: Intuitive voice commands and reliable alarm scheduling
- **Battery Impact**: <5% additional battery usage with proper wake lock management
- **Accuracy**: 95% voice command parsing accuracy
- **System Integration**: Seamless integration with Android's native alarm system
