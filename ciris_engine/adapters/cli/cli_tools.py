import os
import asyncio
import uuid
from typing import Dict, Any, List, Optional

from ciris_engine.protocols.services import ToolService

class CLIToolService(ToolService):
    """Simple ToolService providing local filesystem browsing."""

    def __init__(self):
        self._results: Dict[str, Dict[str, Any]] = {}
        self._tools = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "shell_command": self._shell_command,
            "search_text": self._search_text,
        }

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        correlation_id = parameters.get("correlation_id", str(uuid.uuid4()))

        if tool_name not in self._tools:
            result = {"error": f"Unknown tool: {tool_name}"}
        else:
            try:
                result = await self._tools[tool_name](parameters)
            except Exception as e:
                result = {"error": str(e)}

        if correlation_id:
            self._results[correlation_id] = result
        return result

    async def _list_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = params.get("path", ".")
        try:
            files = sorted(os.listdir(path))
            return {"files": files, "path": path}
        except Exception as e:
            return {"error": str(e)}

    async def _read_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read file contents"""
        path = params.get("path")
        if not path:
            return {"error": "path parameter required"}
        try:
            with open(path, "r") as f:
                return {"content": f.read(), "path": path}
        except Exception as e:
            return {"error": str(e)}

    async def _write_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        path = params.get("path")
        content = params.get("content", "")
        if not path:
            return {"error": "path parameter required"}
        try:
            await asyncio.to_thread(self._write_file_sync, path, content)
            return {"status": "written", "path": path}
        except Exception as e:
            return {"error": str(e)}

    def _write_file_sync(self, path: str, content: str) -> None:
        with open(path, "w") as f:
            f.write(content)

    async def _shell_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        cmd = params.get("command")
        if not cmd:
            return {"error": "command parameter required"}
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return {
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "returncode": proc.returncode,
        }

    async def _search_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        pattern = params.get("pattern")
        path = params.get("path")
        if not pattern or not path:
            return {"error": "pattern and path required"}
        matches = []
        try:
            lines = await asyncio.to_thread(self._read_lines_sync, path)
            for idx, line in enumerate(lines, 1):
                if pattern in line:
                    matches.append({"line": idx, "text": line.strip()})
            return {"matches": matches}
        except Exception as e:
            return {"error": str(e)}

    def _read_lines_sync(self, path: str) -> List[str]:
        with open(path, "r") as f:
            return f.readlines()

    async def get_available_tools(self) -> List[str]:
        return list(self._tools.keys())

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        for _ in range(int(timeout * 10)):
            if correlation_id in self._results:
                return self._results.pop(correlation_id)
            await asyncio.sleep(0.1)
        return None

    async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        return tool_name in self._tools
