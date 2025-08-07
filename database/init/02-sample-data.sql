-- Sample data for Personal Assistant Database
-- This script inserts sample data for testing purposes

-- Insert sample alarms
INSERT INTO alarms (title, time, days, is_enabled, ringtone_uri, snooze_duration, alarm_duration) VALUES
('Morning Wake Up', '07:00:00', '["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]', true, 'content://media/external/audio/media/1', 300, 60),
('Weekend Alarm', '08:30:00', '["SATURDAY", "SUNDAY"]', true, 'content://media/external/audio/media/2', 600, 120),
('Work Meeting', '09:00:00', '["MONDAY", "WEDNESDAY", "FRIDAY"]', true, 'content://media/external/audio/media/3', 300, 90),
('Gym Time', '18:00:00', '["MONDAY", "WEDNESDAY", "FRIDAY"]', true, 'content://media/external/audio/media/4', 300, 60);

-- Insert sample calendar events
INSERT INTO calendar_events (title, description, start_time, end_time, location, is_all_day, reminder_minutes) VALUES
('Team Meeting', 'Weekly team sync meeting', '2024-01-15 10:00:00+00', '2024-01-15 11:00:00+00', 'Conference Room A', false, 15),
('Doctor Appointment', 'Annual health checkup', '2024-01-16 14:00:00+00', '2024-01-16 15:00:00+00', 'Medical Center', false, 30),
('Birthday Party', 'Friend birthday celebration', '2024-01-20 19:00:00+00', '2024-01-20 23:00:00+00', 'Restaurant Downtown', false, 60),
('Project Deadline', 'Submit final project', '2024-01-25 17:00:00+00', '2024-01-25 17:00:00+00', 'Office', false, 120);

-- Insert sample calls
INSERT INTO calls (phone_number, contact_name, call_type, call_status, start_time, end_time, duration_seconds, is_whatsapp_call) VALUES
('+1234567890', 'John Doe', 'incoming', 'answered', '2024-01-15 09:30:00+00', '2024-01-15 09:45:00+00', 900, false),
('+1234567891', 'Jane Smith', 'outgoing', 'answered', '2024-01-15 14:20:00+00', '2024-01-15 14:35:00+00', 900, false),
('+1234567892', 'Unknown', 'incoming', 'missed', '2024-01-15 16:00:00+00', NULL, NULL, false),
('+1234567893', 'Mom', 'incoming', 'answered', '2024-01-15 20:00:00+00', '2024-01-15 20:30:00+00', 1800, true);

-- Insert sample tasks
INSERT INTO tasks (title, description, priority, status, due_date, category, tags) VALUES
('Complete project proposal', 'Finish the quarterly project proposal document', 'high', 'pending', '2024-01-20 17:00:00+00', 'Work', '["urgent", "documentation"]'),
('Buy groceries', 'Milk, bread, eggs, and vegetables', 'medium', 'pending', '2024-01-16 18:00:00+00', 'Personal', '["shopping", "food"]'),
('Call dentist', 'Schedule annual dental checkup', 'low', 'completed', '2024-01-15 10:00:00+00', 'Health', '["appointment"]'),
('Review code', 'Code review for new feature', 'high', 'in_progress', '2024-01-18 16:00:00+00', 'Work', '["development", "review"]'),
('Exercise', '30 minutes cardio workout', 'medium', 'pending', '2024-01-15 18:00:00+00', 'Health', '["fitness", "cardio"]');

-- Insert sample goals
INSERT INTO goals (title, description, target_date, progress_percentage, category) VALUES
('Learn Kotlin', 'Master Kotlin programming language for Android development', '2024-06-30 23:59:59+00', 60, 'Learning'),
('Run Marathon', 'Complete a full marathon', '2024-10-15 23:59:59+00', 25, 'Fitness'),
('Save Money', 'Save $10,000 for emergency fund', '2024-12-31 23:59:59+00', 40, 'Finance'),
('Read Books', 'Read 24 books this year', '2024-12-31 23:59:59+00', 15, 'Personal');

-- Insert sample WhatsApp messages
INSERT INTO whatsapp_messages (sender, receiver, message_content, message_type, timestamp, is_incoming, chat_id) VALUES
('John Doe', 'Me', 'Hey, are you free for lunch tomorrow?', 'text', '2024-01-15 10:30:00+00', true, 'chat_123'),
('Me', 'Jane Smith', 'Can you send me the meeting notes?', 'text', '2024-01-15 14:15:00+00', false, 'chat_124'),
('Mom', 'Me', 'Don''t forget about dinner on Sunday!', 'text', '2024-01-15 18:45:00+00', true, 'chat_125'),
('Work Group', 'Me', 'Meeting rescheduled to 3 PM', 'text', '2024-01-15 09:00:00+00', true, 'chat_126');

-- Insert sample voice commands
INSERT INTO voice_commands (command_text, parsed_intent, parsed_entities, success, processing_time_ms) VALUES
('Wake me up at 7 AM', 'create_alarm', '{"time": "07:00", "title": "Wake up"}', true, 150),
('Set alarm for 6:30 tomorrow', 'create_alarm', '{"time": "06:30", "date": "tomorrow", "title": "Alarm"}', true, 200),
('Create task buy groceries', 'create_task', '{"title": "buy groceries", "priority": "medium"}', true, 180),
('Call John', 'make_call', '{"contact": "John"}', true, 120),
('What''s my schedule for today?', 'get_calendar', '{"date": "today"}', true, 250);
