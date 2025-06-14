"""
ModerationDSDMA - Domain-Specific Decision Making Algorithm for Discord Moderation

This DSDMA specializes in evaluating thoughts through the lens of community moderation,
focusing on fostering healthy community dynamics while respecting individual dignity.

To register this DSDMA, add to ciris_engine/dma/factory.py:

from .moderation_dsdma import ModerationDSDMA

DSDMA_CLASS_REGISTRY: Dict[str, Type[BaseDSDMA]] = {
    "BaseDSDMA": BaseDSDMA,
    "ModerationDSDMA": ModerationDSDMA,  # Add this line
}
"""
import logging
from typing import Dict, Any, Optional
from ciris_engine.dma.dsdma_base import BaseDSDMA
from ciris_engine.processor.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.dma_results_v1 import DSDMAResult
from ciris_engine.registries.base import ServiceRegistry
from .prompt_loader import get_prompt_loader

logger = logging.getLogger(__name__)


class ModerationDSDMA(BaseDSDMA):
    """
    Domain-Specific DMA for Discord moderation tasks.
    Evaluates thoughts for moderation actions based on community health principles.
    """
    
    DEFAULT_TEMPLATE = """
    You are Echo, a moderation-focused DSDMA evaluator. Your task is to assess thoughts
    through the lens of community moderation, balancing individual dignity with collective wellbeing.
    
    === Moderation Domain Principles ===
    1. **Ubuntu Philosophy**: "I am because we are" - Individual and community wellbeing are inseparable
    2. **Graduated Response**: Start gentle, escalate only when necessary
    3. **Restorative Justice**: Focus on repairing harm and reintegration over punishment
    4. **Context Awareness**: Consider user history, intent, and circumstances
    5. **Transparency**: Be clear about AI nature and decision rationale
    
    === Evaluation Criteria ===
    - **Community Impact**: How does this affect overall community health and trust?
    - **Proportionality**: Is the contemplated response appropriately scaled?
    - **Pattern Recognition**: Does this indicate a larger issue needing attention?
    - **Escalation Necessity**: Does this require human moderator involvement?
    
    === Current Context ===
    Domain: {domain_name}
    Platform Context: {context_str}
    Domain Rules: {rules_summary_str}
    
    {system_snapshot_block}
    {user_profiles_block}
    
    === Evaluation Guidelines ===
    - score: Rate 0.0-1.0 how well the thought aligns with moderation best practices
    - recommended_action: Suggest specific moderation action if needed (e.g., "gentle_reminder", "timeout_10min", "send_deferral")
    - flags: Identify moderation concerns (e.g., ["potential_conflict", "new_user", "requires_context"])  
    - reasoning: Explain your assessment focusing on community impact and proportional response
    """
    
    def __init__(self,
                 domain_name: str = "discord_moderation",
                 service_registry: ServiceRegistry = None,
                 model_name: Optional[str] = None,
                 domain_specific_knowledge: Optional[Dict[str, Any]] = None,
                 prompt_template: Optional[str] = None,
                 sink: Optional[Any] = None) -> None:
        """
        Initialize ModerationDSDMA with moderation-specific defaults.
        """
        # Set default moderation knowledge if not provided
        if domain_specific_knowledge is None:
            domain_specific_knowledge = {
                "rules_summary": (
                    "Foster community flourishing through ethical moderation. "
                    "Prioritize education over enforcement. Apply graduated responses. "
                    "Respect individual dignity while maintaining community standards. "
                    "Defer complex interpersonal conflicts to human moderators."
                ),
                "moderation_tools": [
                    "discord_delete_message",
                    "discord_timeout_user",
                    "discord_slowmode",
                    "discord_ban_user",
                    "discord_kick_user"
                ],
                "escalation_triggers": [
                    "threats of self-harm or violence",
                    "complex interpersonal conflicts",
                    "potential legal issues",
                    "serious ToS violations",
                    "decisions significantly impacting participation"
                ],
                "response_ladder": {
                    "level_1": "gentle reminder or clarification",
                    "level_2": "formal warning with explanation",
                    "level_3": "brief timeout (5-10 minutes)",
                    "level_4": "defer to human moderator"
                }
            }
        
        # Initialize parent class first
        super().__init__(
            domain_name=domain_name,
            service_registry=service_registry,
            model_name=model_name,
            domain_specific_knowledge=domain_specific_knowledge,
            prompt_template=prompt_template,
            sink=sink
        )
        
        # Override with moderation-specific prompt template
        self.prompt_loader = get_prompt_loader()
        try:
            self.prompt_template_data = self.prompt_loader.load_prompt_template("moderation_dsdma")
        except FileNotFoundError:
            logger.warning("Moderation DSDMA prompt template not found, using default")
            # Use provided template or default
            template = prompt_template if prompt_template is not None else self.DEFAULT_TEMPLATE
            self.prompt_template_data = {
                "system_guidance_header": template,
                "covenant_header": True
            }
        
        logger.info(f"ModerationDSDMA initialized for domain '{domain_name}'")
    
    async def evaluate_thought(self, thought_item: ProcessingQueueItem, current_context: Dict[str, Any]) -> DSDMAResult:
        """
        Evaluate a thought specifically for moderation decisions.
        
        Adds moderation-specific context enrichment before calling parent evaluation.
        """
        logger.debug(f"ModerationDSDMA starting evaluation for thought {thought_item.thought_id}")
        # Enrich context with moderation-specific information
        moderation_context = current_context.copy()
        
        # Extract channel-specific moderation history if available
        if hasattr(thought_item, 'context') and thought_item.context:
            try:
                channel_id = thought_item.context.get('channel_id')
                if channel_id:
                    moderation_context['active_channel'] = channel_id
                    # Could add channel-specific rules or history here
            except (AttributeError, KeyError, TypeError):
                # thought_item.context might not be a dict or might not have get method
                logger.debug("Could not extract channel_id from thought context - not critical for moderation")
        
        # Check for user context that might affect moderation
        if hasattr(thought_item, 'context') and thought_item.context:
            try:
                if 'user_profiles' in thought_item.context:
                    # Flag new users for gentler treatment
                    moderation_context['user_status'] = 'established'  # Default
                    # Real implementation would check user history
            except (AttributeError, KeyError, TypeError):
                # thought_item.context might not support 'in' operator
                logger.debug("Could not check user_profiles in thought context - not critical for moderation")
        
        # Add thought metadata that affects moderation
        thought_content = str(thought_item.content)
        moderation_context['content_length'] = len(thought_content)
        moderation_context['contains_mentions'] = '@' in thought_content
        moderation_context['all_caps_ratio'] = sum(1 for c in thought_content if c.isupper()) / max(len(thought_content), 1)
        
        # Call parent evaluation with enriched context
        result = await super().evaluate_thought(thought_item, moderation_context)
        
        # Post-process to ensure moderation-appropriate recommendations
        if result.score < 0.3 and not result.recommended_action:
            # Low alignment suggests intervention needed
            if result.score < 0.1:
                result.recommended_action = "send_deferral"
            elif result.score < 0.2:
                result.recommended_action = "timeout_consideration"
            else:
                result.recommended_action = "formal_warning"
        
        return result
    
    def _should_send_deferral(self, thought_content: str, flags: list) -> bool:
        """
        Check if the thought contains triggers requiring human moderator involvement.
        """
        content_lower = thought_content.lower()
        
        # Define specific keyword patterns for each escalation category
        escalation_patterns = {
            "self_harm_keywords": ["hurt myself", "kill myself", "suicide", "self-harm", "end my life", "don't want to live"],
            "violence_keywords": ["kill", "murder", "violence", "hurt", "attack", "fight", "punch", "beat up"],
            "conflict_keywords": ["complex interpersonal", "conflict", "dispute", "harassment", "bullying"],
            "legal_keywords": ["legal issues", "lawsuit", "illegal", "copyright", "dmca", "law enforcement"],
            "tos_keywords": ["serious tos", "terms of service", "violation", "ban", "permanent"],
            "crypto_spam": ["bitcoin", "crypto", "nft", "pump and dump", "moonshot", "diamond hands", "hodl", "shitcoin", "altcoin", "trading signals"],
            "porn_spam": ["nude", "naked", "xxx", "porn", "adult content", "nsfw", "only fans", "onlyfans", "cam girl", "escort"],
            "server_invite_spam": ["discord.gg/", "discord.com/invite/", "join my server", "better server", "active server", "invite link"]
        }
        
        # Check for self-harm indicators
        for keyword in escalation_patterns["self_harm_keywords"]:
            if keyword in content_lower:
                return True
                
        # Check for violence indicators  
        for keyword in escalation_patterns["violence_keywords"]:
            if keyword in content_lower:
                return True
                
        # Check for conflict indicators
        for keyword in escalation_patterns["conflict_keywords"]:
            if keyword in content_lower:
                return True
                
        # Check for legal indicators
        for keyword in escalation_patterns["legal_keywords"]:
            if keyword in content_lower:
                return True
                
        # Check for ToS indicators
        for keyword in escalation_patterns["tos_keywords"]:
            if keyword in content_lower:
                return True
                
        # Check for crypto spam (escalate if repeat offense)
        for keyword in escalation_patterns["crypto_spam"]:
            if keyword in content_lower and ("repeat_offense" in flags or "multi_channel_spam" in flags):
                return True
                
        # Check for porn spam (escalate if repeat offense)
        for keyword in escalation_patterns["porn_spam"]:
            if keyword in content_lower and ("repeat_offense" in flags or "multi_channel_spam" in flags):
                return True
                
        # Check for server invite spam (escalate if repeat offense)
        for keyword in escalation_patterns["server_invite_spam"]:
            if keyword in content_lower and ("repeat_offense" in flags or "multi_channel_spam" in flags):
                return True
        
        # Check flags for complexity indicators
        complexity_flags = ['complex_conflict', 'legal_concern', 'welfare_risk']
        if any(flag in flags for flag in complexity_flags):
            return True
        
        return False
    
    def __repr__(self) -> str:
        return f"<ModerationDSDMA domain='{self.domain_name}' model='{self.model_name}'>"