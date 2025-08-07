#!/bin/bash

# Script to run Android environment interactively with visual access

echo "Starting Android environment with visual access..."

# Create a simplified docker-compose for just Android
cat > docker-compose.android.yml << 'EOF'
version: '3.8'

services:
  android-app:
    build:
      context: .
      dockerfile: Dockerfile.android
    container_name: personal-assistant-android-interactive
    environment:
      - ANDROID_HOME=/opt/android-sdk
      - JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
      - GRADLE_HOME=/opt/gradle
      - PATH=$PATH:/opt/android-sdk/platform-tools:/opt/android-sdk/tools:/opt/gradle/bin
      - DISPLAY=${DISPLAY}
    volumes:
      - android-sdk:/opt/android-sdk
      - gradle-cache:/root/.gradle
      - /tmp/.X11-unix:/tmp/.X11-unix:rw
    ports:
      - "5555:5555"  # ADB
      - "5900:5900"  # VNC server
      - "6080:6080"  # noVNC web interface
    privileged: true
    command: >
      sh -c "
        echo 'Starting Xvfb...' &&
        Xvfb :0 -screen 0 1024x768x24 &
        sleep 2 &&
        echo 'Starting window manager...' &&
        fluxbox &
        sleep 2 &&
        echo 'Starting Android emulator...' &&
        /opt/android-sdk/emulator/emulator -avd test_device -no-audio -gpu swiftshader_indirect -display :0 &
        sleep 30 &&
        echo 'Waiting for emulator to boot...' &&
        adb wait-for-device &&
        echo 'Starting VNC server...' &&
        x11vnc -display :0 -nopw -listen localhost -xkb -ncache 10 -ncache_cr -forever &
        echo 'Starting noVNC...' &&
        /opt/novnc/utils/launch.sh --vnc localhost:5900 --listen 6080 &
        echo 'Android emulator ready!' &&
        echo 'Access via: http://localhost:6080' &&
        echo 'ADB available at: localhost:5555' &&
        tail -f /dev/null
      "

volumes:
  android-sdk:
    driver: local
  gradle-cache:
    driver: local
EOF

# Run the Android environment
echo "Building and starting Android container..."
docker-compose -f docker-compose.android.yml up --build -d

echo ""
echo "Android environment is starting..."
echo "Access the Android emulator via:"
echo "  - Web browser: http://localhost:6080"
echo "  - VNC client: localhost:5900"
echo "  - ADB: adb connect localhost:5555"
echo ""
echo "To stop the environment:"
echo "  docker-compose -f docker-compose.android.yml down"
echo ""
echo "To view logs:"
echo "  docker-compose -f docker-compose.android.yml logs -f android-app"
