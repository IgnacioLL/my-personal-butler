-- Database Connection Information
-- This script creates additional users and provides connection details

-- Create a read-only user for the Android app
CREATE USER assistant_app_user WITH PASSWORD 'app_password';

-- Grant necessary permissions to the app user
GRANT CONNECT ON DATABASE personal_assistant TO assistant_app_user;
GRANT USAGE ON SCHEMA public TO assistant_app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO assistant_app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO assistant_app_user;

-- Grant permissions for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO assistant_app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO assistant_app_user;

-- Create a backup user with read-only access
CREATE USER backup_user WITH PASSWORD 'backup_password';
GRANT CONNECT ON DATABASE personal_assistant TO backup_user;
GRANT USAGE ON SCHEMA public TO backup_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO backup_user;

-- Display connection information
DO $$
BEGIN
    RAISE NOTICE 'Database Setup Complete!';
    RAISE NOTICE 'Database Name: personal_assistant';
    RAISE NOTICE 'Admin User: assistant_user';
    RAISE NOTICE 'App User: assistant_app_user';
    RAISE NOTICE 'Backup User: backup_user';
    RAISE NOTICE 'Port: 5432';
    RAISE NOTICE 'Host: localhost';
END $$;
