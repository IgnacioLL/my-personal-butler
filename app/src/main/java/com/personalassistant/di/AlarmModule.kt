package com.personalassistant.di

import android.app.AlarmManager
import android.content.Context
import androidx.work.WorkManager
import com.personalassistant.data.local.database.mappers.AlarmMapper
import com.personalassistant.data.repositories.AlarmRepositoryImpl
import com.personalassistant.domain.repositories.AlarmRepository
import com.personalassistant.data.local.database.dao.AlarmDao
import com.personalassistant.domain.usecases.alarms.*
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AlarmModule {
    
    @Provides
    @Singleton
    fun provideAlarmMapper(): AlarmMapper {
        return AlarmMapper()
    }
    
    @Provides
    @Singleton
    fun provideAlarmManager(@ApplicationContext context: Context): AlarmManager {
        return context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
    }
    
    @Provides
    @Singleton
    fun provideWorkManager(@ApplicationContext context: Context): WorkManager {
        return WorkManager.getInstance(context)
    }
    
    @Provides
    @Singleton
    fun provideAlarmRepository(
        alarmDao: AlarmDao,
        alarmManager: AlarmManager,
        @ApplicationContext context: Context,
        workManager: WorkManager
    ): AlarmRepository {
        return AlarmRepositoryImpl(alarmDao, alarmManager, context, workManager)
    }
    
    @Provides
    @Singleton
    fun provideCreateAlarmUseCase(
        alarmRepository: AlarmRepository
    ): CreateAlarmUseCase {
        return CreateAlarmUseCase(alarmRepository)
    }
    
    @Provides
    @Singleton
    fun provideGetAlarmsUseCase(
        alarmRepository: AlarmRepository
    ): GetAlarmsUseCase {
        return GetAlarmsUseCase(alarmRepository)
    }
    
    @Provides
    @Singleton
    fun provideUpdateAlarmUseCase(
        alarmRepository: AlarmRepository
    ): UpdateAlarmUseCase {
        return UpdateAlarmUseCase(alarmRepository)
    }
    
    @Provides
    @Singleton
    fun provideDeleteAlarmUseCase(
        alarmRepository: AlarmRepository
    ): DeleteAlarmUseCase {
        return DeleteAlarmUseCase(alarmRepository)
    }
    
    @Provides
    @Singleton
    fun provideTriggerAlarmUseCase(
        alarmRepository: AlarmRepository
    ): TriggerAlarmUseCase {
        return TriggerAlarmUseCase(alarmRepository)
    }
    
    @Provides
    @Singleton
    fun provideSnoozeAlarmUseCase(
        alarmRepository: AlarmRepository
    ): SnoozeAlarmUseCase {
        return SnoozeAlarmUseCase(alarmRepository)
    }
    
}
