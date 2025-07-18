"""Persistence package providing database and model utilities."""

from .db import (
    get_db_connection,
    initialize_database,
    get_graph_nodes_table_schema_sql,
    get_graph_edges_table_schema_sql,
    get_service_correlations_table_schema_sql,
    run_migrations,
    MIGRATIONS_DIR,
    get_sqlite_db_full_path,
)
from .models import (
    update_task_status,
    task_exists,
    add_task,
    get_all_tasks,
    get_task_by_id,
    get_tasks_by_status,
    get_recent_completed_tasks,
    get_top_tasks,
    get_pending_tasks_for_activation,
    count_tasks,
    delete_tasks_by_ids,
    get_tasks_older_than,
    add_thought,
    get_thought_by_id,
    async_get_thought_by_id,
    get_thoughts_by_ids,
    async_get_thoughts_by_ids,
    async_get_thought_status,
    update_thought_status,
    get_thoughts_by_status,
    get_thoughts_older_than,
    get_thoughts_by_task_id,
    count_thoughts,
    delete_thoughts_by_ids,
    save_deferral_report_mapping,
    get_deferral_report_context,
    add_graph_node,
    get_graph_node,
    delete_graph_node,
    add_graph_edge,
    delete_graph_edge,
    get_edges_for_node,
    get_all_graph_nodes,
    get_nodes_by_type,
    add_correlation,
    update_correlation,
    get_correlation,
    get_correlations_by_task_and_action,
    get_correlations_by_channel,
    get_queue_status,
    QueueStatus,
)
from .analytics import (
    get_pending_thoughts_for_active_tasks,
    count_pending_thoughts_for_active_tasks,
    count_active_tasks,
    get_tasks_needing_seed_thought,
    pending_thoughts,
    thought_exists_for,
    count_thoughts_by_status,
)

__all__ = [
    "get_db_connection",
    "initialize_database",
    "get_tasks_older_than",
    "get_thoughts_older_than",
    "run_migrations",
    "MIGRATIONS_DIR",
    "get_sqlite_db_full_path",
    "update_task_status",
    "task_exists",
    "add_task",
    "get_all_tasks",
    "get_task_by_id",
    "get_tasks_by_status",
    "get_recent_completed_tasks",
    "get_top_tasks",
    "get_pending_tasks_for_activation",
    "count_tasks",
    "delete_tasks_by_ids",
    "add_thought",
    "get_thought_by_id",
    "async_get_thought_by_id",
    "get_thoughts_by_ids",
    "async_get_thoughts_by_ids",
    "async_get_thought_status",
    "update_thought_status",
    "get_thoughts_by_status",
    "get_thoughts_by_task_id",
    "count_thoughts",
    "delete_thoughts_by_ids",
    "save_deferral_report_mapping",
    "get_deferral_report_context",
    "add_graph_node",
    "get_graph_node",
    "delete_graph_node",
    "add_graph_edge",
    "delete_graph_edge",
    "get_edges_for_node",
    "get_all_graph_nodes",
    "get_nodes_by_type",
    "add_correlation",
    "update_correlation",
    "get_correlation",
    "get_correlations_by_task_and_action",
    "get_correlations_by_channel",
    "get_pending_thoughts_for_active_tasks",
    "count_pending_thoughts_for_active_tasks",
    "count_active_tasks",
    "get_tasks_needing_seed_thought",
    "pending_thoughts",
    "thought_exists_for",
    "count_thoughts_by_status",
    "get_graph_nodes_table_schema_sql",
    "get_graph_edges_table_schema_sql",
    "get_service_correlations_table_schema_sql",
    "get_queue_status",
    "QueueStatus",
]
