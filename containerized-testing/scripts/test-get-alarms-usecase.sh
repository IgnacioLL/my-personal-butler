#!/bin/bash

# Test script for GetAlarmsUseCase in containerized environment

set -e

echo "Starting GetAlarmsUseCase integration tests..."

# Set environment variables
export ANDROID_HOME=/opt/android-sdk
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export GRADLE_HOME=/opt/gradle
export PATH=$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools:$ANDROID_HOME/cmdline-tools/latest/bin:$GRADLE_HOME/bin

# Navigate to app directory
cd /workspace/app

# Check if we're in the right directory
if [ ! -f "build.gradle" ]; then
    echo "Error: No Android project found in /workspace/app"
    exit 1
fi

echo "Building project for testing..."
./gradlew assembleDebug

echo "Running GetAlarmsUseCase integration tests..."

# Run the specific integration test
./gradlew connectedAndroidTest -Pandroid.testInstrumentationRunner="androidx.test.runner.AndroidJUnitRunner" \
    --tests "com.personalassistant.GetAlarmsUseCaseIntegrationTest"

echo "Running unit tests for GetAlarmsUseCase..."

# Run unit tests
./gradlew test --tests "com.personalassistant.GetAlarmsUseCaseTest"

echo "Running all alarm-related tests..."

# Run all alarm-related tests
./gradlew test --tests "*Alarm*"
./gradlew connectedAndroidTest --tests "*Alarm*"

echo "Test execution completed!"

# Generate test report
echo "Generating test report..."
./gradlew jacocoTestReport

echo "Test results available in:"
echo "- Unit tests: build/reports/tests/"
echo "- Integration tests: build/reports/androidTests/"
echo "- Coverage report: build/reports/jacoco/"

# Check if all tests passed
if [ $? -eq 0 ]; then
    echo "✅ All GetAlarmsUseCase tests passed!"
else
    echo "❌ Some tests failed. Check the logs above for details."
    exit 1
fi
