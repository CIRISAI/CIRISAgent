"""Central constants for CIRIS."""
from pathlib import Path

# Agent defaults
DEFAULT_WA = "CIRIS"
DEFAULT_TEMPLATE = "default"
DEFAULT_TEMPLATE_PATH = Path("ciris_templates")

# Model defaults  
DEFAULT_OPENAI_MODEL_NAME = "gpt-4o-mini"

# Prompt defaults
DEFAULT_PROMPT_TEMPLATE = "default_prompt"

# System defaults
DEFAULT_NUM_ROUNDS = 10

# API defaults
# Security Note: 127.0.0.1 binds to localhost only (recommended for security)
# Use 0.0.0.0 to bind to all interfaces (only for trusted networks/production deployments)
# Configure via CIRIS_API_HOST environment variable
DEFAULT_API_HOST = "127.0.0.1"  # Secure default - localhost only
DEFAULT_API_PORT = 8080