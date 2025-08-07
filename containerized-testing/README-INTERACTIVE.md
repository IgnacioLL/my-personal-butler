# Interactive Android Environment

This guide explains how to run an interactive Android environment with visual access without implementing the Personal Assistant app.

## Quick Start

### 1. Run Android Environment Only

```bash
cd containerized-testing
./scripts/run-android-interactive.sh
```

### 2. Access the Android Emulator

Once the container is running, you can access the Android emulator through:

- **Web Browser**: http://localhost:6080
- **VNC Client**: localhost:5900
- **ADB**: `adb connect localhost:5555`

## What You Get

### Visual Android Environment
- Full Android 13 (API 33) emulator
- 1024x768 display resolution
- Hardware acceleration enabled
- Touch, keyboard, and mouse support

### Development Tools
- Android SDK with all tools
- ADB (Android Debug Bridge)
- Gradle build system
- Command line access

### Interactive Features
- Full Android UI experience
- Install and test any APK
- Debug applications
- Use Android apps and features

## Usage Examples

### 1. Install and Test APKs
```bash
# Connect ADB
adb connect localhost:5555

# Install an APK
adb install your-app.apk

# Launch an app
adb shell am start -n com.example.app/.MainActivity
```

### 2. Debug Applications
```bash
# View logs
adb logcat

# Take screenshots
adb shell screencap /sdcard/screenshot.png
adb pull /sdcard/screenshot.png

# Record screen
adb shell screenrecord /sdcard/recording.mp4
```

### 3. Use Android Features
- Browse the web
- Install apps from Play Store
- Test different Android features
- Experiment with Android settings

## Configuration Options

### Modify Display Settings
Edit `configs/android-emulator.conf`:
```ini
hw.lcd.width=1024
hw.lcd.height=768
hw.lcd.density=240
```

### Change Performance Settings
```ini
hw.ramSize=2048
hw.cpu.ncore=4
vm.heapSize=256
```

## Troubleshooting

### Common Issues

1. **Emulator won't start**
   ```bash
   # Check container logs
   docker-compose -f docker-compose.android.yml logs android-app
   
   # Restart container
   docker-compose -f docker-compose.android.yml restart android-app
   ```

2. **VNC connection issues**
   ```bash
   # Check if VNC is running
   docker exec -it personal-assistant-android-interactive ps aux | grep x11vnc
   
   # Restart VNC
   docker exec -it personal-assistant-android-interactive pkill x11vnc
   ```

3. **ADB connection issues**
   ```bash
   # Kill and restart ADB server
   adb kill-server
   adb start-server
   adb connect localhost:5555
   ```

### Performance Optimization

1. **Increase container resources**
   ```yaml
   # In docker-compose.android.yml
   deploy:
     resources:
       limits:
         memory: 4G
         cpus: '2.0'
   ```

2. **Use hardware acceleration**
   ```bash
   # Ensure KVM is available
   ls -l /dev/kvm
   
   # Run with KVM support
   docker run --privileged -v /dev/kvm:/dev/kvm ...
   ```

## Advanced Usage

### Custom Android Image
You can create a custom Android image with pre-installed apps:

```dockerfile
# In Dockerfile.android
COPY custom-apps/ /workspace/custom-apps/
RUN for app in /workspace/custom-apps/*.apk; do \
    adb install $app; \
done
```

### Persistent Data
The Android emulator data persists between container restarts:
```yaml
volumes:
  - android-data:/root/.android/avd/test_device.avd
```

### Network Access
The emulator has full network access and can:
- Download apps from Play Store
- Access web services
- Connect to development servers

## Integration with Development

### Local Development
1. Build your app locally
2. Install APK in the emulator
3. Test and debug interactively

### CI/CD Integration
```bash
# Automated testing
docker-compose -f docker-compose.android.yml up -d
sleep 60  # Wait for emulator
adb install app-debug.apk
adb shell am start -n com.example.app/.MainActivity
# Run tests...
```

## Security Considerations

- The container runs with `privileged: true` for hardware access
- VNC server has no password (development only)
- Consider using VPN for production environments
- Regularly update base images for security patches

## Resource Requirements

### Minimum Requirements
- 4GB RAM
- 2 CPU cores
- 10GB disk space

### Recommended Requirements
- 8GB RAM
- 4 CPU cores
- 20GB disk space
- Hardware virtualization support (KVM)

## Support

For issues and questions:
- Check container logs: `docker-compose logs android-app`
- Review Android emulator documentation
- Check Docker and KVM installation
- Ensure sufficient system resources
