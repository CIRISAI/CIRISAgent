# CIRIS Incident Management Service

**Category**: Graph Services
**Location**: `ciris_engine/logic/services/graph/incident_service.py`
**Protocol**: `ciris_engine/protocols/services/graph/incident_management.py`
**Schemas**: `ciris_engine/schemas/services/graph/incident.py`
**Version**: 1.0.0
**Status**: ⚠️ NEEDS MODULE CONVERSION (single file → directory structure)

## Overview

The Incident Management Service implements **ITIL-aligned incident processing** for agent self-improvement through automated pattern detection, root cause analysis, and insight generation. It operates as a critical component of CIRIS's self-observational capabilities, transforming operational failures into learning opportunities.

### Mission Alignment: Meta-Goal M-1

**How Incident Tracking/Learning Serves Meta-Goal M-1:**

**Meta-Goal M-1**: *Promote sustainable adaptive coherence — the living conditions under which diverse sentient beings may pursue their own flourishing in justice and wonder.*

The Incident Management Service directly advances this mission through:

1. **Adaptive Coherence**: Transforms system failures into systematic improvements, enhancing the agent's ability to maintain coherent operation under diverse conditions

2. **Sustainable Operation**: Identifies and addresses systemic problems before they cascade, ensuring long-term operational stability that supports sustained engagement with diverse stakeholders

3. **Pattern Learning**: Extracts actionable insights from operational incidents, creating feedback loops that improve the agent's capacity to serve diverse needs without compromising any stakeholder

4. **Proactive Resilience**: Prevents recurring failures that could disrupt the conditions necessary for others to pursue their flourishing

5. **Transparent Self-Improvement**: Provides audit trails of how the agent learns from mistakes, building trust essential for ethical AI governance

## Architecture

### Core Components

The service manages three primary node types in the memory graph:

#### 1. IncidentNode
- **Purpose**: Captures individual incidents from WARNING/ERROR logs
- **Node Type**: `AUDIT_ENTRY`
- **Scope**: `LOCAL`
- **Key Fields**:
  - `incident_type`: ERROR, WARNING, EXCEPTION
  - `severity`: CRITICAL, HIGH, MEDIUM, LOW
  - `status`: OPEN, INVESTIGATING, RESOLVED, CLOSED, RECURRING
  - `source_component`: Component that generated the incident
  - `detected_at`: Timestamp of detection
  - **Technical Correlation**: correlation_id, task_id, thought_id, handler_name
  - **Code Location**: filename, line_number, function_name, stack_trace

#### 2. ProblemNode
- **Purpose**: Represents root causes identified from incident patterns
- **Node Type**: `CONCEPT`
- **Scope**: `IDENTITY`
- **Key Fields**:
  - `problem_statement`: Human-readable description
  - `affected_incidents`: List of related incident IDs
  - `potential_root_causes`: Identified underlying causes
  - `recommended_actions`: Suggested fixes
  - **Metrics**: incident_count, first_occurrence, last_occurrence

#### 3. IncidentInsightNode
- **Purpose**: Analysis results and recommendations from dream cycle processing
- **Node Type**: `CONCEPT`
- **Scope**: `LOCAL`
- **Key Fields**:
  - `insight_type`: PERIODIC_ANALYSIS, PATTERN_DETECTED, NO_INCIDENTS
  - `summary`: High-level analysis summary
  - `details`: Statistical breakdown (severity, component, time distribution)
  - **Recommendations**:
    - `behavioral_adjustments`: Changes to agent behavior
    - `configuration_changes`: System configuration updates
  - **Effectiveness Tracking**: applied, effectiveness_score

### Data Flow

```
Log Files → Incident Detection → Pattern Analysis → Problem Identification → Insight Generation
    ↓              ↓                    ↓                     ↓                    ↓
incidents_     IncidentNodes      Pattern Groups      ProblemNodes      IncidentInsightNode
latest.log    (Memory Graph)     (In-Memory)      (Memory Graph)      (Memory Graph)
```

## Core Functionality

### 1. Incident Processing (`process_recent_incidents`)

**Primary Method**: Called during **dream cycles** for self-improvement analysis

**Process**:
1. **Data Collection**: Retrieves incidents from last 24 hours (configurable)
2. **Pattern Detection**: Groups incidents by similarity, component, and time clusters
3. **Problem Identification**: Identifies root causes from recurring patterns
4. **Insight Generation**: Creates actionable recommendations
5. **Graph Storage**: Persists all analysis results in memory graph

**Input**: `hours: int = 24` (analysis window)
**Output**: `IncidentInsightNode` with complete analysis

### 2. Pattern Detection

**Similarity Grouping**:
- Groups incidents by error message similarity (first 3 words)
- Minimum threshold: 3 occurrences for pattern recognition

**Component Analysis**:
- Identifies components generating multiple incidents
- Minimum threshold: 5 incidents per component

**Time Clustering**:
- Detects error spikes (incidents within 5-minute windows)
- Minimum threshold: 5 incidents per cluster

### 3. Root Cause Analysis

**Automated Cause Detection**:
- **Timeout Issues**: "timeout" keywords → configuration adjustments
- **Connection Problems**: "connection" keywords → network/service availability
- **Resource Constraints**: "memory"/"resource" keywords → capacity planning
- **Authentication Issues**: "permission"/"auth" keywords → authorization config

**Component Isolation**:
- Single-component problems identified and flagged
- Multi-component issues marked for broader investigation

### 4. Recommendation Engine

**Behavioral Adjustments**:
- Retry logic with exponential backoff
- Additional error handling and logging
- Resource usage monitoring implementation
- Circuit breaker patterns for external services

**Configuration Changes**:
- Timeout value increases
- Memory limit adjustments
- Circuit breaker configuration
- Authentication/authorization settings

## Integration Points

### Memory Bus Integration
- **Storage**: All nodes persisted via MemoryBus.memorize()
- **Queries**: Search for recent incidents using MemorySearchFilter
- **Relationships**: Links incidents to problems and insights

### Time Service Dependency
- **Critical Dependency**: TimeService required for consistent timestamps
- **Usage**: All temporal calculations and node timestamps

### Dream Cycle Integration
- **Trigger**: Called during DREAM cognitive state
- **Frequency**: Typically every 24 hours during deep introspection
- **Purpose**: Transform operational data into systematic improvements

### Audit Trail
- **Complete Traceability**: All incidents, problems, and insights are auditable
- **Version Control**: Node versioning tracks analysis evolution
- **Attribution**: All updates attributed to IncidentManagementService

## Data Sources

### Primary Source: Log Files
- **Location**: `/app/logs/incidents_latest.log`
- **Format**: `YYYY-MM-DD HH:MM:SS.sss - LEVEL - component - file.py:line - message`
- **Fallback**: File parsing when MemoryBus unavailable

### Memory Graph Fallback
- **Primary**: Query via MemoryBus search functionality
- **Node Type Filter**: `NodeType.AUDIT_ENTRY`
- **Time Filtering**: `created_after` parameter for recent incidents

## Metrics & Telemetry

### Standard Metrics (v1.4.3 Compliance)
- `incidents_created`: Total incidents processed
- `incidents_resolved`: Incidents marked as resolved/analyzed
- `incidents_active`: Current open incidents (24-hour window)
- `incident_uptime_seconds`: Service uptime

### Analysis Metrics
- **Pattern Detection**: Number of patterns found per analysis
- **Problem Identification**: Root causes discovered
- **Recommendation Effectiveness**: Success rate of applied fixes

## Current Status & Technical Debt

### ⚠️ Module Conversion Required

The service currently exists as a single file (`incident_service.py`) but should be converted to a module directory structure like other graph services:

**Current**: `incident_service.py`
**Target Structure**:
```
incident_service/
├── __init__.py
├── service.py          # Main service implementation
├── README.md          # This documentation
└── patterns.py        # Pattern detection algorithms (future)
```

### Implementation Notes

1. **Error Handling**: Robust fallbacks when MemoryBus unavailable
2. **Performance**: Efficient pattern matching with configurable thresholds
3. **Extensibility**: Clean separation between detection, analysis, and recommendation phases
4. **Testing**: Comprehensive test suite with mock dependencies

### Dependencies

**Required Services**:
- MemoryService (via MemoryBus) - Graph storage and queries
- TimeService - Consistent temporal operations

**Bus Dependencies**:
- MemoryBus - All graph operations

## API Reference

### Public Methods

```python
async def process_recent_incidents(hours: int = 24) -> IncidentInsightNode
    """Main analysis method - called during dream cycles"""

async def get_incident_count(hours: int = 1) -> int
    """Get count of incidents in time window"""

def get_capabilities() -> ServiceCapabilities
    """Return service capabilities"""

def get_status() -> ServiceStatus
    """Get current service status"""

async def get_metrics() -> Dict[str, float]
    """Get service metrics (v1.4.3 compliant)"""
```

### Protocol Compliance

Implements `IncidentManagementServiceProtocol` which extends:
- `GraphServiceProtocol` - Graph operations
- `ServiceProtocol` - Standard service lifecycle

## Configuration

### Analysis Parameters
- **Default Analysis Window**: 24 hours
- **Pattern Thresholds**:
  - Similarity grouping: 3+ incidents
  - Component issues: 5+ incidents
  - Time clustering: 5+ incidents in 5-minute window
- **Storage Scope**:
  - Incidents: LOCAL scope
  - Problems: IDENTITY scope (agent learning)
  - Insights: LOCAL scope

### Service Configuration
- **Service Name**: "IncidentManagementService"
- **Service Type**: ServiceType.AUDIT
- **ITIL Aligned**: True
- **Version**: "1.0.0"

## Future Enhancements

1. **Machine Learning**: Advanced pattern recognition algorithms
2. **Integration**: Direct integration with monitoring systems
3. **Predictive Analysis**: Proactive incident prevention
4. **Effectiveness Tracking**: Closed-loop measurement of fix success rates
5. **Module Structure**: Convert to directory-based organization

## Testing

Comprehensive test suite located at:
`tests/ciris_engine/logic/services/graph/test_incident_service.py`

**Test Coverage**:
- Incident processing with various scenarios
- Pattern detection algorithms
- Root cause analysis logic
- Mock dependencies (MemoryBus, TimeService)
- Error handling and fallback scenarios

---

*This service exemplifies CIRIS's commitment to continuous self-improvement, transforming operational challenges into opportunities for enhanced service to diverse stakeholders in pursuit of sustainable adaptive coherence.*
