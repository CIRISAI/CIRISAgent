# Contributing to CIRIS Agent

> **🏠 Looking to build multi-modal AI capabilities?** 
> 
> **Consider contributing to [CIRISHome](https://github.com/CIRISAI/CIRISHome)** - our active development platform for vision, audio, and sensor fusion capabilities that enable medical AI for underserved communities. CIRISHome welcomes multi-modal AI development using Home Assistant as a foundation, with the ultimate goal of life-saving healthcare access for those who need it most.
>
> **CIRISAgent** (this repository) focuses on core AI agent functionality with a complete H3ERE architecture, while **CIRISHome** is where multi-modal capabilities are developed and tested.

---

Thank you for your interest in contributing to CIRIS Agent! This document outlines how to contribute effectively to the project.

## 🏗️ **Engine Status: H3ERE Architecture Complete**

The CIRIS Agent's core **H3ERE (Hyper3 Ethical Recursive Engine)** is architecturally complete and production-ready:

- **4 DMAs**: 3 core decision-making algorithms (PDMA, CSDMA, DSDMA) + 1 recursive (ASPDMA)
- **10 Handlers**: Exactly 10 action handlers in 3×3×3+1 structure
- **6 Message Buses**: Complete communication infrastructure
- **22 Core Services**: All essential services implemented and documented
- **Complete Type Safety**: Zero `Dict[str, Any]` in production code

## 🎯 **How to Contribute**

Since the core engine is complete, contributions should focus on:

### **1. New Adapters** ⭐ *Most Valuable*
Create new interfaces for CIRIS to interact with different platforms:
- **Social Media**: Twitter, LinkedIn, Mastodon adapters  
- **Messaging**: Slack, Teams, Telegram adapters
- **Development**: GitHub, GitLab integration adapters
- **Documentation**: Confluence, Notion adapters

### **2. Bug Fixes & Improvements** 🔧
- Fix issues in existing functionality
- Performance optimizations
- Memory leak resolution
- Test coverage improvements

### **3. New Modular Services** 🧩
Extend CIRIS capabilities with new modular services:
- Advanced analytics services
- External API integrations
- Specialized tool services

## 📋 **Adapter Development Guide**

### **Creating a New Adapter**

1. **Follow the established pattern** from existing adapters (`ciris_engine/logic/adapters/`):
   ```
   adapters/your_adapter/
   ├── README.md                    # Comprehensive documentation
   ├── __init__.py                  # Public exports
   ├── adapter.py                   # Main adapter class
   ├── services/                    # Adapter-specific services
   │   ├── communication_service.py # Required: Communication
   │   ├── tool_service.py         # Optional: Tools  
   │   └── runtime_control.py      # Optional: Control
   └── schemas/                     # Adapter-specific schemas
   ```

2. **Implement required interfaces**:
   ```python
   from ciris_engine.protocols.adapters import BaseAdapter
   
   class YourAdapter(BaseAdapter):
       async def initialize(self) -> None:
           """Initialize your adapter"""
           pass
           
       async def cleanup(self) -> None:
           """Clean shutdown"""
           pass
   ```

3. **Create adapter-specific services** that integrate with CIRIS buses
4. **Write comprehensive tests** following existing test patterns
5. **Document everything** with detailed README files

## 🧩 **Modular Service Development**

For new modular services, follow the **Mock LLM pattern** in `ciris_modular_services/mock_llm/`:

### **Required Files:**
```
your_service/
├── manifest.json          # Service declaration
├── README.md             # Documentation
├── __init__.py           # Module exports
├── service.py            # Main service class
├── protocol.py           # Service protocol
└── schemas.py            # Service-specific schemas
```

### **Manifest Structure:**
```json
{
  "module": {
    "name": "your_service",
    "version": "1.0.0", 
    "description": "Your service description",
    "author": "Your Name"
  },
  "services": [{
    "type": "YOUR_SERVICE_TYPE",
    "priority": "NORMAL",
    "class": "your_service.service.YourServiceClass",
    "capabilities": ["your_capability"]
  }],
  "dependencies": {
    "protocols": [
      "ciris_engine.protocols.services.RequiredProtocol"
    ],
    "schemas": [
      "ciris_engine.schemas.required.schemas"  
    ]
  },
  "exports": {
    "service_class": "your_service.service.YourServiceClass",
    "protocol": "your_service.protocol.YourServiceProtocol"
  },
  "configuration": {
    "config_option": {
      "type": "string",
      "default": "default_value",
      "description": "Configuration description"
    }
  }
}
```

## 🏛️ **H3ERE Architecture Overview**

Understanding the architecture helps create better contributions:

### **Decision-Making Flow:**
1. **Input** → Adapter receives external input
2. **Task Creation** → Adapter creates Task with context
3. **DMA Evaluation** → PDMA, CSDMA, DSDMA evaluate
4. **ASPDMA Selection** → Recursive action selection  
5. **Handler Execution** → One of 10 handlers executes
6. **Output** → Response via Communication Bus

### **The 10 H3ERE Handlers:**
- **Action (3)**: SPEAK, TOOL, OBSERVE
- **Memory (3)**: MEMORIZE, RECALL, FORGET  
- **Deferral (3)**: REJECT, PONDER, DEFER
- **Terminal (1)**: TASK_COMPLETE

### **The 6 Message Buses:**
- **CommunicationBus** → Multi-adapter external communication
- **MemoryBus** → Graph storage and retrieval
- **LLMBus** → Multiple LLM provider access
- **ToolBus** → External tool execution
- **RuntimeControlBus** → System control and monitoring
- **WiseBus** → Ethical guidance and wisdom

## 📝 **Development Guidelines**

### **Type Safety First**
- **No Dicts**: Use Pydantic models for all data
- **No Strings**: Use enums and typed constants  
- **No Kings**: No special cases or bypass patterns

### **Task and Thought Creation**
When creating new input sources:

```python
# Store raw input in Task.context
task_context = {
    "origin_service": "your_adapter",
    "initial_input_content": raw_input,
    "adapter_specific_id": message_id,
    # ... other metadata
}
new_task = Task(..., context=task_context)
```

- **Don't create Thoughts manually** - The engine auto-generates seed thoughts
- **Store all external context** in `Task.context` for processing

### **Testing Requirements**
- **Unit tests** for all new functionality
- **Integration tests** for adapter interactions
- **Mock services** for external dependencies
- **Type safety validation** with mypy

### **Documentation Standards**
- **README.md** for every new component
- **Inline documentation** for complex logic
- **API documentation** for new protocols
- **Architecture alignment** with H3ERE principles

## 🔍 **Development Setup**

1. **Fork and Clone**:
   ```bash
   git clone https://github.com/your-username/CIRISAgent.git
   cd CIRISAgent
   ```

2. **Set up Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   pip install -r requirements.txt
   ```

3. **Run Tests**:
   ```bash
   python -m pytest tests/
   ```

4. **Check Type Safety**:
   ```bash
   mypy ciris_engine/
   ```

## 🚀 **Pull Request Process**

1. **Create branch** from latest `main`
2. **Follow naming**: `feature/your-feature` or `fix/issue-description`
3. **Write tests** for all new functionality
4. **Update documentation** as needed
5. **Ensure all tests pass**: `pytest`
6. **Verify type safety**: `mypy`
7. **Write clear commit messages** following conventional commits
8. **Submit PR** with detailed description

### **PR Requirements:**
- [ ] All tests pass
- [ ] Type safety maintained (no new `Dict[str, Any]`)
- [ ] Documentation updated
- [ ] Follows H3ERE architectural principles
- [ ] No breaking changes to core engine

## 🏷️ **Issue Labels**

- **adapter**: New adapter development
- **service**: New modular service
- **bug**: Bug fixes and corrections  
- **improvement**: Performance or code quality improvements
- **documentation**: Documentation updates
- **testing**: Test coverage improvements

## 📚 **Resources**

- **Architecture**: See `ciris_engine/logic/README.md`
- **H3ERE Documentation**: All bus and service README files
- **Example Adapters**: `ciris_engine/logic/adapters/`
- **Example Services**: `ciris_modular_services/mock_llm/`

## ⚖️ **Code of Conduct**

All contributors must follow our commitment to ethical AI development:
- **Beneficence**: Contributions must benefit users and society
- **Non-maleficence**: No harmful or malicious code
- **Transparency**: Clear, well-documented contributions
- **Respect**: Professional and inclusive collaboration

---

**The H3ERE engine is complete. Your contributions extend its reach and capabilities!** 🚀

*Copyright © 2025 Eric Moore and CIRIS L3C - Apache 2.0 License*