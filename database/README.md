# Personal Assistant Database Setup

This directory contains the PostgreSQL database setup for the Personal Assistant Android app.

## Database Overview

The database is designed to support all features of the Personal Assistant app:
- **Alarms**: Voice-controlled alarm system
- **Calendar Events**: Google Calendar integration
- **Calls**: Phone call monitoring and logging
- **Tasks**: TODO list management
- **Goals**: Long-term goal tracking
- **WhatsApp Messages**: WhatsApp chat monitoring
- **Voice Commands**: Voice command processing logs

## Quick Start

### Using Docker Compose (Recommended)

1. **Start the database:**
   ```bash
   docker-compose up -d
   ```

2. **Stop the database:**
   ```bash
   docker-compose down
   ```

3. **View logs:**
   ```bash
   docker-compose logs postgres
   ```

### Manual Setup

If you prefer to run PostgreSQL manually:

1. **Install PostgreSQL 15**
2. **Create database:**
   ```sql
   CREATE DATABASE personal_assistant;
   ```
3. **Run initialization scripts:**
   ```bash
   psql -U postgres -d personal_assistant -f database/init/01-init-schema.sql
   psql -U postgres -d personal_assistant -f database/init/02-sample-data.sql
   psql -U postgres -d personal_assistant -f database/init/03-connection-info.sql
   ```

## Connection Information

### Database Details
- **Host**: localhost
- **Port**: 5432
- **Database**: personal_assistant
- **Admin User**: assistant_user
- **Admin Password**: assistant_password

### Application User
- **Username**: assistant_app_user
- **Password**: app_password
- **Permissions**: SELECT, INSERT, UPDATE, DELETE

### Backup User
- **Username**: backup_user
- **Password**: backup_password
- **Permissions**: SELECT only

## Database Schema

### Tables

1. **alarms** - Alarm system data
   - id, title, time, days (JSON), is_enabled, ringtone_uri, etc.

2. **calendar_events** - Calendar integration
   - id, title, description, start_time, end_time, location, etc.

3. **calls** - Phone call monitoring
   - id, phone_number, contact_name, call_type, call_status, etc.

4. **tasks** - TODO list management
   - id, title, description, priority, status, due_date, etc.

5. **goals** - Long-term goal tracking
   - id, title, description, target_date, progress_percentage, etc.

6. **whatsapp_messages** - WhatsApp monitoring
   - id, sender, receiver, message_content, timestamp, etc.

7. **voice_commands** - Voice command processing logs
   - id, command_text, parsed_intent, parsed_entities, etc.

### Indexes
- Performance indexes on frequently queried columns
- Time-based indexes for alarms and events
- Status indexes for tasks and calls

## Web Interface

### pgAdmin Access
- **URL**: http://localhost:8080
- **Email**: admin@personalassistant.com
- **Password**: admin_password

### Adding Server in pgAdmin
1. Open pgAdmin
2. Right-click "Servers" → "Register" → "Server"
3. **General Tab:**
   - Name: Personal Assistant DB
4. **Connection Tab:**
   - Host: localhost
   - Port: 5432
   - Database: personal_assistant
   - Username: assistant_user
   - Password: assistant_password

## Android App Integration

### Connection String
```
jdbc:postgresql://localhost:5432/personal_assistant
```

### Environment Variables
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=personal_assistant
DB_USER=assistant_app_user
DB_PASSWORD=app_password
```

### Dependencies
Add to your Android app's `build.gradle`:
```gradle
implementation 'org.postgresql:postgresql:42.6.0'
implementation 'org.jetbrains.exposed:exposed-core:0.44.0'
implementation 'org.jetbrains.exposed:exposed-dao:0.44.0'
implementation 'org.jetbrains.exposed:exposed-jdbc:0.44.0'
```

## Backup and Restore

### Backup
```bash
docker exec personal-assistant-db pg_dump -U assistant_user personal_assistant > backup.sql
```

### Restore
```bash
docker exec -i personal-assistant-db psql -U assistant_user personal_assistant < backup.sql
```

## Troubleshooting

### Common Issues

1. **Port already in use:**
   ```bash
   sudo lsof -i :5432
   # Kill the process or change port in docker-compose.yml
   ```

2. **Permission denied:**
   ```bash
   sudo chown -R $USER:$USER database/
   ```

3. **Container won't start:**
   ```bash
   docker-compose logs postgres
   docker system prune -f
   ```

### Reset Database
```bash
docker-compose down -v
docker-compose up -d
```

## Security Notes

- Change default passwords in production
- Use environment variables for sensitive data
- Enable SSL for remote connections
- Regular security updates
- Backup strategy implementation

## Performance Tuning

- Monitor query performance with `EXPLAIN ANALYZE`
- Adjust PostgreSQL configuration for your workload
- Consider connection pooling for high-traffic apps
- Regular VACUUM and ANALYZE operations
