#!/bin/bash

# Android build script for containerized environment

set -e

echo "Starting Android build process..."

# Set environment variables
export ANDROID_HOME=/opt/android-sdk
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export GRADLE_HOME=/opt/gradle
export PATH=$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools:$ANDROID_HOME/cmdline-tools/latest/bin:$GRADLE_HOME/bin

# Navigate to app directory
cd /workspace/app

# Check if app directory exists and has content
if [ ! -f "build.gradle" ]; then
    echo "No Android project found in /workspace/app"
    echo "Creating a sample Android project..."
    
    # Create a basic Android project structure
    mkdir -p src/main/java/com/example/testapp
    mkdir -p src/main/res/layout
    mkdir -p src/main/res/values
    
    # Create basic build.gradle
    cat > build.gradle << 'EOF'
plugins {
    id 'com.android.application'
}

android {
    compileSdk 33
    
    defaultConfig {
        applicationId "com.example.testapp"
        minSdk 21
        targetSdk 33
        versionCode 1
        versionName "1.0"
    }
    
    buildTypes {
        release {
            minifyEnabled false
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
}

dependencies {
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.9.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'
}
EOF

    # Create basic MainActivity
    cat > src/main/java/com/example/testapp/MainActivity.java << 'EOF'
package com.example.testapp;

import android.os.Bundle;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
    }
}
EOF

    # Create basic layout
    cat > src/main/res/layout/activity_main.xml << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:gravity="center">

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="Hello Android!"
        android:textSize="24sp" />

</LinearLayout>
EOF

    # Create basic strings
    cat > src/main/res/values/strings.xml << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Test App</string>
</resources>
EOF

    # Create basic manifest
    cat > src/main/AndroidManifest.xml << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:theme="@style/Theme.AppCompat.Light.DarkActionBar">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
EOF

    echo "Sample Android project created"
fi

# Build the Android project
echo "Building Android project..."
./gradlew assembleDebug

echo "Build completed successfully!"
echo "APK location: /workspace/app/build/outputs/apk/debug/app-debug.apk"
