#!/usr/bin/env python3
"""
CIRIS Protocol Generator

This tool generates protocol definitions from existing module implementations.
It analyzes public methods and creates corresponding protocol interfaces.
"""
import json
from pathlib import Path
from typing import List


class ProtocolGenerator:
    """Generates protocol definitions from module implementations."""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.ciris_root = self.project_root / "ciris_engine"
        self.protocols_dir = self.ciris_root / "protocols"

        # Load existing data
        try:
            with open("trinity_analysis_results.json", "r") as f:
                self.trinity_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError, IOError):
            self.trinity_data = {"modules": {}, "protocols": {}}

    def generate_all_missing_protocols(self):
        """Generate protocols for all modules without them."""
        print("🔧 Generating Missing Protocols...\n")

        # Find modules without protocols
        modules_with_protocols = set()
        for protocol, alignment in self.trinity_data.get("trinity_alignment", {}).items():
            if alignment.get("module"):
                modules_with_protocols.add(alignment["module"])

        all_modules = set(self.trinity_data.get("modules", {}).keys())
        modules_without_protocols = all_modules - modules_with_protocols

        print(f"📊 Found {len(modules_without_protocols)} modules without protocols")

        # Group by category
        service_modules = []
        handler_modules = []
        adapter_modules = []
        other_modules = []

        for module_name in modules_without_protocols:
            if "Service" in module_name:
                service_modules.append(module_name)
            elif "Handler" in module_name:
                handler_modules.append(module_name)
            elif "Adapter" in module_name:
                adapter_modules.append(module_name)
            else:
                other_modules.append(module_name)

        # Generate protocols by category
        self._generate_service_protocols(service_modules)
        self._generate_handler_protocols(handler_modules)
        self._generate_adapter_protocols(adapter_modules)

    def _generate_service_protocols(self, service_modules: List[str]):
        """Generate service protocol definitions."""
        if not service_modules:
            return

        print(f"\n📋 Generating {len(service_modules)} Service Protocols...")

        # Create services protocol file content
        content = '''"""
CIRIS Service Protocol Definitions

This file contains protocol interfaces for all service implementations.
Services use these protocols to ensure consistent interfaces across the system.
"""
from typing import Protocol, Optional, List, Dict, Any
from ciris_engine.schemas.base_schemas_v1 import ServiceCapabilities
from ciris_engine.schemas.task_thought_schemas_v1 import GraphNode
from ciris_engine.schemas.services_schemas_v1 import MemoryQuery, MemoryOpResult

'''

        # Add existing imports from original protocols
        existing_protocols = [
            "MemoryServiceProtocol",
            "ToolServiceProtocol",
            "AuditServiceProtocol",
            "LLMServiceProtocol",
            "SecretsServiceProtocol",
            "RuntimeControlServiceProtocol",
            "WiseAuthorityServiceProtocol",
        ]

        # Generate new protocols
        for module_name in sorted(service_modules):
            if module_name in ["CommunicationService", "NetworkService", "CommunityService"]:
                # Skip these as they're in protocols already
                continue

            module_info = self.trinity_data["modules"].get(module_name, {})
            if not module_info:
                continue

            # Create protocol name
            if module_name.endswith("Service"):
                protocol_name = module_name.replace("Service", "ServiceProtocol")
            else:
                protocol_name = module_name + "Protocol"

            # Skip if already exists
            if protocol_name in existing_protocols:
                continue

            print(f"  ✓ Generating {protocol_name} from {module_name}")

            # Generate protocol class
            content += f"\n\nclass {protocol_name}(Protocol):\n"
            content += f'    """Protocol for {module_name}."""\n'

            # Add methods
            public_methods = [m for m in module_info.get("methods", []) if not m["name"].startswith("_")]

            if not public_methods:
                content += "    pass  # No public methods\n"
            else:
                for method in public_methods:
                    method_name = method["name"]
                    is_async = method.get("is_async", False)

                    # Generate method signature
                    if is_async:
                        content += f"    async def {method_name}(self"
                    else:
                        content += f"    def {method_name}(self"

                    # Add generic parameters for now
                    if "get" in method_name.lower() or "list" in method_name.lower():
                        content += ") -> Any:\n"
                    elif "create" in method_name.lower() or "add" in method_name.lower():
                        content += ", *args, **kwargs) -> Any:\n"
                    else:
                        content += ", *args, **kwargs) -> Any:\n"

                    content += '        """TODO: Add proper type hints."""\n'
                    content += "        ...\n\n"

        # Save the generated protocols
        new_protocols_file = self.protocols_dir / "generated_services.py"
        with open(new_protocols_file, "w") as f:
            f.write(content)

        print(f"  💾 Saved to {new_protocols_file}")

    def _generate_handler_protocols(self, handler_modules: List[str]):
        """Generate handler protocol definitions."""
        if not handler_modules:
            return

        print(f"\n📋 Generating {len(handler_modules)} Handler Protocols...")

        content = '''"""
CIRIS Handler Protocol Definitions

This file contains protocol interfaces for all handler implementations.
Handlers use these protocols to ensure consistent action processing.
"""
from typing import Protocol, Optional, Any
from ciris_engine.schemas.task_thought_schemas_v1 import Task, Thought, ActionContext

'''

        # Group handlers by type
        handler_groups = {"external": [], "control": [], "memory": [], "terminal": []}

        for handler_name in handler_modules:
            if any(x in handler_name for x in ["Speak", "Tool", "Observe"]):
                handler_groups["external"].append(handler_name)
            elif any(x in handler_name for x in ["Ponder", "Defer", "Reject"]):
                handler_groups["control"].append(handler_name)
            elif any(x in handler_name for x in ["Memorize", "Recall", "Forget"]):
                handler_groups["memory"].append(handler_name)
            elif "TaskComplete" in handler_name:
                handler_groups["terminal"].append(handler_name)

        # Generate base handler protocol
        content += '''
class BaseHandlerProtocol(Protocol):
    """Base protocol for all action handlers."""

    async def handle(self, task: Task, thought: Thought, context: ActionContext) -> Any:
        """Handle an action."""
        ...

    def get_action_type(self) -> str:
        """Get the action type this handler processes."""
        ...

'''

        # Generate specific handler protocols
        for group_name, handlers in handler_groups.items():
            if handlers:
                group_protocol = f"{group_name.title()}ActionHandlerProtocol"
                content += f"\nclass {group_protocol}(BaseHandlerProtocol, Protocol):\n"
                content += f'    """Protocol for {group_name} action handlers."""\n'
                content += "    pass  # Inherits from BaseHandlerProtocol\n\n"

        # Save the generated protocols
        new_protocols_file = self.protocols_dir / "handlers.py"
        with open(new_protocols_file, "w") as f:
            f.write(content)

        print(f"  💾 Saved to {new_protocols_file}")

    def _generate_adapter_protocols(self, adapter_modules: List[str]):
        """Generate adapter protocol definitions."""
        if not adapter_modules:
            return

        print(f"\n📋 Generating {len(adapter_modules)} Adapter Protocols...")

        content = '''"""
CIRIS Adapter Protocol Definitions

This file contains protocol interfaces for platform adapters.
Adapters implement these protocols to provide consistent platform integration.
"""
from typing import Protocol, Optional, Dict, Any, List
from ciris_engine.schemas.protocol_schemas_v1 import AdapterConfig

'''

        # Generate base adapter protocol
        content += '''
class BaseAdapterProtocol(Protocol):
    """Base protocol for all platform adapters."""

    async def start(self) -> None:
        """Start the adapter."""
        ...

    async def stop(self) -> None:
        """Stop the adapter."""
        ...

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        ...

    def get_status(self) -> Dict[str, Any]:
        """Get adapter status."""
        ...

'''

        # Generate specific adapter protocols
        platform_adapters = {"API": [], "CLI": [], "Discord": []}

        for adapter_name in adapter_modules:
            if "API" in adapter_name:
                platform_adapters["API"].append(adapter_name)
            elif "CLI" in adapter_name:
                platform_adapters["CLI"].append(adapter_name)
            elif "Discord" in adapter_name:
                platform_adapters["Discord"].append(adapter_name)

        for platform, adapters in platform_adapters.items():
            if adapters:
                platform_protocol = f"{platform}AdapterProtocol"
                content += f"\nclass {platform_protocol}(BaseAdapterProtocol, Protocol):\n"
                content += f'    """Protocol for {platform} adapters."""\n'

                # Add platform-specific methods based on known patterns
                if platform == "API":
                    content += '''
    async def handle_request(self, request: Any) -> Any:
        """Handle API request."""
        ...

    def get_routes(self) -> List[Any]:
        """Get API routes."""
        ...
'''
                elif platform == "CLI":
                    content += '''
    async def handle_command(self, command: str) -> Any:
        """Handle CLI command."""
        ...

    def get_commands(self) -> Dict[str, Any]:
        """Get available commands."""
        ...
'''
                elif platform == "Discord":
                    content += '''
    async def handle_message(self, message: Any) -> Any:
        """Handle Discord message."""
        ...

    def get_bot_config(self) -> Dict[str, Any]:
        """Get Discord bot configuration."""
        ...
'''
                content += "\n"

        # Save the generated protocols
        new_protocols_file = self.protocols_dir / "adapters.py"
        with open(new_protocols_file, "w") as f:
            f.write(content)

        print(f"  💾 Saved to {new_protocols_file}")

    def generate_summary(self):
        """Generate a summary of what needs to be done."""
        print("\n" + "=" * 60)
        print("📊 Protocol Generation Summary")
        print("=" * 60)

        print("\n🎯 Next Steps:")
        print("\n1. **Review Generated Protocols**")
        print("   - Check ciris_engine/protocols/generated_services.py")
        print("   - Check ciris_engine/protocols/handlers.py")
        print("   - Check ciris_engine/protocols/adapters.py")

        print("\n2. **Add Proper Type Hints**")
        print("   - Replace 'Any' with specific types")
        print("   - Add proper parameter types")
        print("   - Use schemas from schemas directory")

        print("\n3. **Update Module Implementations**")
        print("   - Add protocol inheritance to classes")
        print("   - Ensure methods match protocol signatures")
        print("   - Remove any extra public methods")

        print("\n4. **Run Trinity Validator**")
        print("   - python analyze_trinity.py")
        print("   - Verify alignment improved")
        print("   - Fix any remaining mismatches")


if __name__ == "__main__":
    generator = ProtocolGenerator()
    generator.generate_all_missing_protocols()
    generator.generate_summary()
