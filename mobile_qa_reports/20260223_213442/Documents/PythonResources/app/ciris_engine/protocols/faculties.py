"""Epistemic Faculty Protocol for Conscience Integration."""

from abc import abstractmethod
from typing import List, Optional, Protocol

from ciris_engine.schemas.dma.faculty import FacultyContext, FacultyResult


class EpistemicFaculty(Protocol):
    """Protocol for epistemic faculties used in conscience bounce mechanism."""

    @abstractmethod
    async def analyze(self, content: str, context: Optional[FacultyContext] = None) -> FacultyResult:
        """
        Analyze content and return epistemic insights.

        Args:
            content: The content to analyze
            context: Optional typed context for deeper analysis

        Returns:
            FacultyResult containing faculty-specific analysis results
        """
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Get the name of this faculty."""
        ...

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Get the capabilities of this faculty."""
        ...
