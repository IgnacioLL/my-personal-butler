# PostgreSQL Database API

## Overview

The Personal Assistant app uses PostgreSQL as its primary database for storing all application data. The database is designed to support all features including alarms, calendar events, calls, tasks, goals, WhatsApp messages, and voice commands.

## Database Connection

### Connection Details
- **Host**: localhost
- **Port**: 5432
- **Database**: personal_assistant
- **Admin User**: assistant_user
- **Admin Password**: assistant_password
- **App User**: assistant_app_user
- **App Password**: app_password

### Connection String
```
jdbc:postgresql://localhost:5432/personal_assistant
```

## Database Schema

### Tables

#### 1. alarms
Stores alarm system data with voice control integration.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| title | VARCHAR(255) | Alarm title |
| time | TIME | Alarm time |
| days | JSONB | Array of days for recurring alarms |
| is_enabled | BOOLEAN | Whether alarm is active |
| ringtone_uri | VARCHAR(500) | Custom ringtone URI |
| vibration_pattern | JSONB | Vibration pattern array |
| snooze_duration | INTEGER | Snooze duration in seconds |
| max_snooze_count | INTEGER | Maximum snooze attempts |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### 2. calendar_events
Stores Google Calendar integration data.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| title | VARCHAR(255) | Event title |
| description | TEXT | Event description |
| start_time | TIMESTAMP | Event start time |
| end_time | TIMESTAMP | Event end time |
| location | VARCHAR(500) | Event location |
| is_all_day | BOOLEAN | All-day event flag |
| reminder_minutes | INTEGER | Reminder time in minutes |
| calendar_id | VARCHAR(255) | Google Calendar ID |
| event_id | VARCHAR(255) | Google Calendar Event ID |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### 3. calls
Stores phone call monitoring data.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| phone_number | VARCHAR(50) | Phone number |
| contact_name | VARCHAR(255) | Contact name |
| call_type | call_type | incoming/outgoing/missed |
| call_status | call_status | answered/rejected/missed/ended |
| start_time | TIMESTAMP | Call start time |
| end_time | TIMESTAMP | Call end time |
| duration_seconds | INTEGER | Call duration |
| is_whatsapp_call | BOOLEAN | WhatsApp call flag |
| notes | TEXT | Call notes |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### 4. tasks
Stores TODO list management data.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| title | VARCHAR(255) | Task title |
| description | TEXT | Task description |
| priority | task_priority | low/medium/high/urgent |
| status | task_status | pending/in_progress/completed/cancelled |
| due_date | TIMESTAMP | Task due date |
| completed_at | TIMESTAMP | Completion timestamp |
| category | VARCHAR(100) | Task category |
| tags | JSONB | Array of tags |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### 5. goals
Stores long-term goal tracking data.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| title | VARCHAR(255) | Goal title |
| description | TEXT | Goal description |
| target_date | TIMESTAMP | Goal target date |
| progress_percentage | INTEGER | Progress percentage (0-100) |
| is_completed | BOOLEAN | Completion flag |
| completed_at | TIMESTAMP | Completion timestamp |
| category | VARCHAR(100) | Goal category |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### 6. whatsapp_messages
Stores WhatsApp monitoring data.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| sender | VARCHAR(255) | Message sender |
| receiver | VARCHAR(255) | Message receiver |
| message_content | TEXT | Message content |
| message_type | VARCHAR(50) | text/image/video/audio/document |
| timestamp | TIMESTAMP | Message timestamp |
| is_incoming | BOOLEAN | Incoming message flag |
| chat_id | VARCHAR(255) | Chat identifier |
| message_id | VARCHAR(255) | WhatsApp message ID |
| created_at | TIMESTAMP | Creation timestamp |

#### 7. voice_commands
Stores voice command processing logs.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| command_text | TEXT | Original voice command |
| parsed_intent | VARCHAR(100) | Extracted intent |
| parsed_entities | JSONB | Extracted entities |
| success | BOOLEAN | Processing success flag |
| error_message | TEXT | Error message if failed |
| processing_time_ms | INTEGER | Processing time in milliseconds |
| created_at | TIMESTAMP | Creation timestamp |

## Custom Types

### Enums

#### alarm_recurrence
- none
- daily
- weekly
- monthly
- yearly

#### task_priority
- low
- medium
- high
- urgent

#### task_status
- pending
- in_progress
- completed
- cancelled

#### call_type
- incoming
- outgoing
- missed

#### call_status
- answered
- rejected
- missed
- ended

## Indexes

### Performance Indexes
- `idx_alarms_time` - Alarm time queries
- `idx_alarms_enabled` - Enabled alarms filter
- `idx_calendar_events_start_time` - Event time queries
- `idx_calls_start_time` - Call time queries
- `idx_calls_phone_number` - Phone number lookups
- `idx_tasks_due_date` - Task due date queries
- `idx_tasks_status` - Task status filter
- `idx_goals_target_date` - Goal target date queries
- `idx_whatsapp_messages_timestamp` - Message time queries
- `idx_voice_commands_created_at` - Command time queries

## Triggers

### Automatic Timestamp Updates
All tables have triggers that automatically update the `updated_at` column when records are modified.

## Sample Queries

### Get All Active Alarms
```sql
SELECT * FROM alarms WHERE is_enabled = true ORDER BY time;
```

### Get Today's Calendar Events
```sql
SELECT * FROM calendar_events 
WHERE DATE(start_time) = CURRENT_DATE 
ORDER BY start_time;
```

### Get Pending Tasks
```sql
SELECT * FROM tasks 
WHERE status = 'pending' 
ORDER BY due_date;
```

### Get Recent Calls
```sql
SELECT * FROM calls 
WHERE start_time >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY start_time DESC;
```

### Get Voice Commands by Intent
```sql
SELECT command_text, parsed_entities, processing_time_ms 
FROM voice_commands 
WHERE parsed_intent = 'create_alarm' 
ORDER BY created_at DESC;
```

## Android Integration

### Dependencies
```gradle
implementation 'org.postgresql:postgresql:42.6.0'
implementation 'org.jetbrains.exposed:exposed-core:0.44.0'
implementation 'org.jetbrains.exposed:exposed-dao:0.44.0'
implementation 'org.jetbrains.exposed:exposed-jdbc:0.44.0'
```

### Connection Configuration
```kotlin
val database = Database.connect(
    url = "jdbc:postgresql://localhost:5432/personal_assistant",
    driver = "org.postgresql.Driver",
    user = "assistant_app_user",
    password = "app_password"
)
```

### Environment Variables
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=personal_assistant
DB_USER=assistant_app_user
DB_PASSWORD=app_password
```

## Security Considerations

1. **Connection Security**
   - Use SSL for production connections
   - Implement connection pooling
   - Use environment variables for credentials

2. **Data Protection**
   - Encrypt sensitive data at rest
   - Implement row-level security if needed
   - Regular security audits

3. **Access Control**
   - Use dedicated app user with minimal permissions
   - Implement proper authentication
   - Monitor database access logs

## Backup and Recovery

### Automated Backup
```bash
# Create backup
docker exec personal-assistant-db pg_dump -U assistant_user personal_assistant > backup.sql

# Restore backup
docker exec -i personal-assistant-db psql -U assistant_user personal_assistant < backup.sql
```

### Backup Schedule
- Daily incremental backups
- Weekly full backups
- Monthly archive backups

## Performance Optimization

### Query Optimization
- Use prepared statements
- Implement proper indexing
- Monitor slow queries
- Regular VACUUM and ANALYZE

### Connection Management
- Use connection pooling
- Implement connection timeouts
- Monitor connection usage

## Monitoring

### Key Metrics
- Query performance
- Connection count
- Disk usage
- Memory usage
- Backup success rate

### Alerts
- Database unavailable
- High disk usage
- Slow query performance
- Backup failures
