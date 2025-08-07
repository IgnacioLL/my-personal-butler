# Containerized Testing Environment

## Overview

This directory contains a complete containerized testing environment for the Personal Assistant application. The setup allows for isolated testing of different components and their interactions without affecting the local development environment.

## Architecture

The testing environment consists of multiple containers:

1. **Android App Container** - Runs the Android application in an emulator
2. **Database Container** - PostgreSQL database for data persistence
3. **API Services Container** - Mock/Test versions of external APIs
4. **Monitoring Container** - Logs, metrics, and debugging tools
5. **Test Runner Container** - Automated test execution

## Directory Structure

```
containerized-testing/
├── README.md                 # This file
├── docker-compose.yml        # Main orchestration file
├── docker-compose.test.yml   # Test-specific overrides
├── scripts/
│   ├── setup.sh             # Initial setup script
│   ├── run-tests.sh         # Test execution script
│   ├── cleanup.sh           # Cleanup script
│   └── monitor.sh           # Monitoring script
├── configs/
│   ├── android-emulator.conf # Android emulator configuration
│   ├── database-init.sql     # Database initialization
│   └── api-mocks.json       # Mock API responses
├── tests/
│   ├── integration/         # Integration tests
│   ├── e2e/                # End-to-end tests
│   └── performance/         # Performance tests
└── logs/                   # Test logs and outputs
```

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- At least 8GB RAM available for containers
- Android SDK (for local development)

### Setup

1. **Clone and navigate to the testing directory:**
   ```bash
   cd containerized-testing
   ```

2. **Run the setup script:**
   ```bash
   chmod +x scripts/setup.sh
   ./scripts/setup.sh
   ```

3. **Start the testing environment:**
   ```bash
   docker-compose up -d
   ```

4. **Run tests:**
   ```bash
   ./scripts/run-tests.sh
   ```

## Testing Strategy

### 1. Component Isolation Testing

Each component is tested in isolation:

- **Database Layer**: Test data persistence, migrations, and queries
- **API Layer**: Test external service integrations
- **Business Logic**: Test use cases and domain logic
- **UI Layer**: Test user interactions and responses

### 2. Integration Testing

Test component interactions:

- **Data Flow**: Database → Repository → Use Case → ViewModel → UI
- **API Integration**: App → External APIs → Response handling
- **Service Communication**: Background services ↔ Main app

### 3. End-to-End Testing

Complete user journey testing:

- **Voice Commands**: Speech → Processing → Action → Response
- **Task Management**: Create → Update → Complete → Notify
- **Alarm System**: Set → Schedule → Trigger → Dismiss
- **Call Screening**: Incoming call → Analysis → Decision → Action

### 4. Performance Testing

- **Load Testing**: Multiple concurrent users
- **Stress Testing**: High data volume scenarios
- **Memory Testing**: Long-running operations
- **Network Testing**: Poor connectivity scenarios

## Container Details

### Android App Container

- **Image**: `openjdk:11-jdk`
- **Features**:
  - Android SDK and emulator
  - Gradle build system
  - ADB (Android Debug Bridge)
  - Automated app installation and testing

### Database Container

- **Image**: `postgres:15`
- **Features**:
  - Persistent data storage
  - Automated schema migrations
  - Test data seeding
  - Backup and restore capabilities

### API Services Container

- **Image**: `node:16-alpine`
- **Features**:
  - Mock Google Calendar API
  - Mock Gmail API
  - Mock OpenAI API
  - Mock AssemblyAI API
  - Configurable responses and delays

### Monitoring Container

- **Image**: `grafana/grafana:latest`
- **Features**:
  - Real-time metrics dashboard
  - Log aggregation
  - Performance monitoring
  - Alert system

## Test Scenarios

### Voice Command Testing

```bash
# Test voice command processing
curl -X POST http://localhost:8080/api/voice/process \
  -H "Content-Type: application/json" \
  -d '{"command": "set alarm for 8 AM tomorrow"}'
```

### Database Testing

```bash
# Test database operations
docker exec -it personal-assistant-db psql -U testuser -d testdb -c "SELECT * FROM tasks;"
```

### API Integration Testing

```bash
# Test external API calls
curl -X GET http://localhost:8081/api/calendar/events
```

## Monitoring and Debugging

### Access Points

- **Grafana Dashboard**: http://localhost:3000
- **Database Admin**: http://localhost:8080 (pgAdmin)
- **API Documentation**: http://localhost:8081/docs
- **Test Results**: `logs/test-results/`

### Logs

```bash
# View all container logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f android-app
docker-compose logs -f database
docker-compose logs -f api-services
```

### Debugging

```bash
# Access Android emulator
adb connect localhost:5555

# Access database
docker exec -it personal-assistant-db psql -U testuser -d testdb

# Access API container
docker exec -it personal-assistant-api sh
```

## Performance Benchmarks

### Target Metrics

- **App Startup**: < 3 seconds
- **Voice Processing**: < 2 seconds
- **Database Queries**: < 100ms
- **API Calls**: < 500ms
- **Memory Usage**: < 200MB
- **Battery Impact**: < 5% per hour

### Load Testing

```bash
# Run performance tests
./scripts/run-tests.sh --performance

# Generate load test report
./scripts/monitor.sh --generate-report
```

## Continuous Integration

### Automated Testing Pipeline

1. **Code Commit** → Trigger CI/CD pipeline
2. **Build Containers** → Create fresh test environment
3. **Run Tests** → Execute all test suites
4. **Generate Report** → Create detailed test report
5. **Cleanup** → Remove test containers

### Test Reports

Reports are generated in multiple formats:
- **HTML**: Interactive test results
- **JSON**: Machine-readable data
- **JUnit XML**: CI/CD integration
- **Performance**: Metrics and benchmarks

## Troubleshooting

### Common Issues

1. **Container Startup Failures**
   ```bash
   docker-compose down
   docker system prune -f
   docker-compose up -d
   ```

2. **Android Emulator Issues**
   ```bash
   docker exec -it personal-assistant-android adb kill-server
   docker exec -it personal-assistant-android adb start-server
   ```

3. **Database Connection Issues**
   ```bash
   docker-compose restart database
   docker exec -it personal-assistant-db pg_ctl restart
   ```

4. **API Service Issues**
   ```bash
   docker-compose restart api-services
   docker logs personal-assistant-api
   ```

### Performance Issues

- **High Memory Usage**: Reduce container memory limits
- **Slow Startup**: Use pre-built images
- **Network Issues**: Check Docker network configuration

## Development Workflow

### 1. Local Development
- Develop features locally
- Use containers for testing dependencies
- Run unit tests locally

### 2. Container Testing
- Push changes to container environment
- Run integration tests
- Validate component interactions

### 3. Performance Validation
- Run performance benchmarks
- Compare against targets
- Optimize if needed

### 4. Deployment Preparation
- Final integration testing
- Load testing
- Documentation updates

## Contributing

### Adding New Tests

1. Create test file in appropriate directory
2. Update test configuration
3. Add to test runner
4. Update documentation

### Modifying Test Environment

1. Update Docker configuration
2. Modify test scripts
3. Update documentation
4. Test changes

## Security Considerations

- All containers run in isolated networks
- No production credentials in test environment
- Regular security updates for base images
- Encrypted communication between containers

## Maintenance

### Regular Tasks

- **Weekly**: Update base images
- **Monthly**: Review and update test scenarios
- **Quarterly**: Performance benchmark review
- **Annually**: Complete environment refresh

### Backup Strategy

- Database backups: Daily
- Test results: Weekly
- Configuration: Monthly
- Complete environment: Quarterly

## Support

For issues and questions:
- Check troubleshooting section
- Review logs in `logs/` directory
- Consult test documentation
- Create issue in project repository
