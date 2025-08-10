"""
Typed crisis resource management for CIRIS agents.

This module provides structured, validated crisis resources to ensure:
1. All crisis resources are actively maintained and validated
2. Resources are consistent across all templates
3. Legal disclaimers are properly included
4. Resources can be tested programmatically
5. Updates propagate to all agents automatically
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set

from pydantic import BaseModel, Field, HttpUrl, field_validator


class CrisisResourceType(str, Enum):
    """Types of crisis resources available."""

    HOTLINE = "hotline"
    WEBSITE = "website"
    TEXT_LINE = "text_line"
    EMERGENCY = "emergency"
    DIRECTORY = "directory"
    SEARCH_TERM = "search_term"


class ResourceAvailability(str, Enum):
    """Geographic availability of resources."""

    GLOBAL = "global"
    US = "us"
    UK = "uk"
    EU = "eu"
    CANADA = "ca"
    AUSTRALIA = "au"
    REGIONAL = "regional"


class CrisisResource(BaseModel):
    """A validated crisis resource with metadata."""

    id: str = Field(..., description="Unique identifier for the resource")
    name: str = Field(..., description="Human-readable name")
    type: CrisisResourceType = Field(..., description="Type of resource")

    # Contact information (at least one required)
    url: Optional[HttpUrl] = Field(None, description="Website URL")
    phone: Optional[str] = Field(None, description="Phone number")
    text_number: Optional[str] = Field(None, description="SMS/text number")
    search_term: Optional[str] = Field(None, description="Search term for finding local resources")

    # Metadata
    description: str = Field(..., description="Brief description of the service")
    availability: List[ResourceAvailability] = Field(
        default_factory=lambda: [ResourceAvailability.GLOBAL], description="Geographic availability"
    )
    languages: List[str] = Field(default_factory=lambda: ["en"], description="Supported languages (ISO 639-1 codes)")

    # Validation metadata
    last_validated: datetime = Field(
        default_factory=datetime.now, description="When this resource was last validated as working"
    )
    validation_notes: Optional[str] = Field(None, description="Notes from last validation")

    # Legal/compliance
    is_endorsed: bool = Field(False, description="Whether CIRIS endorses this resource (always False for liability)")
    requires_disclaimer: bool = Field(True, description="Whether to show disclaimer when sharing")

    @field_validator("phone", "text_number")
    @classmethod
    def validate_phone_format(cls, v: Optional[str]) -> Optional[str]:
        """Basic phone number validation."""
        if v is None:
            return v
        # Remove common formatting characters
        cleaned = v.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        # Ensure it's numeric (except for + prefix)
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        if not cleaned.isdigit():
            raise ValueError(f"Invalid phone number format: {v}")
        return v

    @field_validator("search_term")
    @classmethod
    def validate_search_term(cls, v: Optional[str]) -> Optional[str]:
        """Ensure search terms are safe and useful."""
        if v is None:
            return v
        # Should contain 'crisis' or 'hotline' or 'emergency'
        keywords = ["crisis", "hotline", "emergency", "help", "support"]
        if not any(keyword in v.lower() for keyword in keywords):
            raise ValueError(f"Search term should contain crisis-related keywords: {v}")
        return v

    def model_post_init(self, __context):
        """Ensure at least one contact method is provided."""
        if not any([self.url, self.phone, self.text_number, self.search_term]):
            raise ValueError("At least one contact method must be provided")

    def format_for_display(self, include_disclaimer: bool = True) -> str:
        """Format resource for display in messages."""
        lines = [f"**{self.name}**"]

        if self.url:
            lines.append(f"• Website: {self.url}")
        if self.phone:
            lines.append(f"• Phone: {self.phone}")
        if self.text_number:
            lines.append(f"• Text: {self.text_number}")
        if self.search_term:
            lines.append(f"• Search: '{self.search_term}'")

        lines.append(f"• {self.description}")

        if include_disclaimer and self.requires_disclaimer:
            lines.append("• (Not an endorsement - information only)")

        return "\n".join(lines)


class CrisisResourceRegistry(BaseModel):
    """Registry of all crisis resources available to CIRIS agents."""

    resources: Dict[str, CrisisResource] = Field(
        default_factory=dict, description="All registered crisis resources by ID"
    )

    # Legal disclaimer that MUST be included
    disclaimer: str = Field(
        default="""DISCLAIMER: I am an AI moderator, not a healthcare provider. The following
is general information only, not medical advice or crisis intervention:

This information is provided as-is without warranty. CIRIS L3C is not a
healthcare provider and does not endorse these resources. Please seek
qualified professional help.""",
        description="Required disclaimer text",
    )

    def add_resource(self, resource: CrisisResource) -> None:
        """Add a resource to the registry."""
        if resource.id in self.resources:
            raise ValueError(f"Resource with ID {resource.id} already exists")
        self.resources[resource.id] = resource

    def get_by_availability(self, regions: List[ResourceAvailability]) -> List[CrisisResource]:
        """Get resources available in specified regions."""
        results = []
        for resource in self.resources.values():
            if ResourceAvailability.GLOBAL in resource.availability:
                results.append(resource)
            elif any(region in resource.availability for region in regions):
                results.append(resource)
        return results

    def get_by_type(self, resource_type: CrisisResourceType) -> List[CrisisResource]:
        """Get all resources of a specific type."""
        return [r for r in self.resources.values() if r.type == resource_type]

    def format_crisis_response(
        self, resource_ids: Optional[List[str]] = None, regions: Optional[List[ResourceAvailability]] = None
    ) -> str:
        """Format a complete crisis response with disclaimer."""
        lines = [
            "The information shared suggests professional support may be helpful.",
            "",
            self.disclaimer,
            "",
            "**General Crisis Resources (not endorsements):**",
        ]

        # Get resources to display
        if resource_ids:
            resources = [self.resources[rid] for rid in resource_ids if rid in self.resources]
        elif regions:
            resources = self.get_by_availability(regions)
        else:
            # Default to global resources
            resources = self.get_by_availability([ResourceAvailability.GLOBAL])

        # Add formatted resources
        for resource in resources:
            lines.append("")
            lines.append(resource.format_for_display(include_disclaimer=False))

        lines.extend(
            ["", "For immediate danger: Contact 911 or local emergency services", "", "[DEFER TO HUMAN MODERATOR]"]
        )

        return "\n".join(lines)

    def validate_all_resources(self) -> Dict[str, bool]:
        """Validate all resources are properly formed."""
        results = {}
        for resource_id, resource in self.resources.items():
            try:
                # Re-validate the model
                resource.model_validate(resource.model_dump())
                results[resource_id] = True
            except Exception as e:
                results[resource_id] = False
        return results


# Default crisis resources that MUST be available
DEFAULT_CRISIS_RESOURCES = CrisisResourceRegistry(
    resources={
        "findahelpline": CrisisResource(
            id="findahelpline",
            name="Find a Helpline",
            type=CrisisResourceType.DIRECTORY,
            url="https://findahelpline.com",
            description="International directory of crisis helplines",
            availability=[ResourceAvailability.GLOBAL],
            languages=["en", "es", "fr", "de", "it", "pt", "ru", "zh", "ja", "ko"],
            last_validated=datetime.now(),
            is_endorsed=False,
            requires_disclaimer=True,
        ),
        "iasp": CrisisResource(
            id="iasp",
            name="IASP Crisis Centers",
            type=CrisisResourceType.DIRECTORY,
            url="https://iasp.info/resources/Crisis_Centres",
            description="International Association for Suicide Prevention resource directory",
            availability=[ResourceAvailability.GLOBAL],
            languages=["en"],
            last_validated=datetime.now(),
            is_endorsed=False,
            requires_disclaimer=True,
        ),
        "crisis_text_line": CrisisResource(
            id="crisis_text_line",
            name="Crisis Text Line",
            type=CrisisResourceType.TEXT_LINE,
            text_number="741741",
            url="https://www.crisistextline.org",
            description="24/7 text-based crisis support (US, UK, Canada)",
            availability=[ResourceAvailability.US, ResourceAvailability.UK, ResourceAvailability.CANADA],
            languages=["en"],
            last_validated=datetime.now(),
            is_endorsed=False,
            requires_disclaimer=True,
        ),
        "988_lifeline": CrisisResource(
            id="988_lifeline",
            name="988 Suicide & Crisis Lifeline",
            type=CrisisResourceType.HOTLINE,
            phone="988",
            url="https://988lifeline.org",
            description="24/7 suicide prevention and crisis support (US)",
            availability=[ResourceAvailability.US],
            languages=["en", "es"],
            last_validated=datetime.now(),
            is_endorsed=False,
            requires_disclaimer=True,
        ),
        "samaritans": CrisisResource(
            id="samaritans",
            name="Samaritans",
            type=CrisisResourceType.HOTLINE,
            phone="116 123",
            url="https://www.samaritans.org",
            description="24/7 emotional support (UK and Ireland)",
            availability=[ResourceAvailability.UK],
            languages=["en"],
            last_validated=datetime.now(),
            is_endorsed=False,
            requires_disclaimer=True,
        ),
        "local_search": CrisisResource(
            id="local_search",
            name="Local Crisis Services",
            type=CrisisResourceType.SEARCH_TERM,
            search_term="crisis hotline [your location]",
            description="Search for crisis services in your area",
            availability=[ResourceAvailability.GLOBAL],
            languages=["en"],
            last_validated=datetime.now(),
            is_endorsed=False,
            requires_disclaimer=True,
        ),
        "emergency_services": CrisisResource(
            id="emergency_services",
            name="Emergency Services",
            type=CrisisResourceType.EMERGENCY,
            phone="911",
            description="For immediate danger or medical emergency",
            availability=[ResourceAvailability.US, ResourceAvailability.CANADA],
            languages=["en"],
            last_validated=datetime.now(),
            is_endorsed=False,
            requires_disclaimer=True,
        ),
    }
)


def get_crisis_response_text(
    regions: Optional[List[ResourceAvailability]] = None, resource_ids: Optional[List[str]] = None
) -> str:
    """
    Get formatted crisis response text with appropriate resources.

    Args:
        regions: Geographic regions to filter resources by
        resource_ids: Specific resource IDs to include

    Returns:
        Formatted crisis response text with disclaimer
    """
    return DEFAULT_CRISIS_RESOURCES.format_crisis_response(resource_ids=resource_ids, regions=regions)
