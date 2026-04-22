"""
Default DSAR ticket SOPs - present in ALL agent templates for GDPR compliance.

These SOPs are automatically added to every agent's ticket configuration.
"""

from ciris_engine.schemas.config.tickets import TicketSOPConfig, TicketStageConfig

# Stage descriptions used across multiple DSAR SOPs
STAGE_DESC_IDENTITY_RESOLUTION = "Resolve user identity across all data sources"

# GDPR Article 15 - Right of Access
DSAR_ACCESS_SOP = TicketSOPConfig(
    sop="DSAR_ACCESS",
    ticket_type="dsar",
    required_fields=["email", "user_identifier"],
    deadline_days=30,  # GDPR 30-day compliance requirement
    priority_default=8,
    description="GDPR Article 15 - Data Subject Access Request for user data export",
    stages=[
        TicketStageConfig(
            name="identity_resolution",
            tools=["identity_resolution_tool"],
            description=STAGE_DESC_IDENTITY_RESOLUTION,
        ),
        TicketStageConfig(
            name="ciris_data_collection",
            tools=["dsar_automation_access"],
            optional=True,  # User may not exist in CIRIS
            description="Collect user data from CIRIS internal storage",
        ),
        TicketStageConfig(
            name="external_data_collection",
            tools=["sql_find_user_data", "sql_export_user"],
            parallel=True,
            optional=True,  # May not have external data sources
            description="Collect user data from external SQL databases",
        ),
        TicketStageConfig(
            name="data_packaging",
            tools=["package_dsar_response"],
            description="Package all collected data for user delivery",
        ),
        TicketStageConfig(
            name="delivery",
            tools=["send_email"],
            description="Deliver DSAR package to user email",
        ),
    ],
)

# GDPR Article 17 - Right to Erasure
DSAR_DELETE_SOP = TicketSOPConfig(
    sop="DSAR_DELETE",
    ticket_type="dsar",
    required_fields=["email", "user_identifier"],
    deadline_days=30,  # GDPR 30-day compliance requirement
    priority_default=9,  # Higher priority - data deletion
    description="GDPR Article 17 - Right to Erasure (Right to be Forgotten)",
    stages=[
        TicketStageConfig(
            name="identity_resolution",
            tools=["identity_resolution_tool"],
            description=STAGE_DESC_IDENTITY_RESOLUTION,
        ),
        TicketStageConfig(
            name="deletion_verification",
            tools=["verify_deletion_eligibility"],
            description="Verify user can be deleted (no legal holds, etc.)",
        ),
        TicketStageConfig(
            name="ciris_data_deletion",
            tools=["dsar_automation_delete"],
            optional=True,
            description="Delete user data from CIRIS internal storage",
        ),
        TicketStageConfig(
            name="external_data_deletion",
            tools=["sql_delete_user"],
            parallel=True,
            optional=True,
            description="Delete user data from external SQL databases",
        ),
        TicketStageConfig(
            name="deletion_confirmation",
            tools=["send_email"],
            description="Send deletion confirmation to user",
        ),
    ],
)

# GDPR Article 20 - Right to Data Portability
DSAR_EXPORT_SOP = TicketSOPConfig(
    sop="DSAR_EXPORT",
    ticket_type="dsar",
    required_fields=["email", "user_identifier"],
    deadline_days=30,
    priority_default=7,
    description="GDPR Article 20 - Right to Data Portability (machine-readable export)",
    stages=[
        TicketStageConfig(
            name="identity_resolution",
            tools=["identity_resolution_tool"],
            description=STAGE_DESC_IDENTITY_RESOLUTION,
        ),
        TicketStageConfig(
            name="ciris_data_export",
            tools=["dsar_automation_export"],
            optional=True,
            description="Export user data from CIRIS in machine-readable format",
        ),
        TicketStageConfig(
            name="external_data_export",
            tools=["sql_export_user"],
            parallel=True,
            optional=True,
            description="Export user data from external SQL databases",
        ),
        TicketStageConfig(
            name="format_conversion",
            tools=["convert_to_portable_format"],
            description="Convert all data to portable format (JSON/CSV)",
        ),
        TicketStageConfig(
            name="delivery",
            tools=["send_email"],
            description="Deliver portable data package to user",
        ),
    ],
)

# GDPR Article 16 - Right to Rectification
DSAR_RECTIFY_SOP = TicketSOPConfig(
    sop="DSAR_RECTIFY",
    ticket_type="dsar",
    required_fields=["email", "user_identifier", "correction_details"],
    deadline_days=30,
    priority_default=7,
    description="GDPR Article 16 - Right to Rectification (correct inaccurate data)",
    stages=[
        TicketStageConfig(
            name="identity_resolution",
            tools=["identity_resolution_tool"],
            description=STAGE_DESC_IDENTITY_RESOLUTION,
        ),
        TicketStageConfig(
            name="data_verification",
            tools=["verify_current_data"],
            description="Retrieve current user data for verification",
        ),
        TicketStageConfig(
            name="ciris_data_correction",
            tools=["update_user_data"],
            optional=True,
            description="Apply corrections to CIRIS internal storage",
        ),
        TicketStageConfig(
            name="external_data_correction",
            tools=["sql_update_user"],
            parallel=True,
            optional=True,
            description="Apply corrections to external SQL databases",
        ),
        TicketStageConfig(
            name="correction_confirmation",
            tools=["send_email"],
            description="Send correction confirmation to user",
        ),
    ],
)

# Default DSAR SOPs that ALL agents get
DEFAULT_DSAR_SOPS = [
    DSAR_ACCESS_SOP,
    DSAR_DELETE_SOP,
    DSAR_EXPORT_SOP,
    DSAR_RECTIFY_SOP,
]
