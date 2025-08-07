-- Personal Assistant Database Schema
-- This script initializes the database schema for the Personal Assistant Android app

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create custom types
CREATE TYPE alarm_recurrence AS ENUM ('none', 'daily', 'weekly', 'monthly', 'yearly');
CREATE TYPE task_priority AS ENUM ('low', 'medium', 'high', 'urgent');
CREATE TYPE task_status AS ENUM ('pending', 'in_progress', 'completed', 'cancelled');
CREATE TYPE call_type AS ENUM ('incoming', 'outgoing', 'missed');
CREATE TYPE call_status AS ENUM ('answered', 'rejected', 'missed', 'ended');

-- Alarms table
CREATE TABLE alarms (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    time TIME NOT NULL,
    days JSONB DEFAULT '[]', -- Array of days for recurring alarms
    is_enabled BOOLEAN DEFAULT TRUE,
    ringtone_uri VARCHAR(500),
    vibration_pattern JSONB, -- Array of vibration pattern
    snooze_duration INTEGER DEFAULT 300, -- in seconds
    max_snooze_count INTEGER DEFAULT 3,
    alarm_duration INTEGER DEFAULT 60, -- Duration of alarm in seconds
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Calendar events table
CREATE TABLE calendar_events (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    location VARCHAR(500),
    is_all_day BOOLEAN DEFAULT FALSE,
    reminder_minutes INTEGER DEFAULT 15,
    calendar_id VARCHAR(255), -- Google Calendar ID
    event_id VARCHAR(255), -- Google Calendar Event ID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Calls table
CREATE TABLE calls (
    id BIGSERIAL PRIMARY KEY,
    phone_number VARCHAR(50),
    contact_name VARCHAR(255),
    call_type call_type NOT NULL,
    call_status call_status NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    is_whatsapp_call BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tasks table
CREATE TABLE tasks (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    priority task_priority DEFAULT 'medium',
    status task_status DEFAULT 'pending',
    due_date TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    category VARCHAR(100),
    tags JSONB DEFAULT '[]', -- Array of tags
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Goals table (for TODO/goals tracking)
CREATE TABLE goals (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    target_date TIMESTAMP WITH TIME ZONE,
    progress_percentage INTEGER DEFAULT 0,
    is_completed BOOLEAN DEFAULT FALSE,
    completed_at TIMESTAMP WITH TIME ZONE,
    category VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- WhatsApp messages table
CREATE TABLE whatsapp_messages (
    id BIGSERIAL PRIMARY KEY,
    sender VARCHAR(255),
    receiver VARCHAR(255),
    message_content TEXT,
    message_type VARCHAR(50), -- text, image, video, audio, document
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    is_incoming BOOLEAN DEFAULT TRUE,
    chat_id VARCHAR(255),
    message_id VARCHAR(255), -- WhatsApp message ID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Voice commands log table
CREATE TABLE voice_commands (
    id BIGSERIAL PRIMARY KEY,
    command_text TEXT NOT NULL,
    parsed_intent VARCHAR(100),
    parsed_entities JSONB,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    processing_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX idx_alarms_time ON alarms(time);
CREATE INDEX idx_alarms_enabled ON alarms(is_enabled);
CREATE INDEX idx_calendar_events_start_time ON calendar_events(start_time);
CREATE INDEX idx_calls_start_time ON calls(start_time);
CREATE INDEX idx_calls_phone_number ON calls(phone_number);
CREATE INDEX idx_tasks_due_date ON tasks(due_date);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_goals_target_date ON goals(target_date);
CREATE INDEX idx_whatsapp_messages_timestamp ON whatsapp_messages(timestamp);
CREATE INDEX idx_voice_commands_created_at ON voice_commands(created_at);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
CREATE TRIGGER update_alarms_updated_at BEFORE UPDATE ON alarms FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_calendar_events_updated_at BEFORE UPDATE ON calendar_events FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_calls_updated_at BEFORE UPDATE ON calls FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON tasks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_goals_updated_at BEFORE UPDATE ON goals FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_whatsapp_messages_updated_at BEFORE UPDATE ON whatsapp_messages FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
