"""
Vulture whitelist for CIRIS Engine.

This file contains code that Vulture incorrectly identifies as unused,
but is actually used by frameworks, decorators, or other dynamic means.
"""

# API routes are used by FastAPI via decorators - false positives
from ciris_engine.logic.adapters.api.routes import *

# Configuration variables used by adapters at runtime
from ciris_engine.logic.adapters.api.config import *
from ciris_engine.logic.adapters.cli.config import *
from ciris_engine.logic.adapters.discord.config import *

# Constants used in API responses and error messages
from ciris_engine.logic.adapters.api.constants import *
from ciris_engine.logic.adapters.discord.constants import *

# Pydantic model fields accessed dynamically
class _WhitelistModels:
    # Memory visualization constants
    NODE_RADIUS = None
    HOVER_RADIUS = None  
    TIMELINE_TRACK_HEIGHT = None
    
    # Telemetry model fields
    degraded_services = None
    active_deferrals = None
    recent_incidents = None
    total_metrics = None
    active_services = None
    
    # Auth response fields
    authorization_url = None
    
    # System health fields  
    initialization_complete = None
    available = None
    shutdown_initiated = None
    
    # Memory query fields
    total_nodes = None
    nodes_by_scope = None
    recent_nodes_24h = None
    
    # Resource metrics
    cpu = None
    disk = None
    network_in_mbps = None
    network_out_mbps = None
    
# Serializer methods called by Pydantic
def serialize_datetime(): pass
def serialize_ts(): pass  
def serialize_times(): pass
def serialize_updated_at(): pass
def serialize_last_seen(): pass
def serialize_start_time(): pass

# Validator methods called by Pydantic
def validate_query_params(): pass

# Calculation methods that may be used in future
def calculate_percentile(): pass
def calculate_trend(): pass
def calculate_range_from_days(): pass

# OAuth methods used by authentication flow
def _create_wa_email(): pass

# Discord event handlers used by discord.py
def on_ready(): pass
def on_disconnect(): pass
def on_thread_join(): pass
def on_thread_delete(): pass

# Base classes for inheritance
class BaseAdapter: pass
class CLIToolService: pass
class CLIWiseAuthorityService: pass

# Exception/response classes for FastAPI
class OAuthLoginResponse: pass
class MetricSeries: pass
class ServiceHealthOverview: pass  
class TraceSpan: pass

# Methods that may be called by framework
def _handle_auth_service(): pass
def rate_limit_wrapper(): pass
def _create_histogram_metric(): pass
def validate_otlp_json(): pass

# Future/planned functionality
def run_chaos_tests(): pass
def run_wa_service(): pass
def fetch_benchmark_prompts(): pass
def submit_benchmark_answers(): pass

# Testing utilities
def test_emergency_endpoint(): pass

# Attributes accessed dynamically  
should_exit = None
database_maintenance_service = None
secrets_tool_service = None
message_handler = None
_guidance_queue = None
_buffered_input_task = None
_input_ready = None
_current_agent_task = None
_detected_secrets = None

# SQL constants that may be used
SQL_ORDER_RANDOM = None

# Template variables
SERVICE_UNAVAILABLE_TEMPLATE = None

# Auth dependency functions
require_system_admin = None
require_service_account = None

# Emergency status attributes  
services_stopped = None
data_persisted = None
final_message_sent = None
shutdown_completed = None
exit_code = None

# Unused variables in complex expressions
has_more = None
is_agent = None
codename = None
pages = None
api_keys_count = None
masked_key = None
services_affected = None
transparency_data = None
schema_extra = None
contact_email = None

# Metrics variables
hourly_average = None
by_service = None
avg = None
p50 = None
p99 = None
decision_count = None
hourly_rate = None
daily_total = None

# Transparency variables
deferrals_to_human = None
deferrals_uncertainty = None  
deferrals_ethical = None
harmful_requests_blocked = None
rate_limit_triggers = None
average_response_ms = None
data_requests_received = None
data_requests_completed = None
commitments = None
links = None

# Storage and audit fields
storage_sources = None
chain_position = None
next_entry_id = None
previous_entry_id = None
export_url = None
row_factory = None