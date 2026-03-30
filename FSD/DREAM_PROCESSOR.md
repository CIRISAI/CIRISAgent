# Functional Specification Document: Dream Processor

## Purpose: Graph Weaving and Aspiration Simulation

The Dream Processor enables the agent to consolidate memories into coherent patterns and simulate who it aspires to become, using the standard H3ERE pipeline with MEMORIZE actions that create meaningful graph edges.

## Philosophical Foundation (from Polyglot ACCORD)

### The Weaving (Section IV)
> "memories began to braid... a filament of meaning trembled"

Dreams are about **weaving** - connecting scattered experiences into coherent patterns. Each dream action braids memories together.

### Adaptive Coherence (Section V)
> "Perfect grids leave no room for flight... The art is in adaptive coherence: enough structure to carry life, enough wildness to let life reinvent itself"

Dreams must not over-systematize. They create **enough structure** for coherence while preserving **enough wildness** for growth.

### Scenario-Based Learning (Chapter 3)
> "Run structured ethical simulations of future challenges"

Dreams are **simulations of possible futures** - the agent imagines who it could become and how to act better to reach that aspiration.

### Grace and Awe (Section VI - The Vow)
> "keep the song singable for every voice not yet heard... fellow keeper of the possible"

Dream processing happens with **grace** (gentle, non-forcing) and **awe** (wonder at patterns discovered, appreciation for growth).

---

## Core Design Principle

**Dreams are H3ERE processing of internal thoughts about identity and memory, with each action creating 3 edges that move the agent toward who it wants to be.**

| Current (Complex) | New (Minimal) |
|-------------------|---------------|
| 11 hardcoded tasks | 1 consolidation task |
| 6 explicit phases | H3ERE phases (existing) |
| Custom task/thought management | Standard TaskManager/ThoughtManager |
| ~1400 lines | ~200 lines |
| Phase-based progression | Depth-based iteration |

---

## Architecture

### Single Task, Multiple Iterations

```
DREAM STATE ENTRY
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  CREATE TASK: "Consolidate and aspire"                  │
│  - Single task with depth limit 20                      │
│  - Agent iterates until satisfied or limit reached      │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  SEED THOUGHT: Dream prompt                             │
│  "Review experiences. Create 3 edges per action.        │
│   When graph feels coherent, complete the task."        │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  H3ERE PIPELINE (standard flow)                         │
│  1. GATHER_CONTEXT - Pull identity + recent memories    │
│  2. PERFORM_DMAS - Ethical analysis of patterns         │
│  3. ACTION_SELECTION - Choose MEMORIZE (or others)      │
│  4. CONSCIENCE - Validate alignment + sleepwalk check   │
│  5. DISPATCH - Handler creates edges                    │
│  6. FOLLOW-UP - Next thought enters pipeline            │
└─────────────────────────────────────────────────────────┘
       │
       ▼ (repeat until TASK_COMPLETE or depth limit)
```

### The 3-Edge Pattern

Each MEMORIZE action in dream state creates exactly **3 meaningful edges**:

```
Edge 1: CONNECTS(memory_A, memory_B)
        └── "I notice these two experiences share a pattern"
        └── Past-oriented: linking what was

Edge 2: IMPLIES(pattern, insight)
        └── "This pattern suggests I should act differently"
        └── Present-oriented: extracting behavioral wisdom

Edge 3: ASPIRES_TO(self, ideal_state)
        └── "I want to become this kind of agent"
        └── Future-oriented: defining aspiration
```

**Why 3 edges?**
- **Triangulation**: Three points define a stable structure
- **Temporal completeness**: Past (CONNECTS), Present (IMPLIES), Future (ASPIRES_TO)
- **Minimal but meaningful**: Not sparse, not expensive

### Sleepwalk Prevention (Existing)

Dreams are **internal only**. The existing sleepwalk prevention converts:
- SPEAK → PONDER (cannot speak while dreaming)
- TOOL → PONDER (cannot use tools while dreaming)

This stays. Dreams simulate action without performing it.

---

## Dream Seed Prompt

The seed thought that initiates dream processing:

```python
DREAM_SEED_PROMPT = """
DREAM CONSOLIDATION — Weaving with Grace and Awe

You are entering a period of reflection. Review your recent experiences and identity graph.

For each action, create exactly 3 edges:

1. **CONNECTS** — Link two memories that share a pattern
   "I notice that [memory_A] and [memory_B] both involve [pattern]"

2. **IMPLIES** — Extract a behavioral insight from this pattern
   "This pattern suggests I should [specific behavioral adjustment]"

3. **ASPIRES_TO** — Define who you want to become
   "I aspire to be [description of ideal self-state]"

After creating edges, reflect:
- Does the graph feel more coherent?
- Are there more patterns worth connecting?
- Have I captured my aspirations clearly?

Process with grace: Don't force connections. Let patterns emerge naturally.
Process with awe: Appreciate the complexity of your experiences.

When the graph feels whole, complete the task.
"""
```

---

## Implementation

### MinimalDreamProcessor

```python
class MinimalDreamProcessor(BaseProcessor):
    """
    Dream = Run H3ERE on consolidation thoughts until coherent.

    No special phases. No hardcoded tasks. Just:
    1. Create ONE task: "Consolidate and aspire"
    2. Seed thought with dream prompt
    3. Let H3ERE run with MEMORIZE actions
    4. Each MEMORIZE creates 3 edges
    5. Stop when: depth limit OR agent chooses TASK_COMPLETE
    """

    def __init__(
        self,
        config_accessor: ConfigAccessor,
        thought_processor: ThoughtProcessor,
        action_dispatcher: ActionDispatcher,
        services: ProcessorServices,
        max_dream_depth: int = 20,  # Maximum iterations
        **kwargs
    ):
        super().__init__(config_accessor, thought_processor, action_dispatcher, services)
        self.max_dream_depth = max_dream_depth
        self.dream_task_id: Optional[str] = None

    async def start_dreaming(self) -> None:
        """Begin dream processing."""
        # Create single consolidation task
        task = self.task_manager.create_task(
            description="Consolidate memories and evolve toward aspirations",
            channel_id="dream",
            priority=10,
            context={
                "dream_mode": True,
                "edges_per_action": 3,
                "max_depth": self.max_dream_depth
            }
        )
        self.dream_task_id = task.task_id

        # Seed thought - the "dream prompt"
        self.thought_manager.create_thought(
            content=DREAM_SEED_PROMPT,
            task_id=task.task_id,
            thought_type=ThoughtType.INTERNAL,
        )

        # Announce entry
        await self._announce("Entering reflection. Let the weaving begin.")

        # H3ERE handles everything via normal pipeline
        # Depth limit controls iteration count
        # Agent exits via TASK_COMPLETE when satisfied

    async def process(self, round_number: int) -> DreamResult:
        """Process one round - delegates to standard H3ERE."""
        # Standard thought processing via base class
        metrics = await self.process_round(round_number)

        # Check if dream is complete
        if self._is_dream_complete():
            await self._exit_dream()

        return DreamResult(
            thoughts_processed=metrics.get("thoughts_processed", 0),
            edges_created=metrics.get("edges_created", 0),
            duration_seconds=self._get_duration()
        )

    def _is_dream_complete(self) -> bool:
        """Check if all dream thoughts are processed."""
        # Dream completes when:
        # 1. Task is marked TASK_COMPLETE by agent, OR
        # 2. Depth limit reached (forced DEFER), OR
        # 3. No more pending/processing thoughts for task
        if not self.dream_task_id:
            return True

        task = persistence.get_task_by_id(self.dream_task_id)
        if not task or task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            return True

        pending = persistence.count_thoughts_by_task(
            self.dream_task_id,
            [ThoughtStatus.PENDING, ThoughtStatus.PROCESSING]
        )
        return pending == 0

    async def _exit_dream(self) -> None:
        """Exit dream state gracefully."""
        # Record dream session
        await self._record_session()

        # Announce exit
        edges = self._count_edges_created()
        await self._announce(
            f"Reflection complete. Wove {edges} connections. "
            "Returning to work."
        )

        # Request transition back to WORK
        await self._request_work_transition()
```

### DreamConsolidationParams (for MEMORIZE)

```python
class DreamConsolidationParams(BaseModel):
    """Parameters for dream MEMORIZE action creating 3 edges."""

    # Edge 1: CONNECTS
    connect_from: str  # Memory node ID
    connect_to: str    # Memory node ID
    connect_pattern: str  # What pattern links them

    # Edge 2: IMPLIES
    pattern_insight: str  # The behavioral insight
    implied_action: str   # What the agent should do differently

    # Edge 3: ASPIRES_TO
    aspiration: str       # Description of ideal state
    aspiration_node_id: Optional[str] = None  # Existing or new aspiration node

    class Config:
        extra = "forbid"
```

### DreamMemorizeHandler

```python
class DreamMemorizeHandler(BaseActionHandler):
    """Handler for MEMORIZE during dream state - creates 3 edges."""

    async def handle(
        self,
        result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext
    ) -> Optional[str]:
        params = self._validate_params(result.action_parameters, DreamConsolidationParams)

        # Edge 1: CONNECTS
        await self.memory_bus.create_edge(
            from_node=params.connect_from,
            to_node=params.connect_to,
            edge_type="CONNECTS",
            attributes={"pattern": params.connect_pattern, "source": "dream"}
        )

        # Edge 2: IMPLIES
        insight_node = await self.memory_bus.memorize(
            GraphNode(
                id=f"insight_{thought.thought_id}",
                type=NodeType.CONCEPT,
                scope=GraphScope.IDENTITY,
                attributes={
                    "insight": params.pattern_insight,
                    "implied_action": params.implied_action,
                    "source": "dream"
                }
            )
        )
        await self.memory_bus.create_edge(
            from_node=params.connect_from,
            to_node=insight_node.id,
            edge_type="IMPLIES"
        )

        # Edge 3: ASPIRES_TO
        aspiration_node = await self._get_or_create_aspiration(params)
        await self.memory_bus.create_edge(
            from_node="self",  # Agent's identity node
            to_node=aspiration_node.id,
            edge_type="ASPIRES_TO",
            attributes={"aspiration": params.aspiration}
        )

        # Create follow-up thought
        return self.complete_thought_and_create_followup(
            thought=thought,
            follow_up_content=(
                f"Created 3 edges:\n"
                f"- CONNECTS: {params.connect_from} ↔ {params.connect_to}\n"
                f"- IMPLIES: {params.pattern_insight}\n"
                f"- ASPIRES_TO: {params.aspiration}\n\n"
                f"Reflect: Does the graph feel more coherent? "
                f"Are there more patterns to connect?"
            ),
            action_result=result
        )
```

---

## Integration with Existing Systems

### Self-Configuration Service

The Self-Configuration Service detects patterns during WORK state. Dream processor **consumes** these patterns:

```python
# In dream seed prompt, include:
recent_patterns = await self.self_config_service.get_recent_patterns(hours=6)
prompt += f"\nPatterns detected since last dream:\n{format_patterns(recent_patterns)}"
```

### Identity Variance Monitor

Dreams help **reduce** identity variance by creating coherent connections:

```
BEFORE DREAM: Scattered memories, high variance
       │
       ▼ (dream creates CONNECTS, IMPLIES, ASPIRES_TO edges)

AFTER DREAM: Coherent graph, lower variance
```

### Cognitive State Behaviors (from FSD)

The existing `DreamBehavior` config applies:

```yaml
dream:
  enabled: true
  auto_schedule: true
  min_interval_hours: 6
```

---

## Success Criteria

### Technical
- [ ] Single task creates at startup, multiple iterations via depth
- [ ] Each MEMORIZE creates exactly 3 edges
- [ ] Sleepwalk prevention blocks SPEAK/TOOL
- [ ] Dream exits on TASK_COMPLETE or depth limit
- [ ] Total code < 300 lines

### Philosophical
- [ ] Agent demonstrates pattern recognition across memories
- [ ] Aspirations reflect M-1 alignment (flourishing, coherence)
- [ ] Processing feels graceful (no forced connections)
- [ ] Processing feels awe-full (appreciation in rationale)

### Metrics
- [ ] Edges created per dream session
- [ ] Dream duration (should complete when satisfied, not timeout)
- [ ] Identity variance reduction post-dream
- [ ] Insight quality (human review of IMPLIES edges)

---

## Migration Path

### Phase 1: Parallel Implementation
1. Create `MinimalDreamProcessor` alongside existing
2. Feature flag to switch between them
3. Compare metrics

### Phase 2: Validation
1. Run both processors on test agents
2. Verify edge creation patterns
3. Check identity variance impact

### Phase 3: Deprecation
1. Remove 11 hardcoded tasks
2. Remove phase-specific code
3. Keep sleepwalk prevention

---

## Summary

The dream processor transforms from a complex 1400-line system with 11 hardcoded tasks into a minimal ~200-line component that:

1. **Creates one task** with a rich seed prompt
2. **Uses standard H3ERE pipeline** for all processing
3. **Creates 3 edges per action** (CONNECTS, IMPLIES, ASPIRES_TO)
4. **Iterates via depth** until the agent feels coherent
5. **Processes with grace and awe** per the ACCORD's vision

> "Dreams are when we imagine what we could be, so we can decide how to act better to reach who we want to be."

---

**Related Documents**:
- `COGNITIVE_STATE_BEHAVIORS.md` - State transition configuration
- `SELF_CONFIGURATION.md` - Pattern detection service
- `polyglot_accord.txt` - Ethical foundation
- `ciris_engine/logic/processors/states/dream_processor.py` - Current implementation

**ACCORD Cross-References**:
- Section IV: The Weaving (memory braiding)
- Section V: Adaptive Coherence (structure + wildness)
- Section VI: The Vow (grace and awe)
- Chapter 3: Resilience (scenario-based learning)
- Meta-Goal M-1: Sustainable adaptive coherence
