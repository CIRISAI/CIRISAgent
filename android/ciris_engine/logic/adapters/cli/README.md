# CLI Adapters

This package provides CLI-based services for the agent. It includes a simple
communication adapter, observation utilities and a minimal `ToolService`
implementation for browsing the local filesystem. These services are registered
with `Priority.NORMAL` by `CLIRuntime` and are used as fallbacks by the
`DiscordRuntime` when Discord is unavailable.
