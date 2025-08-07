package com.personalassistant.data.local.database

import androidx.room.TypeConverter
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.time.LocalTime
import java.time.ZonedDateTime

class Converters {
    private val gson = Gson()
    
    @TypeConverter
    fun fromLocalTime(time: LocalTime?): String? {
        return time?.toString()
    }
    
    @TypeConverter
    fun toLocalTime(timeString: String?): LocalTime? {
        return timeString?.let { LocalTime.parse(it) }
    }
    
    @TypeConverter
    fun fromZonedDateTime(dateTime: ZonedDateTime?): String? {
        return dateTime?.toString()
    }
    
    @TypeConverter
    fun toZonedDateTime(dateTimeString: String?): ZonedDateTime? {
        return dateTimeString?.let { ZonedDateTime.parse(it) }
    }
    
    @TypeConverter
    fun fromIntList(list: List<Int>?): String? {
        return list?.let { gson.toJson(it) }
    }
    
    @TypeConverter
    fun toIntList(json: String?): List<Int>? {
        return json?.let {
            val type = object : TypeToken<List<Int>>() {}.type
            gson.fromJson(it, type)
        }
    }
    
    @TypeConverter
    fun fromLongList(list: List<Long>?): String? {
        return list?.let { gson.toJson(it) }
    }
    
    @TypeConverter
    fun toLongList(json: String?): List<Long>? {
        return json?.let {
            val type = object : TypeToken<List<Long>>() {}.type
            gson.fromJson(it, type)
        }
    }
}
