# CIRIS Resource Monitor Service

**Service Type**: Infrastructure Service  
**Location**: `/ciris_engine/logic/services/infrastructure/resource_monitor.py` ⚠️ *Needs module conversion*  
**Protocol**: `ResourceMonitorServiceProtocol`  
**Status**: Production Ready ✅

## Mission Statement

The Resource Monitor Service is a critical infrastructure component that serves **Meta-Goal M-1: Promote sustainable adaptive coherence** by ensuring CIRIS operates within strict resource constraints, enabling sustainable deployment in resource-limited environments while preventing system exhaustion that would undermine long-term operational stability.

## 🎯 Mission Alignment with Meta-Goal M-1

### Sustainable Adaptive Coherence
- **Resource Sustainability**: Enforces the 4GB RAM target to enable deployment in constrained environments (edge devices, rural clinics, developing regions)
- **Adaptive Response**: Implements graduated protective actions (throttle → defer → reject → shutdown) based on resource pressure
- **Coherence Protection**: Prevents resource exhaustion that would degrade decision-making quality or cause system failures

### Enabling Diverse Flourishing
- **Edge Deployment**: Makes ethical AI accessible in resource-constrained environments where traditional heavy systems cannot operate
- **Offline Capability**: Resource monitoring enables sustainable operation during intermittent connectivity
- **Democratic Access**: By maintaining 4GB RAM constraint, CIRIS remains deployable on commodity hardware worldwide

## Architecture Overview

### Core Components

```python
class ResourceMonitorService(BaseScheduledService, ResourceMonitorServiceProtocol):
    """Monitor system resources and enforce limits for 1000-year sustainable operation."""
```

**Key Components:**
- **Resource Snapshot**: Real-time system state tracking
- **Resource Budget**: Configurable limits and thresholds
- **Signal Bus**: Event-driven protective action system
- **Historical Tracking**: Time-windowed usage patterns

### Service Classification
- **Category**: Infrastructure Service
- **Run Frequency**: 1-second intervals (real-time monitoring)
- **Dependencies**: Time Service (for timestamping)
- **Service Type**: VISIBILITY (provides system observability)

## 📊 Resource Tracking Matrix

| Resource Type | Default Limits | Tracking Window | Primary Use Case |
|---------------|----------------|-----------------|------------------|
| **Memory (MB)** | 4096 limit / 3072 warn / 3840 critical | Real-time | Core 4GB constraint |
| **CPU (%)** | 80 limit / 60 warn / 75 critical | 1-minute average | Performance optimization |
| **Tokens/Hour** | 10k limit / 8k warn / 9.5k critical | Rolling hour | Rate limiting |
| **Tokens/Day** | 100k limit / 80k warn / 95k critical | Rolling day | Cost control |
| **Active Thoughts** | 50 limit / 40 warn / 48 critical | Real-time | Processing queue |
| **Disk Space** | 100MB limit / 80 warn / 95 critical | Real-time | Storage management |

### Resource Actions Hierarchy

```
LOG → WARN → THROTTLE → DEFER → REJECT → SHUTDOWN
  ↑                                           ↑
Minor issues                            System protection
```

## 🔧 Technical Implementation

### Resource Budget Configuration

```python
class ResourceBudget(BaseModel):
    """Configurable limits for all monitored resources"""
    memory_mb: ResourceLimit = Field(default_factory=_memory_mb_limit)
    cpu_percent: ResourceLimit = Field(default_factory=_cpu_percent_limit) 
    tokens_hour: ResourceLimit = Field(default_factory=_tokens_hour_limit)
    tokens_day: ResourceLimit = Field(default_factory=_tokens_day_limit)
    disk_mb: ResourceLimit = Field(default_factory=_disk_mb_limit)
    thoughts_active: ResourceLimit = Field(default_factory=_thoughts_active_limit)
```

### Real-time Monitoring

```python
class ResourceSnapshot(BaseModel):
    """Current system state with health indicators"""
    memory_mb: int = Field(ge=0, description="Memory usage in MB")
    cpu_percent: int = Field(ge=0, le=100, description="CPU usage percentage") 
    tokens_used_hour: int = Field(ge=0, description="Tokens used in current hour")
    thoughts_active: int = Field(ge=0, description="Number of active thoughts")
    healthy: bool = Field(default=True, description="Overall health status")
    warnings: List[str] = Field(default_factory=list, description="Active warnings")
    critical: List[str] = Field(default_factory=list, description="Critical issues")
```

### Signal-Driven Protection System

```python
class ResourceSignalBus:
    """Event bus for resource-driven protective actions"""
    
    async def emit(self, signal: str, resource: str) -> None:
        # Signals: "throttle", "defer", "reject", "shutdown"
        # Enables other services to respond to resource pressure
```

## 🚨 Protective Action System

### Graduated Response Model

1. **THROTTLE** (Performance Degradation)
   - Slower processing to reduce resource pressure
   - Used for: CPU overload
   - Maintains functionality while reducing load

2. **DEFER** (Queue Management)
   - Delay non-critical operations
   - Used for: Memory pressure, token rates
   - Prioritizes essential operations

3. **REJECT** (Request Limiting) 
   - Refuse new requests when resources critical
   - Used for: Daily token limits
   - Protects existing operations

4. **SHUTDOWN** (System Protection)
   - Graceful shutdown when resources exhausted
   - Last resort protection mechanism
   - Prevents system crash/corruption

### Cooldown System
- Prevents action spam during resource pressure
- Configurable cooldown periods (default: 60 seconds)
- Balances responsiveness with stability

## 📈 Telemetry & Metrics

### v1.4.3 Required Metrics
```python
{
    "cpu_percent": float,                    # Current CPU usage
    "memory_mb": float,                      # Current memory in MB  
    "disk_usage_gb": float,                  # Disk usage in GB
    "network_bytes_sent": float,             # Network bytes sent
    "network_bytes_recv": float,             # Network bytes received
    "resource_monitor_uptime_seconds": float # Service uptime
}
```

### Legacy Compatibility Metrics
```python
{
    "tokens_used_hour": float,               # Token rate tracking
    "thoughts_active": float,                # Active thought count
    "warnings": float,                       # Warning count
    "critical": float                        # Critical issue count
}
```

## 💾 Data Sources

### System Resource Collection
- **psutil**: Cross-platform system and process utilities
- **Process-specific**: Memory, CPU usage for CIRIS process
- **System-wide**: Disk usage, network I/O counters

### CIRIS-specific Metrics
- **Database queries**: Active thought counting from SQLite
- **Token tracking**: In-memory deque with 24-hour retention
- **Historical data**: CPU averaging over 1-minute windows

## ⚙️ Configuration

### Default Resource Budget (4GB Target)
```python
# Memory: Critical at 3.75GB of 4GB limit
memory_mb = ResourceLimit(limit=4096, warning=3072, critical=3840, action=DEFER)

# CPU: Throttle when sustained high usage
cpu_percent = ResourceLimit(limit=80, warning=60, critical=75, action=THROTTLE)

# Tokens: Rate limiting for cost control  
tokens_hour = ResourceLimit(limit=10000, warning=8000, critical=9500, action=DEFER)
tokens_day = ResourceLimit(limit=100000, warning=80000, critical=95000, action=REJECT)

# Thoughts: Processing queue management
thoughts_active = ResourceLimit(limit=50, warning=40, critical=48, action=DEFER)
```

## 🔄 Service Lifecycle

### Initialization
```python
ResourceMonitorService(
    budget=ResourceBudget(),           # Resource limits
    db_path="/path/to/sqlite.db",      # Database for thought counting
    time_service=TimeService(),        # Timestamp provider
    signal_bus=ResourceSignalBus()     # Event coordination
)
```

### Runtime Operation
1. **1-second monitoring loop**: Update resource snapshot
2. **Limit checking**: Compare current usage against thresholds  
3. **Signal emission**: Send protective signals when limits exceeded
4. **Historical tracking**: Maintain rolling windows of usage data
5. **Health reporting**: Provide system health status

### Integration Points

#### Service Dependencies
- **Time Service**: Timestamp generation for rate limiting
- **Database Connection**: SQLite for active thought counting
- **Signal Handlers**: Other services register for resource events

#### API Integration
- Health endpoint integration via `is_healthy()`
- Telemetry metrics via `_collect_custom_metrics()`
- Status reporting through `get_status()`

## 🧪 Testing Strategy

### Test Coverage Areas
```python
# Core functionality tests
test_resource_monitoring()           # Basic monitoring operations
test_limit_enforcement()            # Threshold checking
test_signal_emission()              # Event system
test_token_tracking()               # Rate limiting

# Edge cases  
test_psutil_failures()              # System monitoring failures
test_database_unavailable()         # SQLite connection issues
test_cooldown_behavior()            # Action rate limiting
test_health_status_reporting()      # Status integration
```

### Mock-friendly Design
- Optional psutil dependency handling
- Configurable signal bus injection
- Time service abstraction for deterministic testing

## 🚀 Future Enhancements

### Planned Improvements
1. **Predictive Monitoring**: ML-based resource usage forecasting
2. **Dynamic Limits**: Adaptive thresholds based on historical patterns  
3. **Cross-Service Coordination**: Resource sharing negotiations
4. **Enhanced Metrics**: More granular performance tracking
5. **Module Conversion**: Convert from single .py file to proper module structure

### v1.5.0 Roadmap
- [ ] Convert to module directory structure
- [ ] Add predictive resource modeling
- [ ] Implement dynamic threshold adjustment
- [ ] Enhanced network monitoring
- [ ] Integration with external monitoring systems

## 📋 Service Migration Notice

**⚠️ ARCHITECTURE UPDATE REQUIRED:**

This service currently exists as a single Python file and needs conversion to module structure:

```
Current:  ciris_engine/logic/services/infrastructure/resource_monitor.py
Target:   ciris_engine/logic/services/infrastructure/resource_monitor/
          ├── __init__.py
          ├── service.py
          ├── signal_bus.py  
          └── README.md
```

This aligns with the modular architecture pattern used by other infrastructure services.

## 🎯 Mission Challenge Response

**How does Resource Monitor Service serve the 4GB RAM target and Meta-Goal M-1?**

### Direct 4GB RAM Enforcement
1. **Hard Limits**: Enforces 4GB memory limit with graduated warnings at 3GB and critical at 3.75GB
2. **Protective Actions**: Implements DEFER actions when memory pressure builds, preventing OOM conditions
3. **Real-time Monitoring**: 1-second monitoring loop catches memory growth before it becomes critical
4. **Historical Tracking**: Enables identification of memory usage patterns for optimization

### Meta-Goal M-1 Alignment: Sustainable Adaptive Coherence

**Sustainable**: 
- Enables deployment in resource-constrained environments worldwide
- Prevents system exhaustion that would threaten long-term operation
- Supports the "1000-year design" philosophy through disciplined resource management

**Adaptive**:
- Graduated response system adapts protection level to resource pressure
- Dynamic signal system allows other services to adapt their behavior
- Historical tracking enables learning and optimization over time

**Coherence**:
- Prevents resource exhaustion that would degrade decision-making quality
- Maintains system stability under varying load conditions  
- Enables predictable performance for reliable ethical reasoning

By enforcing the 4GB constraint, the Resource Monitor Service directly enables CIRIS deployment in developing regions, rural clinics, edge devices, and other resource-limited environments where ethical AI can have the greatest positive impact - truly serving diverse sentient beings in their pursuit of flourishing.

---

**Status**: ✅ Production Ready | 🔄 Module conversion pending | 📊 Full telemetry integration | 🎯 Mission-aligned