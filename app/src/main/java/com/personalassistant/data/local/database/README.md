# Database Setup Guide

## Overview
This directory contains the Room database implementation for the Personal Assistant app, specifically focused on the Alarm module.

## Components

### 1. AppDatabase
- Main database class that extends `RoomDatabase`
- Currently supports `AlarmEntity` table
- Version 1 with migration support ready

### 2. Entities
- `AlarmEntity`: Represents alarm data in the database
- Includes all necessary fields for alarm functionality
- Uses JSON serialization for complex data types

### 3. DAOs (Data Access Objects)
- `AlarmDao`: Provides CRUD operations for alarms
- Includes queries for enabled alarms and next trigger times
- Uses Flow for reactive data access

### 4. Mappers
- `AlarmMapper`: Converts between Entity and Domain objects
- Handles JSON parsing for complex fields
- Includes error handling for malformed data

### 5. Converters
- `Converters`: Room type converters for complex data types
- Supports List<String>, List<Int>, and Boolean conversions
- Uses Gson for JSON serialization

### 6. Migrations
- `Migration1to2`: Sample migration for future schema changes
- Currently empty but demonstrates the pattern

## Setup Instructions

### 1. Dependencies
Ensure these dependencies are in your `build.gradle`:
```gradle
implementation 'androidx.room:room-runtime:2.5.2'
implementation 'androidx.room:room-ktx:2.5.2'
implementation 'androidx.room:room-migration:2.5.2'
kapt 'androidx.room:room-compiler:2.5.2'
```

### 2. Hilt Integration
The database is integrated with Hilt through `DatabaseModule`:
- Provides `AppDatabase` instance
- Provides `AlarmDao` instance
- Both are singleton scoped

### 3. Usage in Repository
The `AlarmRepositoryImpl` uses the DAO for database operations:
```kotlin
@Inject
constructor(
    private val alarmDao: AlarmDao,
    private val alarmManager: AlarmManager,
    private val context: Context,
    private val workManager: WorkManager
)
```

## Database Schema

### Alarms Table
```sql
CREATE TABLE alarms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    time TEXT NOT NULL, -- ISO time format
    days TEXT, -- JSON array of days
    isEnabled INTEGER NOT NULL, -- 0 or 1
    ringtoneUri TEXT,
    vibrationPattern TEXT, -- JSON array
    snoozeDuration INTEGER NOT NULL, -- milliseconds
    maxSnoozeCount INTEGER NOT NULL,
    alarmDuration INTEGER NOT NULL DEFAULT 60, -- seconds
    createdAt TEXT NOT NULL, -- ISO instant
    updatedAt TEXT NOT NULL, -- ISO instant
    nextTriggerTime TEXT, -- ISO instant
    isRepeating INTEGER NOT NULL DEFAULT 0 -- 0 or 1
);
```

## Migration Strategy

### Current Version: 1
- Initial schema with all alarm fields
- No migrations needed yet

### Future Migrations
- Use `MIGRATION_1_2` as a template
- Add new migrations for each version increment
- Test migrations thoroughly before release

## Testing

### Unit Tests
- Test DAO operations with in-memory database
- Test mappers with various data scenarios
- Test converters with edge cases

### Integration Tests
- Test full database operations
- Test migration scenarios
- Test error handling

## Troubleshooting

### Common Issues
1. **Build Errors**: Ensure Room dependencies are correct
2. **Migration Errors**: Check migration version numbers
3. **Type Conversion Errors**: Verify converter implementations
4. **Performance Issues**: Check database indexing strategy

### Debug Tips
- Use Room's built-in logging: `Room.databaseBuilder().setLoggingQueryParameters(true)`
- Check generated code in `build/generated/source/kapt/`
- Verify database file location in device storage

## Future Enhancements

1. **Additional Entities**: Tasks, Calendar events, Call logs
2. **Database Indexing**: Performance optimization
3. **Backup/Restore**: User data management
4. **Sync**: Cloud database integration
5. **Encryption**: Sensitive data protection
