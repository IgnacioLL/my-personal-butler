package com.personalassistant.data.local.database.migrations

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

/**
 * Sample migration from version 1 to 2
 * This demonstrates how to handle future database schema changes
 */
val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(database: SupportSQLiteDatabase) {
        // Example: Add a new column to the alarms table
        // database.execSQL("ALTER TABLE alarms ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
        
        // For now, this migration is empty since we're starting with version 1
        // Add actual migration logic here when needed
    }
}
