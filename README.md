# Personal Assistant Android App

A voice-controlled Android personal assistant that integrates WhatsApp monitoring, phone call management, calendar scheduling, alarm functionality, and TODO/goals tracking using cloud LLMs and speech-to-text processing.

## 🎯 Project Overview

This app transforms your Android device into a comprehensive personal assistant that can:
- Monitor WhatsApp chats and calls through accessibility services
- Track phone calls and provide call screening
- Manage Google Calendar with Gmail integration
- Set and manage alarms with voice commands
- Create and track TODO lists and personal goals
- Process all interactions through natural language voice commands

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│  │   Activities│ │   Fragments │ │   Compose   │        │
│  │             │ │             │ │   UI        │        │
│  └─────────────┘ └─────────────┘ └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Domain Layer                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│  │   Use Cases │ │   Entities  │ │  Repositories│        │
│  │             │ │             │ │  Interfaces │        │
│  └─────────────┘ └─────────────┘ └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Data Layer                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│  │ PostgreSQL  │ │   Local     │ │   Remote    │        │
│  │   Database  │ │   Storage   │ │    APIs     │        │
│  └─────────────┘ └─────────────┘ └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

## 📋 Requirements

### System Requirements
- **Android Version**: API 24+ (Android 7.0)
- **RAM**: Minimum 4GB, Recommended 6GB+
- **Storage**: 500MB for app + 2GB for database
- **Internet**: Required for LLM API calls and Google services

### Development Requirements
- **Android Studio**: Arctic Fox or later
- **Kotlin**: 1.8.0+
- **JDK**: 11 or higher
- **Gradle**: 7.0+

### API Keys & Services
- **AssemblyAI**: Speech-to-text processing
- **OpenAI/Anthropic**: LLM API for natural language processing
- **Google Calendar API**: Calendar management
- **Gmail API**: Email integration
- **PostgreSQL**: Database hosting

## 🏛️ Code Structure

```
app/
├── src/
│   ├── main/
│   │   ├── java/com/personalassistant/
│   │   │   ├── presentation/
│   │   │   │   ├── activities/
│   │   │   │   │   ├── MainActivity.kt
│   │   │   │   │   ├── VoiceCommandActivity.kt
│   │   │   │   │   └── SettingsActivity.kt
│   │   │   │   ├── fragments/
│   │   │   │   │   ├── DashboardFragment.kt
│   │   │   │   │   ├── CalendarFragment.kt
│   │   │   │   │   ├── CallsFragment.kt
│   │   │   │   │   ├── TasksFragment.kt
│   │   │   │   │   └── AlarmsFragment.kt
│   │   │   │   ├── compose/
│   │   │   │   │   ├── ui/
│   │   │   │   │   │   ├── theme/
│   │   │   │   │   │   ├── components/
│   │   │   │   │   │   └── screens/
│   │   │   │   │   └── viewmodels/
│   │   │   │   └── adapters/
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   ├── Call.kt
│   │   │   │   │   ├── CalendarEvent.kt
│   │   │   │   │   ├── Task.kt
│   │   │   │   │   ├── Goal.kt
│   │   │   │   │   └── Alarm.kt
│   │   │   │   ├── usecases/
│   │   │   │   │   ├── calls/
│   │   │   │   │   │   ├── GetCallsUseCase.kt
│   │   │   │   │   │   ├── MonitorCallsUseCase.kt
│   │   │   │   │   │   └── ScreenCallUseCase.kt
│   │   │   │   │   ├── calendar/
│   │   │   │   │   │   ├── CreateEventUseCase.kt
│   │   │   │   │   │   ├── GetEventsUseCase.kt
│   │   │   │   │   │   └── SyncGmailUseCase.kt
│   │   │   │   │   ├── tasks/
│   │   │   │   │   │   ├── CreateTaskUseCase.kt
│   │   │   │   │   │   ├── GetTasksUseCase.kt
│   │   │   │   │   │   └── UpdateTaskUseCase.kt
│   │   │   │   │   └── alarms/
│   │   │   │   │       ├── CreateAlarmUseCase.kt
│   │   │   │   │       ├── GetAlarmsUseCase.kt
│   │   │   │   │       └── TriggerAlarmUseCase.kt
│   │   │   │   └── repositories/
│   │   │   │       ├── CallRepository.kt
│   │   │   │       ├── CalendarRepository.kt
│   │   │   │       ├── TaskRepository.kt
│   │   │   │       └── AlarmRepository.kt
│   │   │   ├── data/
│   │   │   │   ├── local/
│   │   │   │   │   ├── database/
│   │   │   │   │   │   ├── AppDatabase.kt
│   │   │   │   │   │   ├── dao/
│   │   │   │   │   │   └── entities/
│   │   │   │   │   └── preferences/
│   │   │   │   ├── remote/
│   │   │   │   │   ├── api/
│   │   │   │   │   │   ├── AssemblyAIApi.kt
│   │   │   │   │   │   ├── OpenAIApi.kt
│   │   │   │   │   │   ├── GoogleCalendarApi.kt
│   │   │   │   │   │   └── GmailApi.kt
│   │   │   │   │   ├── dto/
│   │   │   │   │   └── network/
│   │   │   │   └── repositories/
│   │   │   │       ├── CallRepositoryImpl.kt
│   │   │   │       ├── CalendarRepositoryImpl.kt
│   │   │   │       ├── TaskRepositoryImpl.kt
│   │   │   │       └── AlarmRepositoryImpl.kt
│   │   │   ├── services/
│   │   │   │   ├── WhatsAppMonitorService.kt
│   │   │   │   ├── CallScreeningService.kt
│   │   │   │   ├── VoiceProcessingService.kt
│   │   │   │   ├── AlarmService.kt
│   │   │   │   └── NotificationListenerService.kt
│   │   │   ├── utils/
│   │   │   │   ├── VoiceCommandParser.kt
│   │   │   │   ├── PermissionManager.kt
│   │   │   │   ├── DatabaseHelper.kt
│   │   │   │   └── NetworkUtils.kt
│   │   │   └── di/
│   │   │       └── AppModule.kt
│   │   ├── res/
│   │   │   ├── layout/
│   │   │   ├── values/
│   │   │   ├── drawable/
│   │   │   └── menu/
│   │   └── AndroidManifest.xml
│   └── test/
└── build.gradle
```

## 🔧 Key Components

### 1. Presentation Layer
- **Activities**: Main entry points and navigation
- **Fragments**: Feature-specific UI components
- **Jetpack Compose**: Modern UI toolkit for complex interfaces
- **ViewModels**: State management and business logic
- **Adapters**: RecyclerView adapters for lists

### 2. Domain Layer
- **Entities**: Core business objects (Call, Task, Event, etc.)
- **Use Cases**: Business logic and feature operations
- **Repository Interfaces**: Data access contracts

### 3. Data Layer
- **Local Storage**: SharedPreferences for settings
- **Remote APIs**: External service integrations
- **Repository Implementations**: Data access implementations

### 4. Services
- **Accessibility Services**: WhatsApp and system monitoring
- **Background Services**: Voice processing and alarms
- **Notification Listeners**: Call and message monitoring

## 🚀 Setup Instructions

### 1. Environment Setup
```bash
# Clone the repository
git clone https://github.com/yourusername/personal-assistant-android.git
cd personal-assistant-android

# Open in Android Studio
# Sync Gradle files
```

### 2. API Configuration
Create `local.properties` file:
```properties
# AssemblyAI
ASSEMBLY_AI_API_KEY=your_assembly_ai_key

# OpenAI
OPENAI_API_KEY=your_openai_key

# Google APIs
GOOGLE_CALENDAR_CLIENT_ID=your_google_client_id
GOOGLE_GMAIL_CLIENT_ID=your_google_client_id

# PostgreSQL
POSTGRESQL_URL=your_database_url
POSTGRESQL_USERNAME=your_username
POSTGRESQL_PASSWORD=your_password
```

### 3. Database Setup
```sql
-- Create PostgreSQL database
CREATE DATABASE personal_assistant;

-- Tables will be created by Room migrations
```

### 4. Permissions Setup
Add to `AndroidManifest.xml`:
```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.READ_CALL_LOG" />
<uses-permission android:name="android.permission.READ_PHONE_STATE" />
<uses-permission android:name="android.permission.READ_CALENDAR" />
<uses-permission android:name="android.permission.WRITE_CALENDAR" />
<uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" />
<uses-permission android:name="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE" />
<uses-permission android:name="android.permission.BIND_ACCESSIBILITY_SERVICE" />
```

## 📱 Features Implementation

### Voice Processing Pipeline
1. **Audio Capture**: Continuous microphone monitoring
2. **AssemblyAI**: Real-time speech-to-text conversion
3. **LLM Processing**: Natural language understanding
4. **Action Execution**: Feature-specific operations
5. **Feedback**: Voice or visual confirmation

### Data Flow
```
Voice Input → AssemblyAI → LLM API → Use Case → Repository → Database/API
```

### Background Services
- **VoiceProcessingService**: Continuous voice monitoring
- **WhatsAppMonitorService**: Accessibility-based monitoring
- **CallScreeningService**: Call management
- **AlarmService**: Alarm triggering
- **NotificationListenerService**: System notification monitoring

## 🛠️ Development Guidelines

### Code Style
- Follow Kotlin coding conventions
- Use meaningful variable and function names
- Add comprehensive comments for complex logic
- Implement proper error handling

### Architecture Principles
- **Single Responsibility**: Each class has one purpose
- **Dependency Injection**: Use Hilt for DI
- **Repository Pattern**: Abstract data sources
- **MVVM**: Separate UI logic from business logic

### Testing Strategy
- **Unit Tests**: Use Cases and Repositories
- **Integration Tests**: API and database operations
- **UI Tests**: Critical user flows
- **Accessibility Tests**: Service functionality

## 🔒 Security & Privacy

### Data Protection
- All sensitive data encrypted at rest
- API keys stored securely using Android Keystore
- Local processing when possible
- Clear privacy policy and user consent

### Permissions Management
- Request permissions only when needed
- Explain permission usage clearly
- Handle permission denial gracefully
- Provide alternative functionality when possible

## 📊 Performance Considerations

### Optimization Strategies
- **Database**: Efficient queries and indexing
- **Network**: Request caching and compression
- **Memory**: Proper lifecycle management
- **Battery**: Background service optimization

### Monitoring
- **Crash Reporting**: Firebase Crashlytics
- **Performance**: Firebase Performance Monitoring
- **Analytics**: User behavior tracking (anonymized)

## 🚀 Deployment

### Release Process
1. **Testing**: Comprehensive testing on multiple devices
2. **Staging**: Beta testing with limited users
3. **Production**: Gradual rollout to users
4. **Monitoring**: Post-release performance tracking

### Distribution
- **Google Play Store**: Primary distribution channel
- **Internal Testing**: Developer and QA testing
- **Beta Testing**: Limited external testing

## 🤝 Contributing

### Development Workflow
1. Create feature branch from `develop`
2. Implement feature with tests
3. Submit pull request
4. Code review and approval
5. Merge to `develop`
6. Release to `main`

### Code Review Checklist
- [ ] Code follows style guidelines
- [ ] Tests are included and passing
- [ ] Documentation is updated
- [ ] Security considerations addressed
- [ ] Performance impact assessed

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the [Wiki](wiki/) for detailed documentation
- Review the [FAQ](docs/FAQ.md) for common questions

---

**Note**: This app requires significant permissions and handles sensitive data. Ensure compliance with local privacy laws and provide clear user communication about data usage.
