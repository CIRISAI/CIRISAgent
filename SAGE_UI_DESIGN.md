# Sage GDPR Compliance Management UI - MVP Design

**Based on**: ScoutGUI architecture + multi-source-dsar-orchestration branch APIs
**Purpose**: Configure and manage a GDPR compliance agent in a client environment
**Target Users**: Compliance officers, data protection officers, system administrators

---

## 1. Architecture Overview

### Technology Stack
- **Frontend**: Next.js 14 with TypeScript (based on ScoutGUI)
- **UI Components**: shadcn/ui components (matching ScoutGUI)
- **SDK**: TypeScript CIRIS SDK (extend with new DSAR/Connector resources)
- **State Management**: React Query for server state
- **Auth**: Role-based access control (ADMIN, SYSTEM_ADMIN, COMPLIANCE_OFFICER)

### Key Principles
1. **ScoutGUI Patterns**: Reuse Layout, Protected Routes, Modal workflows
2. **Type Safety**: Extend CIRIS SDK with multi-source DSAR resources
3. **Simplicity**: Focus on essential GDPR workflows
4. **Compliance-First**: Audit trails, verification, transparency

---

## 2. Core Features & Pages

### 2.1 Dashboard (`/dashboard`)
**Purpose**: Overview of GDPR compliance status

**Sections**:
```typescript
interface DashboardData {
  // Overall Status
  compliance_score: number;           // 0-100%
  active_connectors: number;
  pending_dsar_requests: number;
  completed_this_month: number;

  // Recent Activity
  recent_requests: DSARTicketSummary[];
  recent_connector_tests: ConnectorTestResult[];

  // Alerts
  expiring_consents: number;
  failed_connectors: ConnectorInfo[];
  overdue_requests: DSARTicketSummary[];
}
```

**UI Components**:
- **Status Cards** (4 metric cards at top)
  - Compliance Score (with trend)
  - Active Data Sources
  - Pending Requests (with urgency badge)
  - Monthly Completions

- **Activity Timeline** (left 2/3)
  - Recent DSAR requests with status badges
  - Connector health checks
  - System events

- **Alerts Panel** (right 1/3)
  - Failed connectors (red)
  - Overdue requests (yellow)
  - Expiring consents (blue)

**ScoutGUI Pattern**: Similar to `/system` page with cards + timeline

---

### 2.2 Data Sources (`/data-sources`)
**Purpose**: Manage external data connectors (SQL, REST, HL7)

**Sub-pages**:
- `/data-sources` - List all connectors
- `/data-sources/new` - Register new connector
- `/data-sources/{id}` - Connector details (modal)

#### 2.2.1 Connector List
**Features**:
- **Filter Bar**: Type (SQL/REST/HL7), Status (healthy/unhealthy), Last tested
- **Search**: By name or ID
- **Table Columns**:
  - Connector Name
  - Type (badge with icon)
  - Status (health indicator)
  - Last Tested
  - Total Requests
  - Actions (Test, Edit, Delete)

**Actions**:
- **Test Connection**: In-line latency test
- **View Privacy Schema**: Modal showing PII mappings
- **Edit Configuration**: Modal form
- **Delete**: Confirmation dialog

#### 2.2.2 New Connector Form
**SQL Connector Fields**:
```typescript
interface SQLConnectorForm {
  connector_name: string;
  database_type: 'postgres' | 'mysql' | 'sqlite' | 'mssql' | 'oracle';
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;  // masked input
  ssl_enabled: boolean;
  privacy_schema?: PrivacySchemaConfig;  // YAML editor or JSON
  max_connections?: number;
  timeout_seconds?: number;
}
```

**REST Connector Fields**:
```typescript
interface RESTConnectorForm {
  connector_name: string;
  base_url: string;
  auth_type: 'none' | 'basic' | 'bearer' | 'oauth2' | 'api_key';
  auth_credentials?: Record<string, string>;
  headers?: Record<string, string>;
  privacy_endpoints?: PrivacyEndpointConfig;
  timeout_seconds?: number;
}
```

**Privacy Schema Editor**:
- **YAML/JSON Toggle**: Switch between YAML and JSON view
- **Visual Builder** (future): Drag-and-drop PII mapping
- **Schema Validator**: Real-time validation
- **Examples Dropdown**: Pre-filled templates

**ScoutGUI Pattern**: Similar to `/users` Add User Modal + `/config` editor

---

### 2.3 DSAR Requests (`/dsar`)
**Purpose**: Submit and track Data Subject Access Requests

**Sub-pages**:
- `/dsar` - List all DSAR tickets
- `/dsar/new` - Submit new DSAR
- `/dsar/{ticket_id}` - Request details (modal)

#### 2.3.1 DSAR List
**Filters**:
- Request Type (Access, Delete, Export, Correct)
- Status (Pending, In Progress, Completed, Failed)
- Date Range
- Urgent Flag

**Table Columns**:
- Ticket ID (clickable)
- Request Type (badge)
- Email
- User Identifier
- Status (progress indicator)
- Sources (e.g., "3/5 complete")
- Submitted Date
- Estimated Completion
- Actions (View, Cancel)

**Bulk Actions**:
- Export selected (CSV/JSON)
- Mark as urgent
- Assign to reviewer

#### 2.3.2 Submit New DSAR
**Form**:
```typescript
interface DSARSubmissionForm {
  request_type: 'access' | 'delete' | 'export' | 'correct';
  email: string;
  user_identifier: string;  // Email, Discord ID, etc.
  export_format?: 'json' | 'xml' | 'csv';  // For export requests
  corrections?: Record<string, any>;       // For correction requests
  details?: string;                        // Free-text description
  urgent: boolean;
}
```

**Validation**:
- Email format validation
- User identifier required
- Corrections required if type = 'correct'
- Export format required if type = 'export'

**Multi-Step Form**:
1. **Step 1**: Request Type Selection (4 large cards)
2. **Step 2**: User Identification (email + identifier)
3. **Step 3**: Type-Specific Fields (export format, corrections, etc.)
4. **Step 4**: Review & Submit

**Progress Indicator**: ScoutGUI `StepVisualization` component

#### 2.3.3 DSAR Details Modal
**Sections**:
- **Header**: Ticket ID, Status badge, Timestamps
- **User Information**: Email, Identifier, Urgent flag
- **Source Progress**:
  - Progress bar: "3/5 sources complete"
  - List of sources with status icons
- **Results Tabs**:
  - **CIRIS Data**: DSARAccessPackage display
  - **External Sources**: Per-source data exports
  - **Identity Resolution**: UserIdentityNode graph
  - **Audit Trail**: Timeline of request processing

**Actions**:
- Download Package (JSON/PDF)
- View Verification Report
- Cancel Request (if in progress)
- Mark as Reviewed

**ScoutGUI Pattern**: Similar to `/users` UserDetailsModal

---

### 2.4 Privacy Schemas (`/privacy-schemas`)
**Purpose**: Manage PII mappings and data classifications

**Features**:
- **Schema Library**: Pre-built schemas for common databases
- **Custom Schemas**: Create/edit YAML privacy schemas
- **Schema Validator**: Real-time validation
- **Schema Templates**: Industry-specific templates (healthcare, finance, etc.)

**Schema Editor**:
```yaml
# Example Privacy Schema
version: "1.0"
database: "customer_db"
tables:
  users:
    pii_columns:
      - name: "email"
        category: "contact_info"
        retention_days: 2555  # 7 years
      - name: "phone"
        category: "contact_info"
      - name: "ssn"
        category: "sensitive_id"
        encrypted: true
    identity_columns:
      - "user_id"
      - "email"
  orders:
    pii_columns:
      - name: "billing_address"
        category: "financial"
    foreign_keys:
      - column: "user_id"
        references: "users.user_id"
```

**Visual Schema Builder** (Future):
- Drag database schema from left
- Drop PII categories onto columns
- Auto-generate YAML

**ScoutGUI Pattern**: Based on `/config` with YAML editor

---

### 2.5 Compliance Reports (`/reports`)
**Purpose**: Generate audit reports for regulators

**Report Types**:
1. **DSAR Compliance Report**
   - Total requests (30-day window adherence)
   - Response time statistics
   - Completion rate

2. **Data Source Inventory**
   - All registered connectors
   - PII categories per source
   - Data retention policies

3. **Consent Audit Report**
   - Consent grants/revocations
   - Decay protocol execution
   - Partnership status

4. **Security Audit**
   - Authentication events
   - Data access logs
   - Encryption status

**Export Formats**: PDF, CSV, JSON

**ScoutGUI Pattern**: Based on `/audit` with export buttons

---

### 2.6 Settings (`/settings`)
**Purpose**: System configuration and preferences

**Sections**:
1. **GDPR Configuration**
   - Default response window (days)
   - Auto-delete after completion
   - Email notifications

2. **Identity Resolution**
   - Enable/disable identity graph
   - Matching thresholds
   - Trusted identifiers

3. **Notification Settings**
   - Email templates
   - Webhook endpoints
   - Slack/Discord integration

4. **Security Settings**
   - Encryption settings
   - Data retention policies
   - Access controls

**ScoutGUI Pattern**: Based on `/account/settings`

---

## 3. Navigation Structure

### Primary Navigation (Top Bar)
```
[Logo] Dashboard | Data Sources | DSAR | Reports | Settings | [User Menu]
```

### Role-Based Access
```typescript
const navigation = [
  { name: "Dashboard", href: "/dashboard", minRole: "OBSERVER" },
  { name: "Data Sources", href: "/data-sources", minRole: "ADMIN" },
  { name: "DSAR Requests", href: "/dsar", minRole: "COMPLIANCE_OFFICER" },
  { name: "Privacy Schemas", href: "/privacy-schemas", minRole: "ADMIN" },
  { name: "Reports", href: "/reports", minRole: "COMPLIANCE_OFFICER" },
  { name: "Settings", href: "/settings", minRole: "ADMIN" },
];
```

---

## 4. Extended TypeScript SDK

### New Resources to Add

#### 4.1 Multi-Source DSAR Resource
```typescript
// lib/ciris-sdk/resources/dsar-multi-source.ts
export class DSARMultiSourceResource extends BaseResource {
  async submitMultiSource(data: MultiSourceDSARRequest): Promise<MultiSourceDSARResponse> {
    return this.transport.post('/v1/dsar/multi-source', data);
  }

  async getStatus(ticketId: string): Promise<MultiSourceDSARStatusResponse> {
    return this.transport.get(`/v1/dsar/multi-source/${ticketId}`);
  }

  async getPartialResults(ticketId: string): Promise<PartialResultsResponse> {
    return this.transport.get(`/v1/dsar/multi-source/${ticketId}/partial`);
  }

  async cancel(ticketId: string): Promise<CancellationResponse> {
    return this.transport.delete(`/v1/dsar/multi-source/${ticketId}`);
  }
}
```

#### 4.2 Connectors Resource
```typescript
// lib/ciris-sdk/resources/connectors.ts
export class ConnectorsResource extends BaseResource {
  async registerSQL(config: SQLConnectorConfig): Promise<ConnectorRegistrationResponse> {
    return this.transport.post('/v1/connectors/sql', {
      connector_type: 'sql',
      config
    });
  }

  async list(connectorType?: string): Promise<ConnectorListResponse> {
    const params = connectorType ? { connector_type: connectorType } : {};
    return this.transport.get('/v1/connectors', { params });
  }

  async test(connectorId: string): Promise<ConnectorTestResult> {
    return this.transport.post(`/v1/connectors/${connectorId}/test`);
  }

  async update(connectorId: string, update: ConnectorUpdateRequest): Promise<void> {
    return this.transport.patch(`/v1/connectors/${connectorId}`, update);
  }

  async delete(connectorId: string): Promise<void> {
    return this.transport.delete(`/v1/connectors/${connectorId}`);
  }
}
```

#### 4.3 Update CIRISClient
```typescript
// lib/ciris-sdk/client.ts
import { DSARMultiSourceResource } from './resources/dsar-multi-source';
import { ConnectorsResource } from './resources/connectors';

export class CIRISClient {
  // ... existing resources ...
  public readonly dsarMultiSource: DSARMultiSourceResource;
  public readonly connectors: ConnectorsResource;

  constructor(options: CIRISClientOptions = {}) {
    // ... existing setup ...
    this.dsarMultiSource = new DSARMultiSourceResource(this.transport);
    this.connectors = new ConnectorsResource(this.transport);
  }
}
```

---

## 5. Key UI Components

### 5.1 ConnectorCard Component
```typescript
interface ConnectorCardProps {
  connector: ConnectorInfo;
  onTest: (id: string) => void;
  onEdit: (connector: ConnectorInfo) => void;
  onDelete: (id: string) => void;
}

// Visual: Card with icon, name, status badge, health indicator, actions
```

### 5.2 DSARStatusBadge Component
```typescript
interface DSARStatusBadgeProps {
  status: 'pending_review' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  sourcesCompleted?: number;
  totalSources?: number;
}

// Visual: Badge with color + optional progress indicator
```

### 5.3 PrivacySchemaEditor Component
```typescript
interface PrivacySchemaEditorProps {
  initialSchema?: string;
  format: 'yaml' | 'json';
  onSave: (schema: string) => void;
  onValidate: (schema: string) => ValidationResult;
}

// Visual: Monaco editor with syntax highlighting + validation
```

### 5.4 MultiSourceProgress Component
```typescript
interface MultiSourceProgressProps {
  sources: {
    source_id: string;
    source_name: string;
    status: 'pending' | 'in_progress' | 'completed' | 'failed';
  }[];
}

// Visual: List with icons showing status per source
```

---

## 6. Workflows

### 6.1 Register New SQL Connector
1. Click "Add Data Source" button
2. Select "SQL Database" card
3. Fill form (database type, credentials, etc.)
4. [Optional] Upload/paste privacy schema
5. Test connection (in-modal)
6. Save connector
7. Success toast + redirect to connector list

### 6.2 Submit Multi-Source DSAR
1. Click "New DSAR Request"
2. Select request type (Access/Delete/Export/Correct)
3. Enter email + user identifier
4. [Conditional] Add type-specific fields
5. Review summary
6. Submit request
7. Real-time progress modal showing source completion
8. Download results when complete

### 6.3 Review DSAR Results
1. Click ticket in DSAR list
2. View modal with tabs:
   - Summary (metadata)
   - CIRIS Data (internal export)
   - External Sources (per-source data)
   - Identity Graph (visual)
   - Audit Trail (timeline)
3. Download full package (JSON/PDF)
4. Mark as reviewed

---

## 7. Data Visualizations

### 7.1 Compliance Score Gauge
- **Type**: Radial gauge (0-100%)
- **Colors**: Red (0-60), Yellow (61-80), Green (81-100)
- **Factors**: Response time, completion rate, connector health

### 7.2 DSAR Response Time Chart
- **Type**: Line chart (last 30 days)
- **Y-axis**: Hours to completion
- **X-axis**: Date
- **Threshold Line**: 30-day GDPR requirement

### 7.3 Data Source Health Map
- **Type**: Grid of cards (one per connector)
- **Indicators**: Green (healthy), Yellow (warning), Red (failed)
- **Tooltip**: Last test time + latency

### 7.4 Identity Resolution Graph
- **Type**: Network graph (D3.js or similar)
- **Nodes**: User identifiers (email, Discord ID, etc.)
- **Edges**: Identity matches
- **Colors**: Confidence level

---

## 8. Error Handling & Edge Cases

### 8.1 Connector Failures
- **Timeout**: Retry with exponential backoff
- **Auth Error**: Display error + edit credentials button
- **Network Error**: Show offline indicator + retry button

### 8.2 Partial DSAR Results
- **Scenario**: Some sources complete, others fail
- **UI**: Show partial results with warnings
- **Action**: Offer retry for failed sources

### 8.3 Privacy Schema Validation
- **Invalid YAML**: Inline error highlighting
- **Missing Required Fields**: Form validation
- **Conflicting Mappings**: Warning modal

---

## 9. Security Considerations

### 9.1 Credential Storage
- **Passwords**: Never display in UI (masked inputs)
- **API Keys**: Truncated display (e.g., "sk-...abc123")
- **Encryption**: All sensitive fields encrypted at rest

### 9.2 Access Control
- **COMPLIANCE_OFFICER**: Can submit/view DSAR requests
- **ADMIN**: Can manage connectors + privacy schemas
- **SYSTEM_ADMIN**: Full access + security settings

### 9.3 Audit Trail
- All actions logged:
  - Connector creation/modification
  - DSAR submissions
  - Data exports
  - Configuration changes

---

## 10. MVP Feature Priority

### Phase 1 (MVP - 2-3 weeks)
✅ **Must Have**:
1. Dashboard (basic metrics)
2. Data Sources (SQL connector CRUD)
3. DSAR Requests (submit + list)
4. Basic privacy schema editor (YAML)

### Phase 2 (Post-MVP - 4-6 weeks)
🎯 **Should Have**:
1. REST/HL7 connectors
2. Advanced reporting
3. Visual privacy schema builder
4. Identity resolution graph
5. Webhook notifications

### Phase 3 (Future)
💡 **Nice to Have**:
1. AI-assisted schema generation
2. Automated compliance scoring
3. Multi-language support
4. Mobile app
5. Slack/Discord bot integration

---

## 11. Development Checklist

### Frontend Setup
- [ ] Fork ScoutGUI as base template
- [ ] Extend TypeScript SDK with new resources
- [ ] Create page structure (`/dashboard`, `/data-sources`, `/dsar`)
- [ ] Build reusable components (ConnectorCard, DSARStatusBadge, etc.)
- [ ] Implement role-based routing

### Backend Integration
- [ ] Verify `/v1/dsar/multi-source` endpoints
- [ ] Verify `/v1/connectors` endpoints
- [ ] Test end-to-end DSAR flow
- [ ] Implement privacy schema validation
- [ ] Add connector health checks

### Testing
- [ ] Unit tests for SDK resources
- [ ] Integration tests for DSAR workflows
- [ ] E2E tests for critical paths
- [ ] Accessibility audit (WCAG 2.1 AA)
- [ ] Performance testing (bundle size, load time)

### Documentation
- [ ] User guide (markdown + screenshots)
- [ ] Admin guide (deployment, configuration)
- [ ] API reference (SDK methods)
- [ ] Privacy schema specification
- [ ] Video tutorials

---

## 12. Design Mockup References

### Color Palette (GDPR-themed)
```css
--primary: #3B82F6;      /* Blue - Trust */
--secondary: #8B5CF6;    /* Purple - Authority */
--success: #10B981;      /* Green - Compliance */
--warning: #F59E0B;      /* Yellow - Attention */
--danger: #EF4444;       /* Red - Violation */
--neutral: #6B7280;      /* Gray - Neutral */
```

### Typography
- **Headings**: Inter (same as ScoutGUI)
- **Body**: Inter
- **Code**: JetBrains Mono

### Icons
- **Data Sources**: DatabaseIcon, ServerIcon, CloudIcon
- **DSAR Types**: FileSearchIcon, TrashIcon, DownloadIcon, EditIcon
- **Status**: CheckCircleIcon, XCircleIcon, ClockIcon, AlertTriangleIcon

---

## 13. Sample API Integration

### Submit Multi-Source DSAR
```typescript
// app/dsar/new/page.tsx
const handleSubmit = async (formData: DSARSubmissionForm) => {
  try {
    const response = await cirisClient.dsarMultiSource.submitMultiSource({
      request_type: formData.request_type,
      email: formData.email,
      user_identifier: formData.user_identifier,
      export_format: formData.export_format,
      corrections: formData.corrections,
      details: formData.details,
      urgent: formData.urgent,
    });

    toast.success(`DSAR request submitted: ${response.data.ticket_id}`);
    router.push(`/dsar/${response.data.ticket_id}`);
  } catch (error) {
    toast.error('Failed to submit DSAR request');
    console.error(error);
  }
};
```

### List Connectors with Filtering
```typescript
// app/data-sources/page.tsx
const { data: connectors } = useQuery({
  queryKey: ['connectors', selectedType],
  queryFn: () => cirisClient.connectors.list(selectedType),
});
```

---

## 14. Deployment Considerations

### Environment Variables
```bash
NEXT_PUBLIC_CIRIS_API_URL=https://agents.ciris.ai/api/sage/v1
NEXT_PUBLIC_AGENT_ID=sage
CIRIS_ADMIN_EMAIL=compliance@company.com
```

### Docker Deployment
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
COPY . .
RUN npm run build
CMD ["npm", "start"]
```

### Nginx Reverse Proxy
```nginx
location /sage {
  proxy_pass http://localhost:3000;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

---

## 15. Success Metrics

### User Adoption
- Active users per week
- DSAR requests submitted per month
- Connectors registered per organization

### Performance
- Average DSAR response time < 10 seconds
- Connector health check success rate > 95%
- Page load time < 2 seconds

### Compliance
- 30-day GDPR deadline adherence > 99%
- Zero data breaches
- 100% audit trail coverage

---

## Conclusion

The **Sage GDPR Compliance Management UI** MVP focuses on:

1. **Data Source Management**: Easy registration and testing of SQL/REST/HL7 connectors
2. **Multi-Source DSAR**: Streamlined submission and tracking of GDPR requests
3. **Privacy Schemas**: YAML-based PII mapping and classification
4. **Compliance Dashboard**: At-a-glance view of GDPR health
5. **Audit Reports**: Regulator-ready compliance reports

By leveraging ScoutGUI's architecture and the new multi-source DSAR APIs, Sage provides a production-ready interface for GDPR compliance with minimal development effort.

**Next Steps**:
1. Review this design with stakeholders
2. Prioritize Phase 1 features
3. Set up development environment (fork ScoutGUI)
4. Begin SDK extension and page implementation
5. Iterate based on user feedback
