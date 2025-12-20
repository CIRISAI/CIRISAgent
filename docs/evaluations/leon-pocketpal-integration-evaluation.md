# Leon AI & PocketPal Integration Evaluation

**Date**: December 2024
**Status**: Evaluation Complete
**Branch**: `claude/evaluate-leon-pocketpal-integration-jVQ4b`

---

## Executive Summary

This document evaluates integration possibilities between CIRISAgent and two open-source AI projects:
- **Leon AI**: Server-based personal assistant with modular skills
- **PocketPal AI**: Mobile LLM inference app

Both projects offer complementary capabilities that could extend CIRIS's reach across voice interfaces, mobile platforms, and skill ecosystems.

---

## 1. Leon AI Overview

### Architecture
- **Core**: Node.js + TypeScript (39.3%) with Python bridge (36.1%)
- **Skills**: Python modules with standardized interfaces
- **Voice**: TTS/STT via Google Cloud, AWS, IBM Watson, or offline (CMU Flite, Coqui)
- **NLP**: Hybrid processing combining LLM, classification, and rule-based NLP
- **Communication**: TCP server for inter-process communication

### Key Components
| Component | Technology | Purpose |
|-----------|------------|---------|
| Server | Node.js/TypeScript | Central orchestration |
| Skills | Python modules | Extensible capabilities |
| Python Bridge | TCP socket | Skill execution |
| Hotword | Various engines | Voice activation |
| Web App | React/Vue | User interface |

### Sources
- [Leon Official Site](https://getleon.ai/)
- [Leon GitHub Repository](https://github.com/leon-ai/leon)
- [Leon Documentation](https://docs.getleon.ai/)

---

## 2. PocketPal AI Overview

### Architecture
- **Framework**: React Native (TypeScript)
- **Inference**: llama.cpp via [llama.rn](https://github.com/a-ghorbani/llama.rn) bindings
- **State**: MobX reactive state management
- **Models**: GGUF quantized models (local or Hugging Face Hub)
- **Platforms**: iOS and Android

### Key Features
| Feature | Description |
|---------|-------------|
| On-device LLM | Full privacy, no cloud dependency |
| Metal/GPU acceleration | Hardware-optimized inference |
| Memory management | Auto offload/load on background |
| Pals system | Personalized AI assistants |
| Benchmarking | Performance comparison tools |

### Sources
- [PocketPal GitHub Repository](https://github.com/a-ghorbani/pocketpal-ai)
- [PocketPal Documentation](https://pocketpal.llm-ventures.com/)

---

## 3. CIRISAgent Architecture Alignment

### Current Adapter System
CIRISAgent uses a modular adapter architecture that maps well to both integrations:

```
ciris_engine/logic/adapters/
├── base_adapter.py          # Abstract base
├── api/                     # REST/WebSocket adapter
├── discord/                 # Discord bot adapter
├── cli/                     # Development CLI
└── [leon/]                  # Proposed Leon adapter
└── [pocketpal/]             # Proposed PocketPal adapter
```

### Service Bus Compatibility
| CIRIS Bus | Leon Mapping | PocketPal Mapping |
|-----------|--------------|-------------------|
| CommunicationBus | Voice/text I/O | Chat interface |
| LLMBus | NLP processing | Local llama.cpp inference |
| ToolBus | Leon skills | N/A (UI focused) |
| MemoryBus | Shared context | Local state sync |
| WiseBus | Decision guidance | N/A |

---

## 4. Leon Integration Analysis

### 4.1 Integration Approach: CIRIS as Leon Skill Provider

**Concept**: Create a Leon skill that connects to CIRIS as a backend, exposing CIRIS capabilities through Leon's voice/text interface.

#### Architecture
```
[User Voice/Text]
      ↓
[Leon Server] ←→ [Leon-CIRIS Skill]
      ↓                    ↓
[Hotword/STT]    [CIRIS API Adapter]
      ↓                    ↓
[TTS Response]   [CIRISAgent Backend]
```

#### Implementation Path

**Option A: Leon Skill → CIRIS API**
```python
# skills/ciris/ciris_bridge.py
import requests
from leon import skill

class CIRISBridge(skill.Skill):
    def __init__(self):
        self.ciris_endpoint = "http://localhost:8000/v1"
        self.token = self._authenticate()

    @skill.action("ask_ciris")
    async def forward_to_ciris(self, query: str) -> str:
        response = requests.post(
            f"{self.ciris_endpoint}/agent/interact",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"message": query}
        )
        return response.json().get("response", "No response")
```

**Option B: CIRIS Leon Adapter**
```python
# ciris_adapters/leon/adapter.py
class LeonAdapter(BaseAdapter):
    """CIRIS adapter that presents as a Leon TCP client."""

    async def start(self):
        self.tcp_client = await self._connect_leon_bridge()
        await self._register_ciris_skills()

    async def handle_leon_request(self, skill_name: str, params: dict):
        # Route Leon skill requests to CIRIS handlers
        tool_result = await self.bus_manager.tool.execute_tool(
            tool_name=skill_name,
            parameters=params
        )
        return tool_result
```

#### Leon Skills as CIRIS Tools

Leon skills could be exposed as CIRIS tools through the ToolBus:

```python
# Tool registration from Leon skills
@dataclass
class LeonSkillTool:
    name: str = "leon.calendar.add_event"
    description: str = "Add calendar event via Leon"
    parameters: ToolParameterSchema = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "datetime": {"type": "string", "format": "date-time"},
            "duration_minutes": {"type": "integer"}
        }
    })
```

#### Voice Interface Integration

Leon's TTS/STT capabilities could provide CIRIS with voice I/O:

| Leon Capability | CIRIS Integration |
|-----------------|-------------------|
| Google Cloud STT | Voice input to CommunicationBus |
| AWS Polly TTS | Voice output from responses |
| Hotword detection | Ambient activation trigger |
| Offline STT (Coqui) | Privacy-preserving voice input |

### 4.2 Effort Estimate

| Component | Complexity | Notes |
|-----------|------------|-------|
| Leon skill for CIRIS | Low | HTTP client to CIRIS API |
| CIRIS Leon adapter | Medium | TCP protocol, skill registry |
| Skills → Tools bridge | Medium | Bidirectional skill/tool mapping |
| Voice I/O integration | High | Audio streaming, latency handling |

### 4.3 Benefits
- Voice interface without building TTS/STT infrastructure
- Access to Leon's existing skill ecosystem
- Offline voice operation capability
- Cross-platform desktop deployment (Linux, macOS, Windows)

### 4.4 Challenges
- Leon is undergoing major architecture changes (develop branch unstable)
- TCP protocol requires careful error handling
- Voice latency for real-time conversation
- Two separate processes to manage

---

## 5. PocketPal Integration Analysis

### 5.1 Integration Approach: PocketPal as Mobile Frontend

**Concept**: PocketPal could serve as a mobile interface to CIRIS, with local LLM fallback when offline.

#### Architecture Options

**Option A: PocketPal as CIRIS Mobile Client**
```
[PocketPal Mobile App]
         ↓
[API Client Module] ←→ [CIRIS API Adapter]
         ↓                    ↓
[Local LLM Fallback]   [Full CIRIS Backend]
```

**Option B: Hybrid Local + Remote**
```
[PocketPal with CIRIS "Pal"]
         ↓
[Online?] → Yes → [CIRIS API for complex tasks]
    ↓
   No → [Local GGUF model for simple queries]
```

### 5.2 Implementation Path

#### PocketPal CIRIS Pal Configuration
PocketPal's "Pals" feature allows creating personalized AI assistants. A CIRIS Pal could be:

```typescript
// src/pals/ciris_pal.ts
interface CIRISPal {
  name: "CIRIS Agent",
  systemPrompt: "You are connected to CIRIS backend...",
  apiEndpoint: "https://agents.ciris.ai/api/{agent_id}/v1",
  useLocalFallback: true,
  localModel: "qwen2.5-1.5b-q4_k_m.gguf"
}
```

#### React Native CIRIS SDK
A dedicated module for PocketPal to communicate with CIRIS:

```typescript
// src/services/ciris_client.ts
export class CIRISClient {
  private baseUrl: string;
  private token: string;

  async interact(message: string): Promise<CIRISResponse> {
    const response = await fetch(`${this.baseUrl}/agent/interact`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ message })
    });
    return response.json();
  }

  async executeTools(tools: ToolRequest[]): Promise<ToolResponse[]> {
    // Batch tool execution for mobile efficiency
  }
}
```

### 5.3 Local LLM as CIRISAgent Backend

PocketPal's llama.cpp integration could potentially serve as a local LLM provider for CIRIS:

```python
# ciris_adapters/pocketpal/llm_provider.py
class PocketPalLLMProvider:
    """Use PocketPal's local model as CIRIS LLM backend."""

    async def complete(self, prompt: str, **kwargs) -> str:
        # Connect to PocketPal's exposed inference endpoint
        # or use shared llama.cpp bindings
        pass
```

However, this is complex due to:
- React Native ↔ Python interop challenges
- Mobile device resource constraints
- Battery/thermal considerations

### 5.4 Shared Model Repository

Both could share GGUF models from the same source:

```yaml
# Shared model configuration
models:
  base_path: "~/.ciris/models"
  sources:
    - huggingface_hub
    - local_cache
  formats:
    - gguf  # PocketPal compatible
    - onnx  # Desktop optimized
```

### 5.5 Effort Estimate

| Component | Complexity | Notes |
|-----------|------------|-------|
| PocketPal API client | Low | HTTP client for CIRIS API |
| CIRIS Pal integration | Low | Configuration-based |
| Offline/online sync | Medium | State reconciliation |
| Local LLM fallback | Medium | Context preservation |
| Shared model repo | Low | File system conventions |

### 5.6 Benefits
- Mobile CIRIS access on iOS/Android
- Offline capability with local models
- Privacy-preserving on-device inference
- Existing polished mobile UI

### 5.7 Challenges
- PocketPal is a separate codebase (React Native)
- Would require forking or contribution upstream
- Mobile resource constraints limit CIRIS capabilities
- Real-time sync complexity

---

## 6. UI/UX Integration Considerations

### 6.1 Unified Experience Design

| Platform | Primary Interface | CIRIS Role |
|----------|-------------------|------------|
| Desktop (Leon) | Voice + Web UI | Backend intelligence |
| Mobile (PocketPal) | Chat UI | API provider + fallback |
| Web (API Adapter) | REST/WebSocket | Full control |
| Discord | Chat + Slash commands | Community moderation |

### 6.2 Cross-Platform Identity

CIRIS's identity should remain consistent across platforms:

```python
# Consistent identity expression
class CIRISIdentity:
    name: str = "CIRIS"
    persona: str = "Ethical AI assistant"
    voice_profile: VoiceSettings  # For Leon TTS
    avatar: str  # For PocketPal UI
    capabilities_message: str  # Platform-appropriate limits
```

### 6.3 UI Component Sharing

| Component | Leon | PocketPal | CIRIS |
|-----------|------|-----------|-------|
| Chat bubbles | Web app | React Native | API response format |
| Settings | Config files | MobX state | Config service |
| History | Local DB | AsyncStorage | Memory graph |
| Themes | CSS | React Native Paper | N/A (backend) |

### 6.4 Accessibility

Leon's voice interface and PocketPal's mobile-first design both improve CIRIS accessibility:

- **Voice I/O**: Hands-free operation for accessibility needs
- **Mobile**: Access from anywhere, low-power devices
- **Offline**: No internet dependency for core functions

---

## 7. Recommended Integration Strategy

### Phase 1: Leon Skill (Low Effort, High Value)
1. Create a Leon skill package that calls CIRIS API
2. Expose key CIRIS tools as Leon actions
3. Use Leon's voice I/O as optional interface
4. Target: 2-3 days development

```
leon/skills/ciris/
├── __init__.py
├── ciris_bridge.py      # API client
├── actions/
│   ├── query.py         # General queries
│   ├── memory.py        # Memory operations
│   └── tools.py         # Tool execution
└── manifest.json
```

### Phase 2: PocketPal Pal (Low Effort)
1. Create CIRIS "Pal" configuration for PocketPal
2. Implement API client in TypeScript
3. Add offline fallback with local model
4. Target: 1-2 days development

### Phase 3: CIRIS Leon Adapter (Medium Effort)
1. Full bidirectional Leon integration
2. Leon skills exposed as CIRIS tools
3. Voice I/O through CommunicationBus
4. Target: 1-2 weeks development

```
ciris_adapters/leon/
├── __init__.py
├── manifest.json
├── adapter.py           # Leon TCP client
├── observer.py          # Message handling
├── skill_bridge.py      # Skill ↔ Tool mapping
└── voice_handler.py     # Audio streaming
```

### Phase 4: Unified Mobile Experience (Higher Effort)
1. Fork PocketPal or contribute CIRIS integration upstream
2. Deep integration with CIRIS memory and identity
3. Shared model management
4. Target: 4-6 weeks development

---

## 8. Technical Compatibility Matrix

| Feature | Leon | PocketPal | CIRIS | Integration Notes |
|---------|------|-----------|-------|-------------------|
| **Language** | Node.js/Python | TypeScript/RN | Python | API bridge needed |
| **LLM** | External APIs | llama.cpp local | OpenAI/Anthropic | PocketPal could provide local fallback |
| **Memory** | Local files | AsyncStorage | Graph DB | Sync complexity |
| **Voice** | TTS/STT | N/A | N/A | Leon provides this |
| **Platforms** | Desktop | iOS/Android | Server | Complementary |
| **Offline** | Optional | Yes | No | Mobile offline via PocketPal |
| **License** | MIT | MIT | MIT | Compatible |

---

## 9. Risk Assessment

### Low Risk
- Leon skill calling CIRIS API (simple HTTP)
- PocketPal Pal configuration (JSON config)

### Medium Risk
- Leon TCP adapter (protocol complexity)
- Offline/online state sync (data consistency)
- Voice latency (user experience)

### High Risk
- Deep PocketPal fork (maintenance burden)
- Local LLM as CIRIS backend (resource constraints)
- Real-time voice conversation (latency requirements)

---

## 10. Conclusion

### Recommendation

**Start with Phase 1 (Leon Skill) and Phase 2 (PocketPal Pal)** for immediate value with minimal risk. These provide:

1. **Voice interface** through Leon without building TTS/STT
2. **Mobile access** through PocketPal with offline fallback
3. **Expanded reach** to desktop (Leon) and mobile (PocketPal) platforms
4. **Low maintenance** as simple API clients

**Defer Phase 3-4** until Phase 1-2 prove valuable and user demand justifies deeper integration.

### Key Takeaways

| Integration | Value | Effort | Recommendation |
|-------------|-------|--------|----------------|
| Leon Skill | High | Low | **Do first** |
| PocketPal Pal | Medium | Low | **Do second** |
| Leon Adapter | Medium | Medium | Defer |
| PocketPal Fork | Low | High | Avoid |

Both Leon and PocketPal align well with CIRIS's architecture and could significantly extend its capabilities without major core changes. The adapter pattern in CIRIS is specifically designed for this kind of integration.

---

## Appendix A: Code Examples

### Leon Skill Package Structure
```
skills/ciris/
├── __init__.py
├── manifest.json
├── config/
│   └── config.json
├── actions/
│   ├── query.py
│   ├── remember.py
│   └── tools.py
└── README.md
```

### PocketPal Pal Configuration
```json
{
  "id": "ciris-agent",
  "name": "CIRIS",
  "avatar": "ciris_avatar.png",
  "systemPrompt": "You are CIRIS, an ethical AI assistant...",
  "apiConfig": {
    "baseUrl": "https://agents.ciris.ai/api/{agent_id}/v1",
    "authType": "bearer"
  },
  "fallbackModel": {
    "name": "qwen2.5-1.5b-instruct",
    "quantization": "Q4_K_M"
  }
}
```

---

## Appendix B: References

- [Leon AI GitHub](https://github.com/leon-ai/leon)
- [Leon Documentation](https://docs.getleon.ai/)
- [PocketPal AI GitHub](https://github.com/a-ghorbani/pocketpal-ai)
- [llama.rn (React Native llama.cpp)](https://github.com/a-ghorbani/llama.rn)
- [CIRIS Adapter Protocol](../ciris_engine/protocols/adapters/base.py)
- [CIRIS Tool Schema](../ciris_engine/schemas/adapters/tools.py)
