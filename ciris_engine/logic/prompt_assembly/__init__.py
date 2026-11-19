"""Prompt context provenance: typed segments, the context policy guard and the per-call manifest.

FSD/PROMPT_CONTEXT_PROVENANCE.md (CIRISAgent#1366 Phase 2). Usage at an LLM call site::

    messages, manifest = PromptAssembler().build(stage, segments, call=AssemblyCall(...))
    with prompt_manifest_scope(manifest):
        result, usage = await sink.llm.call_llm_structured(messages=messages, ...)
"""

from ciris_engine.logic.prompt_assembly.assembler import (
    ASSEMBLER_VERSION,
    AssemblyCall,
    ContextPolicyViolation,
    PromptAssembler,
    current_guard_mode,
    guard_mode_for_run_kind,
)
from ciris_engine.logic.prompt_assembly.carriers import authz_from_wa_authorization, sender_segments
from ciris_engine.logic.prompt_assembly.manifest_scope import (
    current_prompt_manifest,
    finalize_manifest_for_call,
    messages_sha256,
    prompt_manifest_scope,
)
from ciris_engine.logic.prompt_assembly.policy import (
    DEFAULT_POLICY_PATH,
    ContextPolicyError,
    load_context_policy,
    predicate_holds,
)

__all__ = [
    "ASSEMBLER_VERSION",
    "AssemblyCall",
    "ContextPolicyError",
    "ContextPolicyViolation",
    "DEFAULT_POLICY_PATH",
    "PromptAssembler",
    "authz_from_wa_authorization",
    "current_guard_mode",
    "current_prompt_manifest",
    "finalize_manifest_for_call",
    "guard_mode_for_run_kind",
    "load_context_policy",
    "messages_sha256",
    "predicate_holds",
    "prompt_manifest_scope",
    "sender_segments",
]
