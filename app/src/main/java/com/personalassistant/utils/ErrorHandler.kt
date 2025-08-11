package com.personalassistant.utils

import android.content.Context
import android.widget.Toast
import com.personalassistant.R
import kotlinx.coroutines.CancellationException
import java.io.IOException
import java.net.SocketTimeoutException

/**
 * Comprehensive error handling utility for the alarm module
 */
object ErrorHandler {
    
    sealed class AlarmError : Exception() {
        object DatabaseError : AlarmError()
        object NetworkError : AlarmError()
        object PermissionError : AlarmError()
        object InvalidTimeError : AlarmError()
        object AlarmSchedulingError : AlarmError()
        object RingtoneError : AlarmError()
        object VibrationError : AlarmError()
        
        data class CustomError(override val message: String) : AlarmError()
    }
    
    /**
     * Handle errors and provide user-friendly messages
     */
    fun handleError(context: Context, throwable: Throwable) {
        when (throwable) {
            is CancellationException -> {
                // Coroutine was cancelled, no need to show error
                return
            }
            is AlarmError -> {
                showUserFriendlyError(context, throwable)
            }
            is IOException -> {
                showToast(context, context.getString(R.string.error_network_io))
            }
            is SocketTimeoutException -> {
                showToast(context, context.getString(R.string.error_network_timeout))
            }
            else -> {
                showToast(context, context.getString(R.string.error_unknown))
            }
        }
    }
    
    private fun showUserFriendlyError(context: Context, error: AlarmError) {
        val message = when (error) {
            is AlarmError.DatabaseError -> context.getString(R.string.error_database)
            is AlarmError.NetworkError -> context.getString(R.string.error_network)
            is AlarmError.PermissionError -> context.getString(R.string.error_permission)
            is AlarmError.InvalidTimeError -> context.getString(R.string.error_invalid_time)
            is AlarmError.AlarmSchedulingError -> context.getString(R.string.error_alarm_scheduling)
            is AlarmError.RingtoneError -> context.getString(R.string.error_ringtone)
            is AlarmError.VibrationError -> context.getString(R.string.error_vibration)
            is AlarmError.CustomError -> error.message
        }
        showToast(context, message)
    }
    
    private fun showToast(context: Context, message: String) {
        Toast.makeText(context, message, Toast.LENGTH_LONG).show()
    }
    
    /**
     * Check if error is recoverable
     */
    fun isRecoverable(throwable: Throwable): Boolean {
        return when (throwable) {
            is CancellationException -> false
            is AlarmError.NetworkError -> true
            is AlarmError.DatabaseError -> true
            is AlarmError.PermissionError -> false
            is AlarmError.InvalidTimeError -> true
            is AlarmError.AlarmSchedulingError -> true
            is AlarmError.RingtoneError -> true
            is AlarmError.VibrationError -> true
            is AlarmError.CustomError -> true
            else -> true
        }
    }
}
