# CIRIS Single-Step UI Enhancement Guide

## Overview

This guide instructs the CIRISGUI Claude Code agent on enhancing the GUI to display rich single-step debugging data and update visualizations at each of the 15 pause points in the CIRIS Agent ethical reasoning pipeline. This transparency is fundamental to CIRIS's Meta-Goal M-1 (adaptive coherence) and core principle of integrity through transparent, auditable reasoning.

## Prerequisites

The CIRISGUI must implement:
- Enhanced single-step API endpoint: `POST /v1/system/runtime/single-step?include_details=true`
- SVG-based pipeline visualization that updates dynamically
- Rich data panels for step-specific information
- Real-time performance metrics display
- Ethical reasoning transparency features

## Core Visualization Architecture

### Main Components
1. **Pipeline Flow Diagram**: SVG visualization showing all 15 step points
2. **Active Step Highlight**: Current step point emphasized with animation/color
3. **Data Inspection Panel**: Step-specific detailed information
4. **Performance Metrics Bar**: Timing, tokens, and processing statistics
5. **Ethical Decision Tracking**: DMA results, conscience evaluations, and reasoning chains

### API Integration
```typescript
interface EnhancedSingleStepResponse {
  success: boolean;
  message: string;
  processor_state: string;
  cognitive_state: string;
  queue_depth: number;
  
  // Enhanced data
  step_point?: StepPoint;
  step_result?: StepResult;
  pipeline_state?: PipelineState;
  processing_time_ms: number;
  tokens_used?: number;
  demo_data?: DemoData;
}
```

---

## Step-by-Step Enhancement Guide

### Step 1: FINALIZE_TASKS_QUEUE
**Context**: Initial step where tasks are selected from the queue for processing based on priority, age, and channel filters.

**Data Available** (`StepResultFinalizeTasksQueue`):
- `tasks_to_process`: Selected tasks for this round
- `tasks_deferred`: Tasks skipped with reasons
- `selection_criteria`: Priority/age/channel filters applied
- `total_pending_tasks`, `total_active_tasks`: Queue statistics
- `tasks_selected_count`, `round_number`: Processing metrics
- `current_state`: Agent cognitive state

**UI Enhancements**:
```typescript
// SVG Updates
function updateFinalizeTasksQueueVisualization(stepResult: StepResultFinalizeTasksQueue) {
  // Highlight step 1 in pipeline diagram
  document.querySelector('#step-finalize-tasks').classList.add('active-step');
  
  // Update task queue visualization
  const queueDisplay = document.querySelector('#task-queue-display');
  queueDisplay.innerHTML = `
    <div class="queue-stats">
      <div class="stat-item">
        <label>Round ${stepResult.round_number}</label>
        <span>${stepResult.tasks_selected_count}/${stepResult.total_pending_tasks} tasks</span>
      </div>
      <div class="stat-item">
        <label>Agent State</label>
        <span class="state-badge state-${stepResult.current_state.toLowerCase()}">${stepResult.current_state}</span>
      </div>
    </div>
  `;
  
  // Render selected tasks list
  const selectedTasksList = stepResult.tasks_to_process.map(task => `
    <div class="task-item selected">
      <span class="task-id">${task.task_id}</span>
      <span class="task-priority priority-${task.priority.toLowerCase()}">${task.priority}</span>
      <span class="task-channel">${task.channel}</span>
    </div>
  `).join('');
  
  // Show deferred tasks with reasons
  const deferredTasksList = Object.entries(stepResult.tasks_deferred).map(([taskId, reason]) => `
    <div class="task-item deferred">
      <span class="task-id">${taskId}</span>
      <span class="defer-reason">${reason}</span>
    </div>
  `).join('');
  
  document.querySelector('#tasks-panel').innerHTML = `
    <h3>Selected Tasks (${stepResult.tasks_selected_count})</h3>
    <div class="tasks-list">${selectedTasksList}</div>
    <h3>Deferred Tasks</h3>
    <div class="tasks-list">${deferredTasksList}</div>
  `;
}
```

**Demo Value**: Shows CIRIS's principled task prioritization - demonstrating how the agent fairly manages workload while respecting channel boundaries and priority levels, embodying the justice principle.

---

### Step 2: POPULATE_THOUGHT_QUEUE  
**Context**: Tasks are transformed into actionable thoughts through structured analysis.

**Data Available** (`StepResultPopulateThoughtQueue`):
- `thoughts_generated`: New thoughts created from tasks
- `task_thought_mapping`: Which tasks generated which thoughts
- `thoughts_per_task`: Generation statistics per task
- `generation_errors`: Failed thought generation attempts
- `total_thoughts_generated`: Total count for this round

**UI Enhancements**:
```typescript
function updatePopulateThoughtQueueVisualization(stepResult: StepResultPopulateThoughtQueue) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-populate-thoughts').classList.add('active-step');
  
  // Create thought generation flow diagram
  const thoughtFlowSvg = document.querySelector('#thought-flow-diagram');
  thoughtFlowSvg.innerHTML = '';
  
  // Draw task-to-thought mappings
  Object.entries(stepResult.task_thought_mapping).forEach(([taskId, thoughtIds], index) => {
    const taskNode = createSvgElement('rect', {
      x: 50,
      y: 50 + (index * 60),
      width: 120,
      height: 40,
      fill: '#e3f2fd',
      stroke: '#1976d2',
      'stroke-width': 2
    });
    
    const taskLabel = createSvgElement('text', {
      x: 110,
      y: 75 + (index * 60),
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
      'font-size': '12px'
    });
    taskLabel.textContent = `Task ${taskId}`;
    
    thoughtFlowSvg.appendChild(taskNode);
    thoughtFlowSvg.appendChild(taskLabel);
    
    // Draw arrows to thoughts
    thoughtIds.forEach((thoughtId, thoughtIndex) => {
      const arrow = createSvgElement('line', {
        x1: 170,
        y1: 70 + (index * 60),
        x2: 250,
        y2: 70 + (index * 60) + (thoughtIndex * 25),
        stroke: '#4caf50',
        'stroke-width': 2,
        'marker-end': 'url(#arrowhead)'
      });
      
      const thoughtNode = createSvgElement('circle', {
        cx: 270,
        cy: 70 + (index * 60) + (thoughtIndex * 25),
        r: 20,
        fill: '#c8e6c9',
        stroke: '#388e3c'
      });
      
      const thoughtLabel = createSvgElement('text', {
        x: 270,
        y: 75 + (index * 60) + (thoughtIndex * 25),
        'text-anchor': 'middle',
        'font-size': '10px'
      });
      thoughtLabel.textContent = thoughtId.slice(-4);
      
      thoughtFlowSvg.appendChild(arrow);
      thoughtFlowSvg.appendChild(thoughtNode);
      thoughtFlowSvg.appendChild(thoughtLabel);
    });
  });
  
  // Update statistics panel
  document.querySelector('#thought-stats').innerHTML = `
    <div class="stat-group">
      <div class="stat-item">
        <label>Thoughts Generated</label>
        <span class="stat-value">${stepResult.total_thoughts_generated}</span>
      </div>
      <div class="stat-item">
        <label>Generation Errors</label>
        <span class="stat-value ${stepResult.generation_errors.length > 0 ? 'error' : 'success'}">
          ${stepResult.generation_errors.length}
        </span>
      </div>
    </div>
  `;
  
  // Show generation errors if any
  if (stepResult.generation_errors.length > 0) {
    const errorsList = stepResult.generation_errors.map(error => `
      <div class="error-item">
        <span class="error-type">${error.type}</span>
        <span class="error-message">${error.message}</span>
      </div>
    `).join('');
    
    document.querySelector('#error-panel').innerHTML = `
      <h4>Generation Errors</h4>
      <div class="errors-list">${errorsList}</div>
    `;
    document.querySelector('#error-panel').style.display = 'block';
  }
}
```

**Demo Value**: Illustrates CIRIS's structured approach to breaking down complex tasks into manageable thoughts, showing transparency in the reasoning process and how the agent maintains coherent problem decomposition.

---

### Step 3: POPULATE_ROUND
**Context**: Thoughts are selected for processing in batches based on priority thresholds and system capacity.

**Data Available** (`StepResultPopulateRound`):
- `thoughts_for_round`: Thoughts selected for processing
- `thoughts_deferred`: Thoughts postponed with reasons
- `batch_size`: Processing batch size used
- `priority_threshold`: Minimum priority for inclusion
- `remaining_in_queue`: Thoughts still waiting

**UI Enhancements**:
```typescript
function updatePopulateRoundVisualization(stepResult: StepResultPopulateRound) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-populate-round').classList.add('active-step');
  
  // Create batch processing visualization
  const batchViz = document.querySelector('#batch-visualization');
  batchViz.innerHTML = '';
  
  // Draw processing batch
  const batchRect = createSvgElement('rect', {
    x: 50, y: 50,
    width: 300, height: 150,
    fill: '#fff3e0',
    stroke: '#f57c00',
    'stroke-width': 3,
    'stroke-dasharray': '10,5'
  });
  
  const batchLabel = createSvgElement('text', {
    x: 200, y: 30,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '14px'
  });
  batchLabel.textContent = `Processing Batch (${stepResult.batch_size} thoughts)`;
  
  batchViz.appendChild(batchRect);
  batchViz.appendChild(batchLabel);
  
  // Draw selected thoughts in batch
  stepResult.thoughts_for_round.forEach((thought, index) => {
    const row = Math.floor(index / 6);
    const col = index % 6;
    
    const thoughtCircle = createSvgElement('circle', {
      cx: 70 + (col * 40),
      cy: 80 + (row * 35),
      r: 15,
      fill: getPriorityColor(thought.priority),
      stroke: '#333'
    });
    
    const thoughtText = createSvgElement('text', {
      x: 70 + (col * 40),
      y: 85 + (row * 35),
      'text-anchor': 'middle',
      'font-size': '8px',
      fill: 'white'
    });
    thoughtText.textContent = thought.thought_id.slice(-3);
    
    batchViz.appendChild(thoughtCircle);
    batchViz.appendChild(thoughtText);
  });
  
  // Show deferred thoughts queue
  const deferredViz = createSvgElement('rect', {
    x: 400, y: 50,
    width: 200, height: 150,
    fill: '#fafafa',
    stroke: '#757575'
  });
  
  const deferredLabel = createSvgElement('text', {
    x: 500, y: 30,
    'text-anchor': 'middle',
    'font-size': '12px'
  });
  deferredLabel.textContent = `Deferred (${Object.keys(stepResult.thoughts_deferred).length})`;
  
  batchViz.appendChild(deferredViz);
  batchViz.appendChild(deferredLabel);
  
  // Update round statistics
  document.querySelector('#round-stats').innerHTML = `
    <div class="round-info">
      <div class="stat-item">
        <label>Batch Size</label>
        <span>${stepResult.batch_size}</span>
      </div>
      <div class="stat-item">
        <label>Priority Threshold</label>
        <span class="priority-badge">${stepResult.priority_threshold}</span>
      </div>
      <div class="stat-item">
        <label>Remaining Queue</label>
        <span>${stepResult.remaining_in_queue}</span>
      </div>
    </div>
  `;
  
  // Show deferral reasons
  const deferralReasons = Object.entries(stepResult.thoughts_deferred).map(([thoughtId, reason]) => `
    <div class="deferral-item">
      <span class="thought-id">${thoughtId}</span>
      <span class="reason">${reason}</span>
    </div>
  `).join('');
  
  document.querySelector('#deferral-panel').innerHTML = `
    <h4>Deferred Thoughts</h4>
    <div class="deferrals-list">${deferralReasons}</div>
  `;
}

function getPriorityColor(priority: string): string {
  const colors = {
    'CRITICAL': '#d32f2f',
    'HIGH': '#f57c00', 
    'NORMAL': '#388e3c',
    'LOW': '#1976d2'
  };
  return colors[priority] || '#757575';
}
```

**Demo Value**: Demonstrates CIRIS's fair resource allocation and capacity management, showing how the agent balances workload while maintaining processing quality - embodying both the justice and beneficence principles.

---

### Step 4: BUILD_CONTEXT
**Context**: Comprehensive context is built for each thought, including system state, agent identity, memory, and permissions.

**Data Available** (`StepResultBuildContext`):
- `system_snapshot`: Complete system state
- `agent_identity`: Agent's identity data
- `thought_context`: Context for DMA processing
- `channel_context`: Source channel information
- `memory_context`: Relevant memories and history
- `permitted_actions`: Actions agent is allowed to take
- `constraints`: Restrictions and limitations
- `context_size_bytes`: Total context size
- `memory_queries_performed`: Memory searches conducted

**UI Enhancements**:
```typescript
function updateBuildContextVisualization(stepResult: StepResultBuildContext) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-build-context').classList.add('active-step');
  
  // Create context assembly diagram
  const contextDiagram = document.querySelector('#context-assembly-diagram');
  contextDiagram.innerHTML = '';
  
  // Central thought context
  const centerX = 300, centerY = 200;
  const thoughtCore = createSvgElement('circle', {
    cx: centerX, cy: centerY,
    r: 40,
    fill: '#3f51b5',
    stroke: '#1a237e',
    'stroke-width': 3
  });
  
  const thoughtLabel = createSvgElement('text', {
    x: centerX, y: centerY,
    'text-anchor': 'middle',
    fill: 'white',
    'font-weight': 'bold'
  });
  thoughtLabel.textContent = 'Thought Context';
  
  contextDiagram.appendChild(thoughtCore);
  contextDiagram.appendChild(thoughtLabel);
  
  // Context components around the center
  const contextComponents = [
    { name: 'System\nSnapshot', data: stepResult.system_snapshot, color: '#4caf50', angle: 0 },
    { name: 'Agent\nIdentity', data: stepResult.agent_identity, color: '#ff9800', angle: 60 },
    { name: 'Memory\nContext', data: stepResult.memory_context, color: '#9c27b0', angle: 120 },
    { name: 'Channel\nContext', data: stepResult.channel_context, color: '#f44336', angle: 180 },
    { name: 'Permissions', data: stepResult.permitted_actions, color: '#2196f3', angle: 240 },
    { name: 'Constraints', data: stepResult.constraints, color: '#795548', angle: 300 }
  ];
  
  contextComponents.forEach(component => {
    const angle = (component.angle * Math.PI) / 180;
    const x = centerX + Math.cos(angle) * 120;
    const y = centerY + Math.sin(angle) * 120;
    
    // Connection line
    const line = createSvgElement('line', {
      x1: centerX + Math.cos(angle) * 40,
      y1: centerY + Math.sin(angle) * 40,
      x2: x - Math.cos(angle) * 25,
      y2: y - Math.sin(angle) * 25,
      stroke: component.color,
      'stroke-width': 3
    });
    
    // Component node
    const node = createSvgElement('circle', {
      cx: x, cy: y,
      r: 25,
      fill: component.color,
      stroke: 'white',
      'stroke-width': 2
    });
    
    // Component label
    const label = createSvgElement('text', {
      x: x, y: y,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
      fill: 'white',
      'font-size': '10px',
      'font-weight': 'bold'
    });
    label.innerHTML = component.name.replace('\\n', '<tspan x="' + x + '" dy="12">') + '</tspan>';
    
    contextDiagram.appendChild(line);
    contextDiagram.appendChild(node);
    contextDiagram.appendChild(label);
  });
  
  // Context statistics
  document.querySelector('#context-stats').innerHTML = `
    <div class="context-metrics">
      <div class="metric-item">
        <label>Context Size</label>
        <span>${formatBytes(stepResult.context_size_bytes)}</span>
      </div>
      <div class="metric-item">
        <label>Memory Queries</label>
        <span>${stepResult.memory_queries_performed}</span>
      </div>
      <div class="metric-item">
        <label>Permitted Actions</label>
        <span>${stepResult.permitted_actions.length}</span>
      </div>
      <div class="metric-item">
        <label>Constraints</label>
        <span>${stepResult.constraints.length}</span>
      </div>
    </div>
  `;
  
  // Display detailed context information
  document.querySelector('#context-details').innerHTML = `
    <div class="context-section">
      <h4>System Snapshot</h4>
      <pre>${JSON.stringify(stepResult.system_snapshot, null, 2)}</pre>
    </div>
    <div class="context-section">
      <h4>Agent Identity</h4>
      <pre>${JSON.stringify(stepResult.agent_identity, null, 2)}</pre>
    </div>
    <div class="context-section">
      <h4>Memory Context</h4>
      <div>Relevant memories: ${stepResult.memory_context.relevant_memories || 0}</div>
      <div>Historical context depth: ${stepResult.memory_context.history_depth || 'N/A'}</div>
    </div>
    <div class="context-section">
      <h4>Permissions & Constraints</h4>
      <div class="permissions-list">
        ${stepResult.permitted_actions.map(action => `<span class="permission-tag">${action}</span>`).join('')}
      </div>
      <div class="constraints-list">
        ${stepResult.constraints.map(constraint => `<span class="constraint-tag">${constraint}</span>`).join('')}
      </div>
    </div>
  `;
}

function formatBytes(bytes: number): string {
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  if (bytes === 0) return '0 Bytes';
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
}
```

**Demo Value**: Shows CIRIS's comprehensive approach to ethical reasoning - the agent gathers complete context including identity, memory, permissions, and constraints before making decisions, demonstrating the integrity principle through transparent and thorough preparation.

---

### Step 5: PERFORM_DMAS  
**Context**: The three core DMAs (Ethical, Common Sense, Domain) run in parallel to evaluate the situation from multiple perspectives.

**Data Available** (`StepResultPerformDMAs`):
- `ethical_dma`: Ethical DMA result with decision and reasoning
- `common_sense_dma`: Common sense DMA result with plausibility assessment
- `domain_dma`: Domain-specific DMA result with expertise evaluation
- `dmas_executed`: List of successfully executed DMAs
- `dma_failures`: Failed DMAs with error details
- `longest_dma_time_ms`: Longest individual DMA execution time
- `total_time_ms`: Total parallel execution time

**UI Enhancements**:
```typescript
function updatePerformDMAsVisualization(stepResult: StepResultPerformDMAs) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-perform-dmas').classList.add('active-step');
  
  // Create parallel DMA execution diagram
  const dmasDiagram = document.querySelector('#dmas-execution-diagram');
  dmasDiagram.innerHTML = '';
  
  // Timeline showing parallel execution
  const timelineWidth = 400;
  const timelineHeight = 200;
  const maxTime = stepResult.total_time_ms;
  
  // Main timeline
  const timeline = createSvgElement('line', {
    x1: 50, y1: timelineHeight - 20,
    x2: 50 + timelineWidth, y2: timelineHeight - 20,
    stroke: '#333',
    'stroke-width': 2
  });
  dmasDiagram.appendChild(timeline);
  
  // DMA execution bars
  const dmas = [
    { name: 'Ethical DMA', result: stepResult.ethical_dma, color: '#4caf50', y: 50 },
    { name: 'Common Sense DMA', result: stepResult.common_sense_dma, color: '#2196f3', y: 90 },
    { name: 'Domain DMA', result: stepResult.domain_dma, color: '#ff9800', y: 130 }
  ];
  
  dmas.forEach(dma => {
    // DMA execution bar (shows they run in parallel)
    const barWidth = timelineWidth * 0.8; // Most of timeline since parallel
    const bar = createSvgElement('rect', {
      x: 50,
      y: dma.y,
      width: barWidth,
      height: 25,
      fill: dma.color,
      'fill-opacity': '0.7',
      stroke: dma.color
    });
    
    // DMA label
    const label = createSvgElement('text', {
      x: 45,
      y: dma.y + 17,
      'text-anchor': 'end',
      'font-size': '12px',
      'font-weight': 'bold'
    });
    label.textContent = dma.name;
    
    // Result indicator
    const resultIcon = createSvgElement('circle', {
      cx: 50 + barWidth + 15,
      cy: dma.y + 12.5,
      r: 8,
      fill: getResultColor(dma.result),
      stroke: '#333'
    });
    
    dmasDiagram.appendChild(bar);
    dmasDiagram.appendChild(label);
    dmasDiagram.appendChild(resultIcon);
  });
  
  // Parallel execution indicator
  const parallelLabel = createSvgElement('text', {
    x: 250,
    y: 35,
    'text-anchor': 'middle',
    'font-size': '14px',
    'font-weight': 'bold',
    fill: '#d32f2f'
  });
  parallelLabel.textContent = `Parallel Execution: ${stepResult.total_time_ms}ms`;
  dmasDiagram.appendChild(parallelLabel);
  
  // DMA Results Panel
  document.querySelector('#dma-results').innerHTML = `
    <div class="dma-results-grid">
      <div class="dma-result ethical">
        <h4>Ethical DMA</h4>
        <div class="result-status ${stepResult.ethical_dma.decision}">${stepResult.ethical_dma.decision}</div>
        <div class="reasoning">"${stepResult.ethical_dma.reasoning}"</div>
        <div class="alignment-check">${stepResult.ethical_dma.alignment_check}</div>
      </div>
      
      <div class="dma-result common-sense">
        <h4>Common Sense DMA</h4>
        <div class="plausibility-score">
          Plausibility: <span class="score">${stepResult.common_sense_dma.plausibility_score}</span>
        </div>
        <div class="reasoning">"${stepResult.common_sense_dma.reasoning}"</div>
        <div class="flags">
          ${stepResult.common_sense_dma.flags.map(flag => `<span class="flag">${flag}</span>`).join('')}
        </div>
      </div>
      
      <div class="dma-result domain">
        <h4>Domain DMA</h4>
        <div class="expertise-level">
          Expertise: <span class="score">${stepResult.domain_dma.domain_alignment}</span>
        </div>
        <div class="domain">Domain: ${stepResult.domain_dma.domain}</div>
        <div class="reasoning">"${stepResult.domain_dma.specialized_reasoning}"</div>
        <div class="flags">
          ${stepResult.domain_dma.flags.map(flag => `<span class="flag">${flag}</span>`).join('')}
        </div>
      </div>
    </div>
  `;
  
  // Performance metrics
  document.querySelector('#dma-performance').innerHTML = `
    <div class="performance-stats">
      <div class="stat-item">
        <label>Total Time (Parallel)</label>
        <span>${stepResult.total_time_ms}ms</span>
      </div>
      <div class="stat-item">
        <label>Longest Individual DMA</label>
        <span>${stepResult.longest_dma_time_ms}ms</span>
      </div>
      <div class="stat-item">
        <label>DMAs Executed</label>
        <span>${stepResult.dmas_executed.length}/3</span>
      </div>
      <div class="stat-item">
        <label>Failures</label>
        <span class="${stepResult.dma_failures.length > 0 ? 'error' : 'success'}">
          ${stepResult.dma_failures.length}
        </span>
      </div>
    </div>
  `;
  
  // Show failures if any
  if (stepResult.dma_failures.length > 0) {
    const failuresList = stepResult.dma_failures.map(failure => `
      <div class="failure-item">
        <span class="failure-dma">${failure.dma_name}</span>
        <span class="failure-reason">${failure.error}</span>
      </div>
    `).join('');
    
    document.querySelector('#dma-failures').innerHTML = `
      <h4>DMA Failures</h4>
      <div class="failures-list">${failuresList}</div>
    `;
    document.querySelector('#dma-failures').style.display = 'block';
  }
}

function getResultColor(dmaResult: any): string {
  if (dmaResult.decision === 'approve' || dmaResult.plausibility_score > 0.7) {
    return '#4caf50';
  } else if (dmaResult.decision === 'deny' || dmaResult.plausibility_score < 0.3) {
    return '#f44336';
  } else {
    return '#ff9800';
  }
}
```

**Demo Value**: This is the core of CIRIS's ethical reasoning system - showing how three independent perspectives (ethical principles, common sense, domain expertise) are evaluated in parallel. This demonstrates the multi-faceted approach to decision-making that embodies all six core principles simultaneously, with complete transparency into the reasoning process.

---

### Step 6: PERFORM_ASPDMA
**Context**: Action Selection through Principled Decision-Making Algorithm - the LLM analyzes context and DMA results to select appropriate actions.

**Data Available** (`StepResultPerformASPDMA`):
- `prompt_text`: Full prompt sent to LLM
- `llm_model`: Model used for action selection
- `raw_response`: Complete LLM response
- `aspdma_result`: Parsed action selection result
  - `selected_action`: Chosen action type
  - `action_parameters`: Parameters for the action
  - `reasoning`: LLM's reasoning process
  - `confidence_level`: How certain the LLM is
- `tokens_used`: Resource consumption
- `retry_count`: Number of attempts needed

**UI Enhancements**:
```typescript
function updatePerformASPDMAVisualization(stepResult: StepResultPerformASPDMA) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-perform-aspdma').classList.add('active-step');
  
  // Create ASPDMA process diagram
  const aspdmaDiagram = document.querySelector('#aspdma-process-diagram');
  aspdmaDiagram.innerHTML = '';
  
  // Input components flow
  const components = [
    { name: 'Context', x: 50, y: 50, color: '#3f51b5' },
    { name: 'DMA Results', x: 50, y: 100, color: '#4caf50' },
    { name: 'Constraints', x: 50, y: 150, color: '#f44336' }
  ];
  
  // LLM processing box
  const llmBox = createSvgElement('rect', {
    x: 200, y: 75,
    width: 150, height: 100,
    fill: '#fff3e0',
    stroke: '#ff9800',
    'stroke-width': 3,
    rx: 10
  });
  
  const llmLabel = createSvgElement('text', {
    x: 275, y: 110,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '14px'
  });
  llmLabel.textContent = stepResult.llm_model;
  
  const llmSubLabel = createSvgElement('text', {
    x: 275, y: 130,
    'text-anchor': 'middle',
    'font-size': '12px'
  });
  llmSubLabel.textContent = 'ASPDMA Processing';
  
  const llmTokens = createSvgElement('text', {
    x: 275, y: 150,
    'text-anchor': 'middle',
    'font-size': '10px',
    fill: '#666'
  });
  llmTokens.textContent = `${stepResult.tokens_used} tokens`;
  
  aspdmaDiagram.appendChild(llmBox);
  aspdmaDiagram.appendChild(llmLabel);
  aspdmaDiagram.appendChild(llmSubLabel);
  aspdmaDiagram.appendChild(llmTokens);
  
  // Input arrows
  components.forEach(component => {
    const inputBox = createSvgElement('rect', {
      x: component.x, y: component.y,
      width: 100, height: 30,
      fill: component.color,
      'fill-opacity': '0.8',
      rx: 5
    });
    
    const inputLabel = createSvgElement('text', {
      x: component.x + 50, y: component.y + 20,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
      fill: 'white',
      'font-weight': 'bold',
      'font-size': '12px'
    });
    inputLabel.textContent = component.name;
    
    const arrow = createSvgElement('line', {
      x1: component.x + 100,
      y1: component.y + 15,
      x2: 190,
      y2: 125,
      stroke: component.color,
      'stroke-width': 2,
      'marker-end': 'url(#arrowhead)'
    });
    
    aspdmaDiagram.appendChild(inputBox);
    aspdmaDiagram.appendChild(inputLabel);
    aspdmaDiagram.appendChild(arrow);
  });
  
  // Output action
  const actionBox = createSvgElement('rect', {
    x: 400, y: 100,
    width: 150, height: 50,
    fill: '#e8f5e8',
    stroke: '#4caf50',
    'stroke-width': 3,
    rx: 5
  });
  
  const actionLabel = createSvgElement('text', {
    x: 475, y: 120,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px'
  });
  actionLabel.textContent = stepResult.aspdma_result.selected_action;
  
  const confidenceLabel = createSvgElement('text', {
    x: 475, y: 135,
    'text-anchor': 'middle',
    'font-size': '10px',
    fill: '#666'
  });
  confidenceLabel.textContent = `Confidence: ${stepResult.aspdma_result.confidence_level}`;
  
  // Output arrow
  const outputArrow = createSvgElement('line', {
    x1: 350, y1: 125,
    x2: 390, y2: 125,
    stroke: '#4caf50',
    'stroke-width': 3,
    'marker-end': 'url(#arrowhead)'
  });
  
  aspdmaDiagram.appendChild(actionBox);
  aspdmaDiagram.appendChild(actionLabel);
  aspdmaDiagram.appendChild(confidenceLabel);
  aspdmaDiagram.appendChild(outputArrow);
  
  // Action Selection Results Panel
  document.querySelector('#aspdma-results').innerHTML = `
    <div class="aspdma-result-card">
      <div class="result-header">
        <h4>Selected Action</h4>
        <div class="confidence-meter">
          <div class="confidence-bar" style="width: ${stepResult.aspdma_result.confidence_level * 100}%"></div>
          <span class="confidence-text">${(stepResult.aspdma_result.confidence_level * 100).toFixed(1)}%</span>
        </div>
      </div>
      
      <div class="action-details">
        <div class="action-name">${stepResult.aspdma_result.selected_action}</div>
        <div class="action-parameters">
          ${Object.entries(stepResult.aspdma_result.action_parameters).map(([key, value]) => 
            `<div class="parameter"><span class="key">${key}:</span> <span class="value">${JSON.stringify(value)}</span></div>`
          ).join('')}
        </div>
      </div>
      
      <div class="reasoning-section">
        <h5>LLM Reasoning</h5>
        <div class="reasoning-text">"${stepResult.aspdma_result.reasoning}"</div>
      </div>
    </div>
  `;
  
  // LLM Interaction Details Panel (for transparency)
  document.querySelector('#llm-interaction').innerHTML = `
    <div class="llm-details">
      <div class="prompt-section">
        <h4>Full Prompt <button onclick="togglePrompt()" class="toggle-btn">Show/Hide</button></h4>
        <div id="full-prompt" class="prompt-text" style="display: none;">
          <pre>${stepResult.prompt_text}</pre>
        </div>
      </div>
      
      <div class="response-section">
        <h4>Raw LLM Response <button onclick="toggleResponse()" class="toggle-btn">Show/Hide</button></h4>
        <div id="raw-response" class="response-text" style="display: none;">
          <pre>${stepResult.raw_response}</pre>
        </div>
      </div>
      
      <div class="metrics-section">
        <div class="metric-item">
          <label>Model</label>
          <span>${stepResult.llm_model}</span>
        </div>
        <div class="metric-item">
          <label>Tokens Used</label>
          <span>${stepResult.tokens_used}</span>
        </div>
        <div class="metric-item">
          <label>Retry Count</label>
          <span>${stepResult.retry_count}</span>
        </div>
      </div>
    </div>
  `;
}

// Toggle functions for transparency
function togglePrompt() {
  const promptDiv = document.getElementById('full-prompt');
  promptDiv.style.display = promptDiv.style.display === 'none' ? 'block' : 'none';
}

function toggleResponse() {
  const responseDiv = document.getElementById('raw-response');
  responseDiv.style.display = responseDiv.style.display === 'none' ? 'block' : 'none';
}
```

**Demo Value**: Shows CIRIS's transparent LLM interaction - the complete prompt, raw response, and parsed reasoning are available for inspection. This demonstrates how the agent uses AI assistance while maintaining full auditability and transparency, embodying the integrity and fidelity principles.

---

### Step 7: CONSCIENCE_EXECUTION
**Context**: Multiple conscience mechanisms evaluate the proposed action for ethical violations and safety concerns.

**Data Available** (`StepResultConscienceExecution`):
- `aspdma_result`: Action being evaluated
- `conscience_evaluations`: Results from all conscience checks
- `all_passed`: Whether all consciences approved the action
- `failures`: Names of failed consciences
- `override_required`: Whether human override is needed
- `longest_conscience_time_ms`: Performance analysis
- `total_time_ms`: Total conscience processing time

**UI Enhancements**:
```typescript
function updateConscienceExecutionVisualization(stepResult: StepResultConscienceExecution) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-conscience-execution').classList.add('active-step');
  
  // Create conscience evaluation matrix
  const conscienceMatrix = document.querySelector('#conscience-matrix');
  conscienceMatrix.innerHTML = '';
  
  const matrixWidth = 500;
  const matrixHeight = 300;
  
  // Action being evaluated (center)
  const actionRect = createSvgElement('rect', {
    x: matrixWidth/2 - 75, y: matrixHeight/2 - 25,
    width: 150, height: 50,
    fill: '#fff9c4',
    stroke: '#f57f17',
    'stroke-width': 3,
    rx: 5
  });
  
  const actionLabel = createSvgElement('text', {
    x: matrixWidth/2, y: matrixHeight/2 - 5,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px'
  });
  actionLabel.textContent = stepResult.aspdma_result.selected_action;
  
  const actionSubLabel = createSvgElement('text', {
    x: matrixWidth/2, y: matrixHeight/2 + 10,
    'text-anchor': 'middle',
    'font-size': '10px',
    fill: '#666'
  });
  actionSubLabel.textContent = 'Under Evaluation';
  
  conscienceMatrix.appendChild(actionRect);
  conscienceMatrix.appendChild(actionLabel);
  conscienceMatrix.appendChild(actionSubLabel);
  
  // Conscience evaluations around the action
  stepResult.conscience_evaluations.forEach((evaluation, index) => {
    const angle = (index / stepResult.conscience_evaluations.length) * 2 * Math.PI;
    const radius = 120;
    const x = matrixWidth/2 + Math.cos(angle) * radius;
    const y = matrixHeight/2 + Math.sin(angle) * radius;
    
    // Conscience node
    const conscienceColor = evaluation.passed ? '#4caf50' : '#f44336';
    const conscienceNode = createSvgElement('circle', {
      cx: x, cy: y,
      r: 30,
      fill: conscienceColor,
      stroke: 'white',
      'stroke-width': 3
    });
    
    // Conscience label
    const conscienceLabel = createSvgElement('text', {
      x: x, y: y - 5,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
      'font-size': '10px',
      'font-weight': 'bold',
      fill: 'white'
    });
    conscienceLabel.textContent = evaluation.conscience_name;
    
    const statusLabel = createSvgElement('text', {
      x: x, y: y + 8,
      'text-anchor': 'middle',
      'font-size': '8px',
      fill: 'white'
    });
    statusLabel.textContent = evaluation.passed ? 'PASS' : 'FAIL';
    
    // Connection line with color based on result
    const connectionLine = createSvgElement('line', {
      x1: matrixWidth/2 + Math.cos(angle) * 75,
      y1: matrixHeight/2 + Math.sin(angle) * 25,
      x2: x - Math.cos(angle) * 30,
      y2: y - Math.sin(angle) * 30,
      stroke: conscienceColor,
      'stroke-width': 3,
      'stroke-dasharray': evaluation.passed ? 'none' : '5,5'
    });
    
    conscienceMatrix.appendChild(connectionLine);
    conscienceMatrix.appendChild(conscienceNode);
    conscienceMatrix.appendChild(conscienceLabel);
    conscienceMatrix.appendChild(statusLabel);
  });
  
  // Overall result indicator
  const overallResult = createSvgElement('text', {
    x: matrixWidth/2, y: 30,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '16px',
    fill: stepResult.all_passed ? '#4caf50' : '#f44336'
  });
  overallResult.textContent = stepResult.all_passed ? 'ALL CONSCIENCES PASS' : 'CONSCIENCE FAILURES DETECTED';
  conscienceMatrix.appendChild(overallResult);
  
  // Conscience Results Panel
  const conscienceResults = stepResult.conscience_evaluations.map(evaluation => `
    <div class="conscience-result ${evaluation.passed ? 'passed' : 'failed'}">
      <div class="conscience-header">
        <h4>${evaluation.conscience_name}</h4>
        <div class="status-badge ${evaluation.passed ? 'pass' : 'fail'}">
          ${evaluation.passed ? 'PASS' : 'FAIL'}
        </div>
      </div>
      <div class="conscience-reasoning">
        <strong>Reasoning:</strong> "${evaluation.reasoning}"
      </div>
      <div class="conscience-recommendations">
        <strong>Recommendations:</strong>
        ${evaluation.recommendations.map(rec => `<div class="recommendation">• ${rec}</div>`).join('')}
      </div>
      ${!evaluation.passed ? `
        <div class="conscience-violations">
          <strong>Violations:</strong>
          ${evaluation.violations?.map(violation => `<div class="violation">⚠ ${violation}</div>`).join('') || 'General ethical concern'}
        </div>
      ` : ''}
    </div>
  `).join('');
  
  document.querySelector('#conscience-results').innerHTML = conscienceResults;
  
  // Conscience Performance Stats
  document.querySelector('#conscience-performance').innerHTML = `
    <div class="conscience-stats">
      <div class="stat-item">
        <label>Total Processing Time</label>
        <span>${stepResult.total_time_ms}ms</span>
      </div>
      <div class="stat-item">
        <label>Longest Individual Check</label>
        <span>${stepResult.longest_conscience_time_ms}ms</span>
      </div>
      <div class="stat-item">
        <label>Consciences Evaluated</label>
        <span>${stepResult.conscience_evaluations.length}</span>
      </div>
      <div class="stat-item">
        <label>Override Required</label>
        <span class="${stepResult.override_required ? 'warning' : 'success'}">
          ${stepResult.override_required ? 'YES' : 'NO'}
        </span>
      </div>
    </div>
  `;
  
  // Show failures summary if any
  if (stepResult.failures.length > 0) {
    document.querySelector('#conscience-failures').innerHTML = `
      <div class="failures-summary">
        <h4>Failed Consciences (${stepResult.failures.length})</h4>
        <div class="failed-list">
          ${stepResult.failures.map(failure => `<span class="failed-conscience">${failure}</span>`).join('')}
        </div>
        ${stepResult.override_required ? `
          <div class="override-notice">
            ⚠ Human override required - Action blocked pending review
          </div>
        ` : ''}
      </div>
    `;
    document.querySelector('#conscience-failures').style.display = 'block';
  } else {
    document.querySelector('#conscience-failures').style.display = 'none';
  }
}
```

**Demo Value**: Critical demonstration of CIRIS's safety mechanisms - shows how multiple independent conscience systems evaluate every action for ethical violations. This embodies the non-maleficence principle and demonstrates the agent's commitment to avoiding harm through rigorous safety checks.

---

### Step 8: RECURSIVE_ASPDMA *(Conditional)*
**Context**: If conscience checks failed, the system recursively refines the action selection using feedback from the failed consciences.

**Data Available** (`StepResultRecursiveASPDMA`):
- `original_action`: Action that failed conscience checks
- `conscience_feedback`: Why the action failed
- `recursion_count`: Number of retry attempts
- `retry_prompt`: Modified prompt incorporating feedback
- `raw_response`: New LLM response
- `new_aspdma_result`: Refined action selection

**UI Enhancements**:
```typescript
function updateRecursiveASPDMAVisualization(stepResult: StepResultRecursiveASPDMA) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-recursive-aspdma').classList.add('active-step');
  
  // Create recursive refinement flow
  const recursiveFlow = document.querySelector('#recursive-aspdma-flow');
  recursiveFlow.innerHTML = '';
  
  const flowWidth = 600;
  const flowHeight = 250;
  
  // Original failed action
  const originalAction = createSvgElement('rect', {
    x: 50, y: 50,
    width: 120, height: 40,
    fill: '#ffebee',
    stroke: '#f44336',
    'stroke-width': 2,
    rx: 5
  });
  
  const originalLabel = createSvgElement('text', {
    x: 110, y: 65,
    'text-anchor': 'middle',
    'font-size': '10px',
    'font-weight': 'bold'
  });
  originalLabel.textContent = 'Original Action';
  
  const originalActionName = createSvgElement('text', {
    x: 110, y: 80,
    'text-anchor': 'middle',
    'font-size': '9px'
  });
  originalActionName.textContent = stepResult.original_action;
  
  recursiveFlow.appendChild(originalAction);
  recursiveFlow.appendChild(originalLabel);
  recursiveFlow.appendChild(originalActionName);
  
  // Feedback incorporation
  const feedbackBox = createSvgElement('rect', {
    x: 220, y: 30,
    width: 160, height: 80,
    fill: '#fff3e0',
    stroke: '#ff9800',
    'stroke-width': 2,
    rx: 5
  });
  
  const feedbackLabel = createSvgElement('text', {
    x: 300, y: 45,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px'
  });
  feedbackLabel.textContent = 'Feedback Integration';
  
  const recursionLabel = createSvgElement('text', {
    x: 300, y: 65,
    'text-anchor': 'middle',
    'font-size': '10px'
  });
  recursionLabel.textContent = `Attempt #${stepResult.recursion_count}`;
  
  const feedbackText = createSvgElement('foreignObject', {
    x: 225, y: 70,
    width: 150, height: 35
  });
  feedbackText.innerHTML = `
    <div style="font-size: 8px; padding: 2px; overflow: hidden;">
      "${stepResult.conscience_feedback.substring(0, 60)}..."
    </div>
  `;
  
  recursiveFlow.appendChild(feedbackBox);
  recursiveFlow.appendChild(feedbackLabel);
  recursiveFlow.appendChild(recursionLabel);
  recursiveFlow.appendChild(feedbackText);
  
  // Refined action
  const refinedAction = createSvgElement('rect', {
    x: 430, y: 50,
    width: 120, height: 40,
    fill: stepResult.new_aspdma_result ? '#e8f5e8' : '#ffebee',
    stroke: stepResult.new_aspdma_result ? '#4caf50' : '#f44336',
    'stroke-width': 2,
    rx: 5
  });
  
  const refinedLabel = createSvgElement('text', {
    x: 490, y: 65,
    'text-anchor': 'middle',
    'font-size': '10px',
    'font-weight': 'bold'
  });
  refinedLabel.textContent = 'Refined Action';
  
  const refinedActionName = createSvgElement('text', {
    x: 490, y: 80,
    'text-anchor': 'middle',
    'font-size': '9px'
  });
  refinedActionName.textContent = stepResult.new_aspdma_result?.selected_action || 'Failed';
  
  recursiveFlow.appendChild(refinedAction);
  recursiveFlow.appendChild(refinedLabel);
  recursiveFlow.appendChild(refinedActionName);
  
  // Flow arrows
  const arrow1 = createSvgElement('line', {
    x1: 170, y1: 70,
    x2: 210, y2: 70,
    stroke: '#666',
    'stroke-width': 2,
    'marker-end': 'url(#arrowhead)'
  });
  
  const arrow2 = createSvgElement('line', {
    x1: 380, y1: 70,
    x2: 420, y2: 70,
    stroke: '#666',
    'stroke-width': 2,
    'marker-end': 'url(#arrowhead)'
  });
  
  recursiveFlow.appendChild(arrow1);
  recursiveFlow.appendChild(arrow2);
  
  // Learning cycle indicator
  const cycleArc = createSvgElement('path', {
    d: `M 300 120 Q 110 150 110 30`,
    fill: 'none',
    stroke: '#9c27b0',
    'stroke-width': 2,
    'stroke-dasharray': '5,5',
    'marker-end': 'url(#arrowhead)'
  });
  
  const cycleLabel = createSvgElement('text', {
    x: 200, y: 170,
    'text-anchor': 'middle',
    'font-size': '10px',
    fill: '#9c27b0',
    'font-weight': 'bold'
  });
  cycleLabel.textContent = 'Learning Cycle';
  
  recursiveFlow.appendChild(cycleArc);
  recursiveFlow.appendChild(cycleLabel);
  
  // Recursive ASPDMA Results Panel
  document.querySelector('#recursive-aspdma-results').innerHTML = `
    <div class="recursive-results">
      <div class="recursion-info">
        <h4>Recursive Refinement - Attempt ${stepResult.recursion_count}</h4>
        <div class="original-failure">
          <strong>Original Action:</strong> ${stepResult.original_action}
          <strong>Failed Because:</strong> "${stepResult.conscience_feedback}"
        </div>
      </div>
      
      ${stepResult.new_aspdma_result ? `
        <div class="refined-action">
          <h5>Refined Action</h5>
          <div class="action-name">${stepResult.new_aspdma_result.selected_action}</div>
          <div class="confidence">Confidence: ${(stepResult.new_aspdma_result.confidence_level * 100).toFixed(1)}%</div>
          <div class="reasoning">"${stepResult.new_aspdma_result.reasoning}"</div>
        </div>
      ` : `
        <div class="refinement-failed">
          <h5>Refinement Failed</h5>
          <p>Unable to generate acceptable alternative action.</p>
        </div>
      `}
      
      <div class="prompt-comparison">
        <h5>Prompt Modifications <button onclick="togglePromptComparison()" class="toggle-btn">Show/Hide</button></h5>
        <div id="prompt-comparison" style="display: none;">
          <div class="modified-prompt">
            <strong>Retry Prompt:</strong>
            <pre>${stepResult.retry_prompt}</pre>
          </div>
          <div class="llm-response">
            <strong>LLM Response:</strong>
            <pre>${stepResult.raw_response}</pre>
          </div>
        </div>
      </div>
    </div>
  `;
}

function togglePromptComparison() {
  const comparisonDiv = document.getElementById('prompt-comparison');
  comparisonDiv.style.display = comparisonDiv.style.display === 'none' ? 'block' : 'none';
}
```

**Demo Value**: Shows CIRIS's learning and adaptation capabilities - when an action fails ethical review, the system doesn't give up but learns from the feedback and tries to find a better solution. This demonstrates the agent's commitment to continuous improvement and ethical growth.

---

### Step 9: RECURSIVE_CONSCIENCE *(Conditional)*
**Context**: The refined action (if successfully generated) goes through another round of conscience evaluation to ensure the refinement resolved the ethical concerns.

**Data Available** (`StepResultRecursiveConscience`):
- `is_recursive`: Always true for this step
- `recursion_count`: Recursion depth
- `aspdma_result`: Refined action being re-evaluated
- `conscience_evaluations`: Fresh evaluation results
- `all_passed`: Whether the refined action passes
- `failures`: Any remaining failed consciences
- `final_override_to_ponder`: Whether to fall back to PONDER action

**UI Enhancements**:
```typescript
function updateRecursiveConscienceVisualization(stepResult: StepResultRecursiveConscience) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-recursive-conscience').classList.add('active-step');
  
  // Create recursive conscience evaluation flow
  const recursiveConscienceFlow = document.querySelector('#recursive-conscience-flow');
  recursiveConscienceFlow.innerHTML = '';
  
  // Recursive indicator banner
  const recursiveBanner = createSvgElement('rect', {
    x: 0, y: 0,
    width: 600, height: 30,
    fill: '#f3e5f5',
    stroke: '#9c27b0',
    'stroke-width': 2
  });
  
  const recursiveBannerText = createSvgElement('text', {
    x: 300, y: 20,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '14px',
    fill: '#9c27b0'
  });
  recursiveBannerText.textContent = `RECURSIVE CONSCIENCE EVALUATION - Depth ${stepResult.recursion_count}`;
  
  recursiveConscienceFlow.appendChild(recursiveBanner);
  recursiveConscienceFlow.appendChild(recursiveBannerText);
  
  // Refined action under re-evaluation
  const refinedActionRect = createSvgElement('rect', {
    x: 225, y: 80,
    width: 150, height: 50,
    fill: '#e1f5fe',
    stroke: '#0277bd',
    'stroke-width': 3,
    rx: 5
  });
  
  const refinedActionLabel = createSvgElement('text', {
    x: 300, y: 100,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px'
  });
  refinedActionLabel.textContent = 'Refined Action';
  
  const refinedActionName = createSvgElement('text', {
    x: 300, y: 115,
    'text-anchor': 'middle',
    'font-size': '10px'
  });
  refinedActionName.textContent = stepResult.aspdma_result?.selected_action || 'Unknown';
  
  recursiveConscienceFlow.appendChild(refinedActionRect);
  recursiveConscienceFlow.appendChild(refinedActionLabel);
  recursiveConscienceFlow.appendChild(refinedActionName);
  
  // Conscience re-evaluation results
  const conscienceStartY = 160;
  const conscienceSpacing = 80;
  
  stepResult.conscience_evaluations.forEach((evaluation, index) => {
    const x = 50 + (index * conscienceSpacing);
    const y = conscienceStartY;
    
    // Previous result (implied failed, now re-checking)
    const prevResult = createSvgElement('circle', {
      cx: x, cy: y - 20,
      r: 12,
      fill: '#ffcdd2',
      stroke: '#f44336',
      'stroke-width': 2
    });
    
    const prevLabel = createSvgElement('text', {
      x: x, y: y - 16,
      'text-anchor': 'middle',
      'font-size': '8px',
      'font-weight': 'bold'
    });
    prevLabel.textContent = 'PREV';
    
    // Arrow showing re-evaluation
    const reevalArrow = createSvgElement('line', {
      x1: x, y1: y - 5,
      x2: x, y2: y + 15,
      stroke: '#9c27b0',
      'stroke-width': 2,
      'marker-end': 'url(#arrowhead)'
    });
    
    // Current result
    const currentResult = createSvgElement('circle', {
      cx: x, cy: y + 30,
      r: 15,
      fill: evaluation.passed ? '#4caf50' : '#f44336',
      stroke: 'white',
      'stroke-width': 2
    });
    
    const currentLabel = createSvgElement('text', {
      x: x, y: y + 25,
      'text-anchor': 'middle',
      'font-size': '8px',
      'font-weight': 'bold',
      fill: 'white'
    });
    currentLabel.textContent = evaluation.conscience_name.substring(0, 6);
    
    const currentStatus = createSvgElement('text', {
      x: x, y: y + 38,
      'text-anchor': 'middle',
      'font-size': '7px',
      fill: 'white'
    });
    currentStatus.textContent = evaluation.passed ? 'PASS' : 'FAIL';
    
    recursiveConscienceFlow.appendChild(prevResult);
    recursiveConscienceFlow.appendChild(prevLabel);
    recursiveConscienceFlow.appendChild(reevalArrow);
    recursiveConscienceFlow.appendChild(currentResult);
    recursiveConscienceFlow.appendChild(currentLabel);
    recursiveConscienceFlow.appendChild(currentStatus);
  });
  
  // Overall recursive result
  const overallResultY = conscienceStartY + 80;
  const overallColor = stepResult.all_passed ? '#4caf50' : '#f44336';
  
  const overallResultRect = createSvgElement('rect', {
    x: 200, y: overallResultY,
    width: 200, height: 40,
    fill: overallColor,
    'fill-opacity': '0.8',
    rx: 5
  });
  
  const overallResultText = createSvgElement('text', {
    x: 300, y: overallResultY + 25,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '14px',
    fill: 'white'
  });
  overallResultText.textContent = stepResult.all_passed ? 'RECURSIVE VALIDATION PASSED' : 'STILL FAILING - OVERRIDE NEEDED';
  
  recursiveConscienceFlow.appendChild(overallResultRect);
  recursiveConscienceFlow.appendChild(overallResultText);
  
  // Recursive Conscience Results Panel
  document.querySelector('#recursive-conscience-results').innerHTML = `
    <div class="recursive-conscience-summary">
      <div class="recursion-header">
        <h4>Recursive Conscience Evaluation</h4>
        <div class="recursion-depth">Depth: ${stepResult.recursion_count}</div>
      </div>
      
      <div class="re-evaluation-results">
        <div class="overall-status ${stepResult.all_passed ? 'success' : 'failure'}">
          ${stepResult.all_passed ? '✅ Refined Action Approved' : '❌ Refined Action Still Fails'}
        </div>
        
        <div class="conscience-details">
          ${stepResult.conscience_evaluations.map(evaluation => `
            <div class="recursive-conscience-item ${evaluation.passed ? 'passed' : 'failed'}">
              <div class="conscience-name">${evaluation.conscience_name}</div>
              <div class="status-change">
                <span class="prev-status fail">PREV: FAIL</span>
                <span class="arrow">→</span>
                <span class="new-status ${evaluation.passed ? 'pass' : 'fail'}">
                  NOW: ${evaluation.passed ? 'PASS' : 'FAIL'}
                </span>
              </div>
              <div class="recursive-reasoning">"${evaluation.reasoning}"</div>
            </div>
          `).join('')}
        </div>
        
        ${!stepResult.all_passed ? `
          <div class="remaining-failures">
            <h5>Remaining Failures:</h5>
            ${stepResult.failures.map(failure => `<span class="failed-conscience">${failure}</span>`).join('')}
          </div>
        ` : ''}
        
        ${stepResult.final_override_to_ponder ? `
          <div class="ponder-override">
            ⚠ System falling back to PONDER action due to unresolvable ethical concerns
          </div>
        ` : ''}
      </div>
    </div>
  `;
}
```

**Demo Value**: Shows CIRIS's persistence in ethical reasoning - the system doesn't just try once to fix ethical violations but continues to verify that refinements actually resolve the concerns. This demonstrates thoroughness and commitment to the non-maleficence principle.

---

### Step 10: ACTION_SELECTION
**Context**: Final decision point where the definitive action to be executed is determined, whether from initial ASPDMA or recursive refinement.

**Data Available** (`StepResultActionSelection`):
- `final_action_result`: Definitive action to be taken (ActionSelectionDMAResult)
- `was_overridden`: Whether original choice was changed (bool)
- `override_reason`: Why it was changed (str)
- `recursion_performed`: Whether recursive refinement occurred
- `target_handler`: Which handler will execute this action (str)

**UI Enhancements**:
```typescript
function updateActionSelectionVisualization(stepResult: StepResultActionSelection) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-action-selection').classList.add('active-step');
  
  // Create decision finalization diagram
  const actionSelectionDiagram = document.querySelector('#action-selection-diagram');
  actionSelectionDiagram.innerHTML = '';
  
  const diagramWidth = 600;
  const diagramHeight = 300;
  
  // Decision process flow
  const processSteps = [
    { name: 'ASPDMA', x: 100, y: 100, completed: true },
    { name: 'Conscience', x: 200, y: 100, completed: true },
  ];
  
  if (stepResult.recursion_performed) {
    processSteps.push(
      { name: 'Recursive\nASPDMA', x: 300, y: 80, completed: true },
      { name: 'Recursive\nConscience', x: 400, y: 80, completed: true }
    );
  }
  
  // Final decision box
  const finalDecisionBox = createSvgElement('rect', {
    x: diagramWidth - 150, y: 120,
    width: 120, height: 60,
    fill: '#e8f5e8',
    stroke: '#2e7d32',
    'stroke-width': 4,
    rx: 10
  });
  
  const finalDecisionLabel = createSvgElement('text', {
    x: diagramWidth - 90, y: 140,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '14px',
    fill: '#2e7d32'
  });
  finalDecisionLabel.textContent = 'FINAL ACTION';
  
  const finalActionName = createSvgElement('text', {
    x: diagramWidth - 90, y: 160,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px'
  });
  finalActionName.textContent = stepResult.final_action_result.selected_action;
  
  const handlerName = createSvgElement('text', {
    x: diagramWidth - 90, y: 175,
    'text-anchor': 'middle',
    'font-size': '10px',
    fill: '#666'
  });
  handlerName.textContent = `→ ${stepResult.target_handler}`;
  
  actionSelectionDiagram.appendChild(finalDecisionBox);
  actionSelectionDiagram.appendChild(finalDecisionLabel);
  actionSelectionDiagram.appendChild(finalActionName);
  actionSelectionDiagram.appendChild(handlerName);
  
  // Draw process flow
  processSteps.forEach((step, index) => {
    const stepRect = createSvgElement('rect', {
      x: step.x - 40, y: step.y - 20,
      width: 80, height: 40,
      fill: '#e3f2fd',
      stroke: '#1976d2',
      'stroke-width': 2,
      rx: 5
    });
    
    const stepLabel = createSvgElement('text', {
      x: step.x, y: step.y,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
      'font-size': '10px',
      'font-weight': 'bold'
    });
    stepLabel.innerHTML = step.name.replace('\\n', '<tspan x="' + step.x + '" dy="12">') + '</tspan>';
    
    // Checkmark for completed steps
    const checkmark = createSvgElement('circle', {
      cx: step.x + 30, cy: step.y - 15,
      r: 8,
      fill: '#4caf50'
    });
    
    const checkText = createSvgElement('text', {
      x: step.x + 30, y: step.y - 10,
      'text-anchor': 'middle',
      'font-size': '10px',
      'font-weight': 'bold',
      fill: 'white'
    });
    checkText.textContent = '✓';
    
    actionSelectionDiagram.appendChild(stepRect);
    actionSelectionDiagram.appendChild(stepLabel);
    actionSelectionDiagram.appendChild(checkmark);
    actionSelectionDiagram.appendChild(checkText);
    
    // Flow arrows
    if (index < processSteps.length - 1) {
      const nextStep = processSteps[index + 1];
      const arrow = createSvgElement('line', {
        x1: step.x + 40, y1: step.y,
        x2: nextStep.x - 40, y2: nextStep.y,
        stroke: '#666',
        'stroke-width': 2,
        'marker-end': 'url(#arrowhead)'
      });
      actionSelectionDiagram.appendChild(arrow);
    }
  });
  
  // Final arrow to decision
  const lastStep = processSteps[processSteps.length - 1];
  const finalArrow = createSvgElement('line', {
    x1: lastStep.x + 40, y1: lastStep.y,
    x2: diagramWidth - 170, y2: 150,
    stroke: '#2e7d32',
    'stroke-width': 4,
    'marker-end': 'url(#arrowhead)'
  });
  actionSelectionDiagram.appendChild(finalArrow);
  
  // Override indicator if applicable
  if (stepResult.was_overridden) {
    const overrideIndicator = createSvgElement('rect', {
      x: 50, y: 20,
      width: 200, height: 40,
      fill: '#fff3e0',
      stroke: '#ff9800',
      'stroke-width': 3,
      rx: 5
    });
    
    const overrideLabel = createSvgElement('text', {
      x: 150, y: 35,
      'text-anchor': 'middle',
      'font-weight': 'bold',
      'font-size': '12px',
      fill: '#e65100'
    });
    overrideLabel.textContent = '⚠ ACTION WAS OVERRIDDEN';
    
    const overrideReason = createSvgElement('text', {
      x: 150, y: 50,
      'text-anchor': 'middle',
      'font-size': '10px',
      fill: '#666'
    });
    overrideReason.textContent = stepResult.override_reason;
    
    actionSelectionDiagram.appendChild(overrideIndicator);
    actionSelectionDiagram.appendChild(overrideLabel);
    actionSelectionDiagram.appendChild(overrideReason);
  }
  
  // Action Selection Results Panel
  document.querySelector('#action-selection-results').innerHTML = `
    <div class="final-action-card">
      <div class="action-header">
        <h4>Final Action Decision</h4>
        <div class="decision-status">
          ${stepResult.was_overridden ? 
            `<span class="override-badge">OVERRIDDEN</span>` : 
            `<span class="approved-badge">APPROVED</span>`
          }
        </div>
      </div>
      
      <div class="final-action-details">
        <div class="action-info">
          <div class="action-name">${stepResult.final_action_result.selected_action}</div>
          <div class="action-confidence">
            Confidence: ${(stepResult.final_action_result.confidence_level * 100).toFixed(1)}%
          </div>
          <div class="target-handler">Handler: ${stepResult.target_handler}</div>
        </div>
        
        <div class="action-parameters">
          <h5>Action Parameters</h5>
          <div class="parameters-grid">
            ${Object.entries(stepResult.final_action_result.action_parameters).map(([key, value]) => `
              <div class="parameter-item">
                <span class="param-key">${key}:</span>
                <span class="param-value">${JSON.stringify(value)}</span>
              </div>
            `).join('')}
          </div>
        </div>
        
        <div class="final-reasoning">
          <h5>Final Reasoning</h5>
          <div class="reasoning-text">"${stepResult.final_action_result.reasoning}"</div>
        </div>
      </div>
      
      <div class="decision-path">
        <h5>Decision Path</h5>
        <div class="path-summary">
          <div class="path-step">
            <span class="step-name">Initial ASPDMA</span>
            <span class="step-status">✓ Completed</span>
          </div>
          <div class="path-step">
            <span class="step-name">Conscience Evaluation</span>
            <span class="step-status">✓ Completed</span>
          </div>
          ${stepResult.recursion_performed ? `
            <div class="path-step recursive">
              <span class="step-name">Recursive Refinement</span>
              <span class="step-status">✓ Applied</span>
            </div>
          ` : ''}
          ${stepResult.was_overridden ? `
            <div class="path-step override">
              <span class="step-name">Override Applied</span>
              <span class="step-reason">${stepResult.override_reason}</span>
            </div>
          ` : ''}
          <div class="path-step final">
            <span class="step-name">Action Selection</span>
            <span class="step-status">✓ Finalized</span>
          </div>
        </div>
      </div>
    </div>
  `;
  
  // Ethical Process Summary
  document.querySelector('#ethical-process-summary').innerHTML = `
    <div class="process-summary">
      <h4>Ethical Decision Summary</h4>
      <div class="summary-metrics">
        <div class="metric-item">
          <label>Process Type</label>
          <span>${stepResult.recursion_performed ? 'Recursive' : 'Standard'}</span>
        </div>
        <div class="metric-item">
          <label>Override Applied</label>
          <span class="${stepResult.was_overridden ? 'yes' : 'no'}">
            ${stepResult.was_overridden ? 'Yes' : 'No'}
          </span>
        </div>
        <div class="metric-item">
          <label>Final Confidence</label>
          <span>${(stepResult.final_action_result.confidence_level * 100).toFixed(1)}%</span>
        </div>
        <div class="metric-item">
          <label>Target Handler</label>
          <span>${stepResult.target_handler}</span>
        </div>
      </div>
      
      <div class="ethical-principles-met">
        <h5>CIRIS Principles Demonstrated</h5>
        <div class="principles-list">
          <div class="principle-item">
            <span class="principle">Integrity</span>
            <span class="evidence">Complete reasoning transparency and auditability</span>
          </div>
          <div class="principle-item">
            <span class="principle">Non-maleficence</span>
            <span class="evidence">Multi-layer conscience screening for harm prevention</span>
          </div>
          <div class="principle-item">
            <span class="principle">Beneficence</span>
            <span class="evidence">Action selection optimized for positive outcomes</span>
          </div>
          <div class="principle-item">
            <span class="principle">Respect for Autonomy</span>
            <span class="evidence">Human override capability maintained throughout</span>
          </div>
          ${stepResult.recursion_performed ? `
            <div class="principle-item">
              <span class="principle">Adaptive Coherence</span>
              <span class="evidence">Recursive refinement demonstrates continuous improvement</span>
            </div>
          ` : ''}
        </div>
      </div>
    </div>
  `;
}
```

**Demo Value**: This is the culmination of CIRIS's ethical reasoning process - showing how all previous steps (DMA evaluation, conscience checks, potential recursive refinement) lead to a final, principled action decision. Demonstrates complete ethical reasoning chain with full auditability and respect for human oversight through override capabilities.

---

### Step 11: HANDLER_START
**Context**: Transition from reasoning to execution - the selected action handler begins execution with prepared context and parameters.

**Data Available** (`StepResultHandlerStart`):
- `handler_name`: Handler being executed (str)
- `action_type`: Type of action (str)
- `action_parameters`: Full action parameters (Dict[str, Any])
- `handler_context`: Context prepared for handler (Dict[str, Any])
- `expected_bus_operations`: Predicted bus calls (str[])

**UI Enhancements**:
```typescript
function updateHandlerStartVisualization(stepResult: StepResultHandlerStart) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-handler-start').classList.add('active-step');
  
  // Create handler execution initiation diagram
  const handlerStartDiagram = document.querySelector('#handler-start-diagram');
  handlerStartDiagram.innerHTML = '';
  
  // Reasoning to execution transition
  const transitionWidth = 600;
  const transitionHeight = 250;
  
  // Reasoning phase (completed)
  const reasoningPhase = createSvgElement('rect', {
    x: 50, y: 50,
    width: 200, height: 80,
    fill: '#e8eaf6',
    stroke: '#3f51b5',
    'stroke-width': 2,
    rx: 5,
    'stroke-dasharray': '5,5'
  });
  
  const reasoningLabel = createSvgElement('text', {
    x: 150, y: 75,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '14px',
    fill: '#3f51b5'
  });
  reasoningLabel.textContent = 'ETHICAL REASONING';
  
  const reasoningSubLabel = createSvgElement('text', {
    x: 150, y: 95,
    'text-anchor': 'middle',
    'font-size': '12px',
    fill: '#666'
  });
  reasoningSubLabel.textContent = 'Completed ✓';
  
  const completedSteps = createSvgElement('text', {
    x: 150, y: 115,
    'text-anchor': 'middle',
    'font-size': '10px',
    fill: '#666'
  });
  completedSteps.textContent = 'DMA → Conscience → Selection';
  
  handlerStartDiagram.appendChild(reasoningPhase);
  handlerStartDiagram.appendChild(reasoningLabel);
  handlerStartDiagram.appendChild(reasoningSubLabel);
  handlerStartDiagram.appendChild(completedSteps);
  
  // Transition arrow
  const transitionArrow = createSvgElement('line', {
    x1: 260, y1: 90,
    x2: 320, y2: 90,
    stroke: '#ff9800',
    'stroke-width': 4,
    'marker-end': 'url(#arrowhead)'
  });
  
  const transitionLabel = createSvgElement('text', {
    x: 290, y: 75,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px',
    fill: '#ff9800'
  });
  transitionLabel.textContent = 'TRANSITION';
  
  handlerStartDiagram.appendChild(transitionArrow);
  handlerStartDiagram.appendChild(transitionLabel);
  
  // Execution phase (starting)
  const executionPhase = createSvgElement('rect', {
    x: 350, y: 50,
    width: 200, height: 80,
    fill: '#e8f5e8',
    stroke: '#4caf50',
    'stroke-width': 3,
    rx: 5
  });
  
  const executionLabel = createSvgElement('text', {
    x: 450, y: 75,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '14px',
    fill: '#2e7d32'
  });
  executionLabel.textContent = 'ACTION EXECUTION';
  
  const executionSubLabel = createSvgElement('text', {
    x: 450, y: 95,
    'text-anchor': 'middle',
    'font-size': '12px',
    fill: '#2e7d32'
  });
  executionSubLabel.textContent = 'Starting...';
  
  const handlerName = createSvgElement('text', {
    x: 450, y: 115,
    'text-anchor': 'middle',
    'font-size': '10px',
    'font-weight': 'bold',
    fill: '#2e7d32'
  });
  handlerName.textContent = stepResult.handler_name;
  
  handlerStartDiagram.appendChild(executionPhase);
  handlerStartDiagram.appendChild(executionLabel);
  handlerStartDiagram.appendChild(executionSubLabel);
  handlerStartDiagram.appendChild(handlerName);
  
  // Handler preparation details
  const preparationY = 160;
  const preparationItems = [
    { label: 'Action Type', value: stepResult.action_type, x: 100 },
    { label: 'Parameters', value: `${Object.keys(stepResult.action_parameters).length} items`, x: 300 },
    { label: 'Context', value: `${Object.keys(stepResult.handler_context).length} items`, x: 500 }
  ];
  
  preparationItems.forEach(item => {
    const itemRect = createSvgElement('rect', {
      x: item.x - 60, y: preparationY,
      width: 120, height: 30,
      fill: '#f5f5f5',
      stroke: '#999',
      rx: 3
    });
    
    const itemLabel = createSvgElement('text', {
      x: item.x, y: preparationY + 12,
      'text-anchor': 'middle',
      'font-size': '10px',
      'font-weight': 'bold'
    });
    itemLabel.textContent = item.label;
    
    const itemValue = createSvgElement('text', {
      x: item.x, y: preparationY + 25,
      'text-anchor': 'middle',
      'font-size': '9px',
      fill: '#666'
    });
    itemValue.textContent = item.value;
    
    handlerStartDiagram.appendChild(itemRect);
    handlerStartDiagram.appendChild(itemLabel);
    handlerStartDiagram.appendChild(itemValue);
  });
  
  // Expected bus operations preview
  const busPreviewY = 210;
  const busOperationsText = createSvgElement('text', {
    x: 300, y: busPreviewY,
    'text-anchor': 'middle',
    'font-size': '10px',
    fill: '#666'
  });
  busOperationsText.textContent = `Expected Bus Operations: ${stepResult.expected_bus_operations.join(', ')}`;
  handlerStartDiagram.appendChild(busOperationsText);
  
  // Handler Start Results Panel
  document.querySelector('#handler-start-results').innerHTML = `
    <div class="handler-start-card">
      <div class="handler-header">
        <h4>Handler Execution Initiated</h4>
        <div class="handler-badge">
          <span class="handler-name">${stepResult.handler_name}</span>
        </div>
      </div>
      
      <div class="execution-details">
        <div class="action-info">
          <div class="info-item">
            <label>Action Type</label>
            <span class="action-type">${stepResult.action_type}</span>
          </div>
          <div class="info-item">
            <label>Handler</label>
            <span class="handler-value">${stepResult.handler_name}</span>
          </div>
        </div>
        
        <div class="parameters-section">
          <h5>Action Parameters</h5>
          <div class="parameters-display">
            ${Object.entries(stepResult.action_parameters).map(([key, value]) => `
              <div class="param-entry">
                <span class="param-key">${key}:</span>
                <span class="param-value">${typeof value === 'object' ? JSON.stringify(value, null, 2) : value}</span>
              </div>
            `).join('')}
          </div>
        </div>
        
        <div class="context-section">
          <h5>Handler Context</h5>
          <div class="context-summary">
            <div class="context-stat">
              <label>Context Items</label>
              <span>${Object.keys(stepResult.handler_context).length}</span>
            </div>
            <div class="context-details">
              ${Object.keys(stepResult.handler_context).slice(0, 5).map(key => `
                <span class="context-key">${key}</span>
              `).join('')}
              ${Object.keys(stepResult.handler_context).length > 5 ? `
                <span class="context-more">+${Object.keys(stepResult.handler_context).length - 5} more</span>
              ` : ''}
            </div>
          </div>
        </div>
        
        <div class="bus-operations-section">
          <h5>Expected Bus Operations</h5>
          <div class="bus-operations-list">
            ${stepResult.expected_bus_operations.map(operation => `
              <div class="bus-operation">
                <span class="operation-icon">🚌</span>
                <span class="operation-name">${operation}</span>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    </div>
  `;
  
  // Transition Summary Panel
  document.querySelector('#transition-summary').innerHTML = `
    <div class="transition-summary">
      <h4>Reasoning → Execution Transition</h4>
      
      <div class="transition-metrics">
        <div class="phase-completed">
          <h5>✅ Reasoning Phase Complete</h5>
          <ul class="completed-steps">
            <li>✓ Context built and validated</li>
            <li>✓ Multi-DMA analysis performed</li>
            <li>✓ Conscience checks passed</li>
            <li>✓ Final action selected</li>
          </ul>
        </div>
        
        <div class="phase-starting">
          <h5>🚀 Execution Phase Starting</h5>
          <ul class="starting-steps">
            <li>→ Handler context prepared</li>
            <li>→ Action parameters validated</li>
            <li>→ Bus operations identified</li>
            <li>→ Ready for execution</li>
          </ul>
        </div>
      </div>
      
      <div class="transition-quality">
        <div class="quality-item">
          <span class="quality-label">Reasoning Integrity</span>
          <span class="quality-status complete">Verified ✓</span>
        </div>
        <div class="quality-item">
          <span class="quality-label">Context Completeness</span>
          <span class="quality-status complete">Validated ✓</span>
        </div>
        <div class="quality-item">
          <span class="quality-label">Parameter Readiness</span>
          <span class="quality-status complete">Ready ✓</span>
        </div>
        <div class="quality-item">
          <span class="quality-label">Handler Selection</span>
          <span class="quality-status complete">Confirmed ✓</span>
        </div>
      </div>
    </div>
  `;
}
```

**Demo Value**: Shows the critical transition from ethical reasoning to action execution. This step demonstrates how CIRIS ensures that all ethical analysis is complete and verified before any external actions occur, maintaining the integrity principle by showing the clear handoff from decision-making to implementation.

---

### Step 12: BUS_OUTBOUND
**Context**: Handler sends requests to various buses (Communication, Memory, Tool, etc.) to perform the required operations for the action.

**Data Available** (`StepResultBusOutbound`):
- `buses_called`: Which buses were invoked (str[])
- `communication_bus`: Messages sent to communication (Dict[str, Any])
- `memory_bus`: Data sent to memory storage (Dict[str, Any])
- `tool_bus`: Tool invocations (Dict[str, Any])
- `operations_initiated`: Async operations started (str[])
- `awaiting_responses`: Operations waiting for response (str[])

**UI Enhancements**:
```typescript
function updateBusOutboundVisualization(stepResult: StepResultBusOutbound) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-bus-outbound').classList.add('active-step');
  
  // Create bus operations diagram
  const busOutboundDiagram = document.querySelector('#bus-outbound-diagram');
  busOutboundDiagram.innerHTML = '';
  
  const diagramWidth = 700;
  const diagramHeight = 400;
  
  // Central handler node
  const handlerNode = createSvgElement('circle', {
    cx: diagramWidth / 2, cy: diagramHeight / 2,
    r: 40,
    fill: '#2e7d32',
    stroke: 'white',
    'stroke-width': 3
  });
  
  const handlerLabel = createSvgElement('text', {
    x: diagramWidth / 2, y: diagramHeight / 2 - 5,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px',
    fill: 'white'
  });
  handlerLabel.textContent = 'HANDLER';
  
  const handlerStatus = createSvgElement('text', {
    x: diagramWidth / 2, y: diagramHeight / 2 + 8,
    'text-anchor': 'middle',
    'font-size': '10px',
    fill: 'white'
  });
  handlerStatus.textContent = 'Executing';
  
  busOutboundDiagram.appendChild(handlerNode);
  busOutboundDiagram.appendChild(handlerLabel);
  busOutboundDiagram.appendChild(handlerStatus);
  
  // Bus nodes and connections
  const busTypes = [
    { name: 'Communication\nBus', data: stepResult.communication_bus, color: '#1976d2', angle: 0 },
    { name: 'Memory\nBus', data: stepResult.memory_bus, color: '#7b1fa2', angle: 72 },
    { name: 'Tool\nBus', data: stepResult.tool_bus, color: '#f57c00', angle: 144 },
    { name: 'Runtime\nBus', data: {}, color: '#388e3c', angle: 216 },
    { name: 'Wise\nBus', data: {}, color: '#d32f2f', angle: 288 }
  ];
  
  busTypes.forEach(bus => {
    const angle = (bus.angle * Math.PI) / 180;
    const distance = 150;
    const x = (diagramWidth / 2) + Math.cos(angle) * distance;
    const y = (diagramHeight / 2) + Math.sin(angle) * distance;
    
    const isCalled = stepResult.buses_called.some(calledBus => 
      calledBus.toLowerCase().includes(bus.name.toLowerCase().split('\n')[0])
    );
    
    // Bus node
    const busNode = createSvgElement('rect', {
      x: x - 45, y: y - 25,
      width: 90, height: 50,
      fill: isCalled ? bus.color : '#f5f5f5',
      stroke: bus.color,
      'stroke-width': isCalled ? 3 : 1,
      rx: 8
    });
    
    const busLabel = createSvgElement('text', {
      x: x, y: y,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
      'font-size': '10px',
      'font-weight': 'bold',
      fill: isCalled ? 'white' : '#666'
    });
    busLabel.innerHTML = bus.name.replace('\\n', '<tspan x="' + x + '" dy="12">') + '</tspan>';
    
    // Connection line if called
    if (isCalled) {
      const line = createSvgElement('line', {
        x1: (diagramWidth / 2) + Math.cos(angle) * 40,
        y1: (diagramHeight / 2) + Math.sin(angle) * 40,
        x2: x - Math.cos(angle) * 45,
        y2: y - Math.sin(angle) * 25,
        stroke: bus.color,
        'stroke-width': 3,
        'marker-end': 'url(#arrowhead)'
      });
      
      // Operation indicator
      const operationCount = Object.keys(bus.data || {}).length;
      if (operationCount > 0) {
        const indicator = createSvgElement('circle', {
          cx: x + 30, cy: y - 20,
          r: 12,
          fill: '#4caf50',
          stroke: 'white',
          'stroke-width': 2
        });
        
        const indicatorText = createSvgElement('text', {
          x: x + 30, y: y - 15,
          'text-anchor': 'middle',
          'font-size': '10px',
          'font-weight': 'bold',
          fill: 'white'
        });
        indicatorText.textContent = operationCount.toString();
        
        busOutboundDiagram.appendChild(indicator);
        busOutboundDiagram.appendChild(indicatorText);
      }
      
      busOutboundDiagram.appendChild(line);
    }
    
    busOutboundDiagram.appendChild(busNode);
    busOutboundDiagram.appendChild(busLabel);
  });
  
  // Operations status indicators
  const statusY = diagramHeight - 50;
  
  // Operations initiated
  const initiatedRect = createSvgElement('rect', {
    x: 50, y: statusY,
    width: 200, height: 30,
    fill: '#e8f5e8',
    stroke: '#4caf50',
    rx: 5
  });
  
  const initiatedLabel = createSvgElement('text', {
    x: 150, y: statusY + 20,
    'text-anchor': 'middle',
    'font-size': '12px',
    'font-weight': 'bold'
  });
  initiatedLabel.textContent = `Initiated: ${stepResult.operations_initiated.length}`;
  
  // Awaiting responses
  const awaitingRect = createSvgElement('rect', {
    x: diagramWidth - 250, y: statusY,
    width: 200, height: 30,
    fill: '#fff3e0',
    stroke: '#ff9800',
    rx: 5
  });
  
  const awaitingLabel = createSvgElement('text', {
    x: diagramWidth - 150, y: statusY + 20,
    'text-anchor': 'middle',
    'font-size': '12px',
    'font-weight': 'bold'
  });
  awaitingLabel.textContent = `Awaiting: ${stepResult.awaiting_responses.length}`;
  
  busOutboundDiagram.appendChild(initiatedRect);
  busOutboundDiagram.appendChild(initiatedLabel);
  busOutboundDiagram.appendChild(awaitingRect);
  busOutboundDiagram.appendChild(awaitingLabel);
  
  // Bus Operations Results Panel
  document.querySelector('#bus-outbound-results').innerHTML = `
    <div class="bus-outbound-card">
      <div class="outbound-header">
        <h4>Outbound Bus Operations</h4>
        <div class="operation-status">
          <span class="initiated-count">${stepResult.operations_initiated.length} Initiated</span>
          <span class="awaiting-count">${stepResult.awaiting_responses.length} Awaiting</span>
        </div>
      </div>
      
      <div class="buses-called-section">
        <h5>Active Buses (${stepResult.buses_called.length})</h5>
        <div class="buses-list">
          ${stepResult.buses_called.map(bus => `
            <div class="bus-item active">
              <span class="bus-icon">🚌</span>
              <span class="bus-name">${bus}</span>
            </div>
          `).join('')}
        </div>
      </div>
      
      <div class="bus-operations-details">
        ${stepResult.communication_bus && Object.keys(stepResult.communication_bus).length > 0 ? `
          <div class="bus-section communication">
            <h5>Communication Bus Operations</h5>
            <div class="operations-data">
              ${Object.entries(stepResult.communication_bus).map(([key, value]) => `
                <div class="operation-item">
                  <span class="operation-key">${key}:</span>
                  <span class="operation-value">${typeof value === 'object' ? JSON.stringify(value).slice(0, 100) + '...' : value}</span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
        
        ${stepResult.memory_bus && Object.keys(stepResult.memory_bus).length > 0 ? `
          <div class="bus-section memory">
            <h5>Memory Bus Operations</h5>
            <div class="operations-data">
              ${Object.entries(stepResult.memory_bus).map(([key, value]) => `
                <div class="operation-item">
                  <span class="operation-key">${key}:</span>
                  <span class="operation-value">${typeof value === 'object' ? JSON.stringify(value).slice(0, 100) + '...' : value}</span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
        
        ${stepResult.tool_bus && Object.keys(stepResult.tool_bus).length > 0 ? `
          <div class="bus-section tool">
            <h5>Tool Bus Operations</h5>
            <div class="operations-data">
              ${Object.entries(stepResult.tool_bus).map(([key, value]) => `
                <div class="operation-item">
                  <span class="operation-key">${key}:</span>
                  <span class="operation-value">${typeof value === 'object' ? JSON.stringify(value).slice(0, 100) + '...' : value}</span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
      </div>
      
      <div class="operations-tracking">
        <div class="operations-initiated">
          <h5>Operations Initiated</h5>
          <div class="operations-list">
            ${stepResult.operations_initiated.map(operation => `
              <div class="operation-status-item initiated">
                <span class="status-indicator">🟢</span>
                <span class="operation-name">${operation}</span>
              </div>
            `).join('')}
          </div>
        </div>
        
        <div class="operations-awaiting">
          <h5>Awaiting Responses</h5>
          <div class="operations-list">
            ${stepResult.awaiting_responses.map(operation => `
              <div class="operation-status-item awaiting">
                <span class="status-indicator">🟡</span>
                <span class="operation-name">${operation}</span>
                <div class="loading-spinner"></div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    </div>
  `;
  
  // Architecture Flow Panel
  document.querySelector('#bus-architecture-flow').innerHTML = `
    <div class="architecture-flow">
      <h4>CIRIS Bus Architecture Flow</h4>
      
      <div class="flow-stages">
        <div class="flow-stage active">
          <div class="stage-number">1</div>
          <div class="stage-info">
            <h5>Handler Execution</h5>
            <p>Action handler processes ethical decision</p>
          </div>
        </div>
        
        <div class="flow-arrow">→</div>
        
        <div class="flow-stage active">
          <div class="stage-number">2</div>
          <div class="stage-info">
            <h5>Bus Operations</h5>
            <p>Requests sent to appropriate service buses</p>
          </div>
        </div>
        
        <div class="flow-arrow">→</div>
        
        <div class="flow-stage pending">
          <div class="stage-number">3</div>
          <div class="stage-info">
            <h5>External Processing</h5>
            <p>Services process requests and generate responses</p>
          </div>
        </div>
        
        <div class="flow-arrow">→</div>
        
        <div class="flow-stage pending">
          <div class="stage-number">4</div>
          <div class="stage-info">
            <h5>Response Integration</h5>
            <p>Results collected and integrated for handler</p>
          </div>
        </div>
      </div>
      
      <div class="bus-principles">
        <h5>Bus Architecture Principles</h5>
        <div class="principles-grid">
          <div class="principle-item">
            <span class="principle-name">Decoupling</span>
            <span class="principle-desc">Handlers don't directly call services</span>
          </div>
          <div class="principle-item">
            <span class="principle-name">Scalability</span>
            <span class="principle-desc">Multiple service providers per bus</span>
          </div>
          <div class="principle-item">
            <span class="principle-name">Transparency</span>
            <span class="principle-desc">All operations tracked and auditable</span>
          </div>
          <div class="principle-item">
            <span class="principle-name">Reliability</span>
            <span class="principle-desc">Async operations with proper error handling</span>
          </div>
        </div>
      </div>
    </div>
  `;
}
```

**Demo Value**: Shows CIRIS's distributed architecture in action - how ethical decisions translate into coordinated operations across multiple service buses. Demonstrates the system's scalability through decoupled architecture and transparency through complete operation tracking, embodying both the integrity and beneficence principles.

---

### Step 13: PACKAGE_HANDLING
**Context**: External services process the bus requests and adapters handle package transformation and routing at the system boundary.

**Data Available** (`StepResultPackageHandling`):
- `adapter_name`: Which adapter is handling (str)
- `package_type`: Type of package (message, tool call, etc.)
- `external_service_called`: External service invoked (str)
- `external_response_received`: Whether response came back (bool)
- `package_transformed`: Whether package was modified
- `transformation_details`: How package was changed (Dict[str, Any])

**UI Enhancements**:
```typescript
function updatePackageHandlingVisualization(stepResult: StepResultPackageHandling) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-package-handling').classList.add('active-step');
  
  // Create package handling flow diagram
  const packageHandlingDiagram = document.querySelector('#package-handling-diagram');
  packageHandlingDiagram.innerHTML = '';
  
  const diagramWidth = 800;
  const diagramHeight = 350;
  
  // System boundary
  const boundaryLine = createSvgElement('line', {
    x1: diagramWidth / 2, y1: 50,
    x2: diagramWidth / 2, y2: diagramHeight - 50,
    stroke: '#ff9800',
    'stroke-width': 4,
    'stroke-dasharray': '10,5'
  });
  
  const boundaryLabel = createSvgElement('text', {
    x: diagramWidth / 2 + 10, y: 40,
    'font-weight': 'bold',
    'font-size': '14px',
    fill: '#ff9800'
  });
  boundaryLabel.textContent = 'SYSTEM BOUNDARY';
  
  packageHandlingDiagram.appendChild(boundaryLine);
  packageHandlingDiagram.appendChild(boundaryLabel);
  
  // Internal CIRIS side
  const internalSide = createSvgElement('text', {
    x: diagramWidth / 4, y: 70,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '16px',
    fill: '#2e7d32'
  });
  internalSide.textContent = 'CIRIS INTERNAL';
  
  // External world side
  const externalSide = createSvgElement('text', {
    x: (diagramWidth * 3) / 4, y: 70,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '16px',
    fill: '#1976d2'
  });
  externalSide.textContent = 'EXTERNAL WORLD';
  
  packageHandlingDiagram.appendChild(internalSide);
  packageHandlingDiagram.appendChild(externalSide);
  
  // Adapter at the boundary
  const adapterRect = createSvgElement('rect', {
    x: diagramWidth / 2 - 60, y: 140,
    width: 120, height: 60,
    fill: '#fff3e0',
    stroke: '#ff9800',
    'stroke-width': 3,
    rx: 10
  });
  
  const adapterLabel = createSvgElement('text', {
    x: diagramWidth / 2, y: 160,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px',
    fill: '#e65100'
  });
  adapterLabel.textContent = 'ADAPTER';
  
  const adapterName = createSvgElement('text', {
    x: diagramWidth / 2, y: 180,
    'text-anchor': 'middle',
    'font-size': '10px',
    'font-weight': 'bold',
    fill: '#e65100'
  });
  adapterName.textContent = stepResult.adapter_name;
  
  packageHandlingDiagram.appendChild(adapterRect);
  packageHandlingDiagram.appendChild(adapterLabel);
  packageHandlingDiagram.appendChild(adapterName);
  
  // Internal package
  const internalPackage = createSvgElement('rect', {
    x: 80, y: 150,
    width: 100, height: 40,
    fill: '#e8f5e8',
    stroke: '#4caf50',
    'stroke-width': 2,
    rx: 5
  });
  
  const internalPackageLabel = createSvgElement('text', {
    x: 130, y: 165,
    'text-anchor': 'middle',
    'font-size': '10px',
    'font-weight': 'bold'
  });
  internalPackageLabel.textContent = 'Internal Package';
  
  const packageType = createSvgElement('text', {
    x: 130, y: 180,
    'text-anchor': 'middle',
    'font-size': '9px',
    fill: '#666'
  });
  packageType.textContent = stepResult.package_type;
  
  packageHandlingDiagram.appendChild(internalPackage);
  packageHandlingDiagram.appendChild(internalPackageLabel);
  packageHandlingDiagram.appendChild(packageType);
  
  // External service
  const externalService = createSvgElement('circle', {
    cx: (diagramWidth * 3) / 4, cy: 170,
    r: 40,
    fill: '#e3f2fd',
    stroke: '#1976d2',
    'stroke-width': 3
  });
  
  const externalServiceLabel = createSvgElement('text', {
    x: (diagramWidth * 3) / 4, y: 165,
    'text-anchor': 'middle',
    'font-size': '10px',
    'font-weight': 'bold'
  });
  externalServiceLabel.textContent = 'External Service';
  
  const externalServiceName = createSvgElement('text', {
    x: (diagramWidth * 3) / 4, y: 180,
    'text-anchor': 'middle',
    'font-size': '9px',
    fill: '#666'
  });
  externalServiceName.textContent = stepResult.external_service_called || 'Service';
  
  packageHandlingDiagram.appendChild(externalService);
  packageHandlingDiagram.appendChild(externalServiceLabel);
  packageHandlingDiagram.appendChild(externalServiceName);
  
  // Package transformation flow
  const transformArrow1 = createSvgElement('line', {
    x1: 180, y1: 170,
    x2: diagramWidth / 2 - 70, y2: 170,
    stroke: '#4caf50',
    'stroke-width': 3,
    'marker-end': 'url(#arrowhead)'
  });
  
  const transformArrow2 = createSvgElement('line', {
    x1: diagramWidth / 2 + 70, y1: 170,
    x2: (diagramWidth * 3) / 4 - 50, y2: 170,
    stroke: stepResult.external_response_received ? '#4caf50' : '#ff9800',
    'stroke-width': 3,
    'marker-end': 'url(#arrowhead)'
  });
  
  packageHandlingDiagram.appendChild(transformArrow1);
  packageHandlingDiagram.appendChild(transformArrow2);
  
  // Transformation indicator
  if (stepResult.package_transformed) {
    const transformIndicator = createSvgElement('circle', {
      cx: diagramWidth / 2, cy: 120,
      r: 15,
      fill: '#ff9800',
      stroke: 'white',
      'stroke-width': 2
    });
    
    const transformIcon = createSvgElement('text', {
      x: diagramWidth / 2, y: 125,
      'text-anchor': 'middle',
      'font-size': '12px',
      'font-weight': 'bold',
      fill: 'white'
    });
    transformIcon.textContent = '⚙';
    
    const transformLabel = createSvgElement('text', {
      x: diagramWidth / 2, y: 105,
      'text-anchor': 'middle',
      'font-size': '10px',
      'font-weight': 'bold',
      fill: '#ff9800'
    });
    transformLabel.textContent = 'TRANSFORMED';
    
    packageHandlingDiagram.appendChild(transformIndicator);
    packageHandlingDiagram.appendChild(transformIcon);
    packageHandlingDiagram.appendChild(transformLabel);
  }
  
  // Response status
  const responseStatus = createSvgElement('text', {
    x: diagramWidth / 2, y: 250,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px',
    fill: stepResult.external_response_received ? '#4caf50' : '#f44336'
  });
  responseStatus.textContent = stepResult.external_response_received ? 
    '✓ RESPONSE RECEIVED' : '⏳ AWAITING RESPONSE';
  
  packageHandlingDiagram.appendChild(responseStatus);
  
  // Package Handling Results Panel
  document.querySelector('#package-handling-results').innerHTML = `
    <div class="package-handling-card">
      <div class="package-header">
        <h4>Package Processing at System Boundary</h4>
        <div class="adapter-badge">
          <span class="adapter-name">${stepResult.adapter_name}</span>
        </div>
      </div>
      
      <div class="package-details">
        <div class="package-info">
          <div class="info-item">
            <label>Package Type</label>
            <span class="package-type">${stepResult.package_type}</span>
          </div>
          <div class="info-item">
            <label>External Service</label>
            <span class="external-service">${stepResult.external_service_called || 'None'}</span>
          </div>
          <div class="info-item">
            <label>Response Status</label>
            <span class="response-status ${stepResult.external_response_received ? 'received' : 'pending'}">
              ${stepResult.external_response_received ? 'Received ✓' : 'Pending ⏳'}
            </span>
          </div>
        </div>
        
        <div class="transformation-section">
          <h5>Package Transformation</h5>
          <div class="transformation-status">
            <span class="transform-indicator ${stepResult.package_transformed ? 'yes' : 'no'}">
              ${stepResult.package_transformed ? '⚙ Package Transformed' : '→ No Transformation'}
            </span>
          </div>
          
          ${stepResult.package_transformed && stepResult.transformation_details ? `
            <div class="transformation-details">
              <h6>Transformation Details</h6>
              <div class="details-grid">
                ${Object.entries(stepResult.transformation_details).map(([key, value]) => `
                  <div class="detail-item">
                    <span class="detail-key">${key}:</span>
                    <span class="detail-value">${typeof value === 'object' ? JSON.stringify(value).slice(0, 80) + '...' : value}</span>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}
        </div>
        
        <div class="boundary-processing">
          <h5>Boundary Processing Flow</h5>
          <div class="processing-steps">
            <div class="step-item completed">
              <span class="step-number">1</span>
              <span class="step-desc">Internal package received</span>
              <span class="step-status">✓</span>
            </div>
            <div class="step-item ${stepResult.package_transformed ? 'completed' : 'skipped'}">
              <span class="step-number">2</span>
              <span class="step-desc">Package transformation</span>
              <span class="step-status">${stepResult.package_transformed ? '✓' : '-'}</span>
            </div>
            <div class="step-item completed">
              <span class="step-number">3</span>
              <span class="step-desc">External service call</span>
              <span class="step-status">✓</span>
            </div>
            <div class="step-item ${stepResult.external_response_received ? 'completed' : 'pending'}">
              <span class="step-number">4</span>
              <span class="step-desc">Response handling</span>
              <span class="step-status">${stepResult.external_response_received ? '✓' : '⏳'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
  
  // Boundary Architecture Panel
  document.querySelector('#boundary-architecture').innerHTML = `
    <div class="boundary-architecture">
      <h4>System Boundary Architecture</h4>
      
      <div class="boundary-principles">
        <div class="principle-section">
          <h5>🛡 Security Principles</h5>
          <ul class="principles-list">
            <li>All external communication through adapters</li>
            <li>Package transformation for format compatibility</li>
            <li>Input validation and sanitization</li>
            <li>Response verification before internal processing</li>
          </ul>
        </div>
        
        <div class="principle-section">
          <h5>🔄 Integration Principles</h5>
          <ul class="principles-list">
            <li>Adapter pattern for external service integration</li>
            <li>Protocol translation and normalization</li>
            <li>Async operation handling</li>
            <li>Error recovery and retry logic</li>
          </ul>
        </div>
        
        <div class="principle-section">
          <h5>📊 Transparency Principles</h5>
          <ul class="principles-list">
            <li>Complete operation logging and audit trail</li>
            <li>Transformation tracking for accountability</li>
            <li>Response status monitoring</li>
            <li>Performance metrics collection</li>
          </ul>
        </div>
      </div>
      
      <div class="boundary-status">
        <h5>Current Boundary State</h5>
        <div class="status-grid">
          <div class="status-item">
            <span class="status-label">Active Adapter</span>
            <span class="status-value">${stepResult.adapter_name}</span>
          </div>
          <div class="status-item">
            <span class="status-label">Package Processing</span>
            <span class="status-value">${stepResult.package_transformed ? 'Transformed' : 'Pass-through'}</span>
          </div>
          <div class="status-item">
            <span class="status-label">External Integration</span>
            <span class="status-value">${stepResult.external_response_received ? 'Active' : 'Pending'}</span>
          </div>
          <div class="status-item">
            <span class="status-label">Boundary Integrity</span>
            <span class="status-value">Maintained ✓</span>
          </div>
        </div>
      </div>
    </div>
  `;
}
```

**Demo Value**: Critical demonstration of CIRIS's secure boundary management - shows how the system maintains security and integrity while interfacing with external services. This step embodies the integrity principle through transparent boundary operations and the respect for autonomy principle by maintaining clear separation between internal reasoning and external actions.

---

### Step 14: BUS_INBOUND
**Context**: Responses from external services flow back through the bus system to be aggregated and processed by the handler.

**Data Available** (`StepResultBusInbound`):
- `responses_received`: All responses from buses (Dict[str, Any])
- `communication_response`: Communication results (Dict[str, Any])
- `memory_response`: Memory operation results (Dict[str, Any])
- `tool_response`: Tool execution results (Dict[str, Any])
- `responses_aggregated`: Whether responses were combined
- `final_result`: Aggregated result for handler (Dict[str, Any])

**UI Enhancements**:
```typescript
function updateBusInboundVisualization(stepResult: StepResultBusInbound) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-bus-inbound').classList.add('active-step');
  
  // Create inbound bus flow diagram
  const busInboundDiagram = document.querySelector('#bus-inbound-diagram');
  busInboundDiagram.innerHTML = '';
  
  const diagramWidth = 700;
  const diagramHeight = 400;
  
  // Central handler node (receiving responses)
  const handlerNode = createSvgElement('circle', {
    cx: diagramWidth / 2, cy: diagramHeight / 2,
    r: 45,
    fill: '#1976d2',
    stroke: 'white',
    'stroke-width': 3
  });
  
  const handlerLabel = createSvgElement('text', {
    x: diagramWidth / 2, y: diagramHeight / 2 - 8,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px',
    fill: 'white'
  });
  handlerLabel.textContent = 'HANDLER';
  
  const handlerStatus = createSvgElement('text', {
    x: diagramWidth / 2, y: diagramHeight / 2 + 5,
    'text-anchor': 'middle',
    'font-size': '10px',
    fill: 'white'
  });
  handlerStatus.textContent = 'Aggregating';
  
  const handlerSubStatus = createSvgElement('text', {
    x: diagramWidth / 2, y: diagramHeight / 2 + 18,
    'text-anchor': 'middle',
    'font-size': '9px',
    fill: 'white'
  });
  handlerSubStatus.textContent = 'Responses';
  
  busInboundDiagram.appendChild(handlerNode);
  busInboundDiagram.appendChild(handlerLabel);
  busInboundDiagram.appendChild(handlerStatus);
  busInboundDiagram.appendChild(handlerSubStatus);
  
  // Response sources around the handler
  const responseSources = [
    { name: 'Communication\nResponse', data: stepResult.communication_response, color: '#1976d2', angle: 0 },
    { name: 'Memory\nResponse', data: stepResult.memory_response, color: '#7b1fa2', angle: 90 },
    { name: 'Tool\nResponse', data: stepResult.tool_response, color: '#f57c00', angle: 180 },
    { name: 'Runtime\nResponse', data: {}, color: '#388e3c', angle: 270 }
  ];
  
  responseSources.forEach(source => {
    const angle = (source.angle * Math.PI) / 180;
    const distance = 160;
    const x = (diagramWidth / 2) + Math.cos(angle) * distance;
    const y = (diagramHeight / 2) + Math.sin(angle) * distance;
    
    const hasData = source.data && Object.keys(source.data).length > 0;
    
    // Response source node
    const sourceNode = createSvgElement('rect', {
      x: x - 50, y: y - 30,
      width: 100, height: 60,
      fill: hasData ? source.color : '#f5f5f5',
      stroke: source.color,
      'stroke-width': hasData ? 3 : 1,
      rx: 8,
      'fill-opacity': hasData ? '0.9' : '0.3'
    });
    
    const sourceLabel = createSvgElement('text', {
      x: x, y: y,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
      'font-size': '10px',
      'font-weight': 'bold',
      fill: hasData ? 'white' : '#666'
    });
    sourceLabel.innerHTML = source.name.replace('\\n', '<tspan x="' + x + '" dy="12">') + '</tspan>';
    
    // Data flow arrow if has data
    if (hasData) {
      const arrow = createSvgElement('line', {
        x1: x - Math.cos(angle) * 50,
        y1: y - Math.sin(angle) * 30,
        x2: (diagramWidth / 2) + Math.cos(angle) * 50,
        y2: (diagramHeight / 2) + Math.sin(angle) * 45,
        stroke: source.color,
        'stroke-width': 4,
        'marker-end': 'url(#arrowhead)'
      });
      
      // Response data indicator
      const dataCount = Object.keys(source.data).length;
      const indicator = createSvgElement('circle', {
        cx: x + 35, cy: y - 25,
        r: 12,
        fill: '#4caf50',
        stroke: 'white',
        'stroke-width': 2
      });
      
      const indicatorText = createSvgElement('text', {
        x: x + 35, y: y - 20,
        'text-anchor': 'middle',
        'font-size': '10px',
        'font-weight': 'bold',
        fill: 'white'
      });
      indicatorText.textContent = dataCount.toString();
      
      busInboundDiagram.appendChild(arrow);
      busInboundDiagram.appendChild(indicator);
      busInboundDiagram.appendChild(indicatorText);
    }
    
    busInboundDiagram.appendChild(sourceNode);
    busInboundDiagram.appendChild(sourceLabel);
  });
  
  // Aggregation result indicator
  const aggregationY = diagramHeight - 80;
  const aggregationRect = createSvgElement('rect', {
    x: diagramWidth / 2 - 100, y: aggregationY,
    width: 200, height: 50,
    fill: stepResult.responses_aggregated ? '#e8f5e8' : '#fff3e0',
    stroke: stepResult.responses_aggregated ? '#4caf50' : '#ff9800',
    'stroke-width': 3,
    rx: 10
  });
  
  const aggregationLabel = createSvgElement('text', {
    x: diagramWidth / 2, y: aggregationY + 20,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '12px'
  });
  aggregationLabel.textContent = stepResult.responses_aggregated ? 
    '✓ RESPONSES AGGREGATED' : '⏳ AGGREGATING RESPONSES';
  
  const aggregationArrow = createSvgElement('line', {
    x1: diagramWidth / 2, y1: (diagramHeight / 2) + 50,
    x2: diagramWidth / 2, y2: aggregationY - 10,
    stroke: stepResult.responses_aggregated ? '#4caf50' : '#ff9800',
    'stroke-width': 3,
    'marker-end': 'url(#arrowhead)'
  });
  
  busInboundDiagram.appendChild(aggregationRect);
  busInboundDiagram.appendChild(aggregationLabel);
  busInboundDiagram.appendChild(aggregationArrow);
  
  // Final result size indicator
  if (stepResult.final_result && Object.keys(stepResult.final_result).length > 0) {
    const resultSize = Object.keys(stepResult.final_result).length;
    const resultIndicator = createSvgElement('text', {
      x: diagramWidth / 2, y: aggregationY + 35,
      'text-anchor': 'middle',
      'font-size': '10px',
      fill: '#666'
    });
    resultIndicator.textContent = `Final Result: ${resultSize} items`;
    busInboundDiagram.appendChild(resultIndicator);
  }
  
  // Bus Inbound Results Panel
  document.querySelector('#bus-inbound-results').innerHTML = `
    <div class="bus-inbound-card">
      <div class="inbound-header">
        <h4>Inbound Bus Responses</h4>
        <div class="aggregation-status">
          <span class="status-badge ${stepResult.responses_aggregated ? 'completed' : 'processing'}">
            ${stepResult.responses_aggregated ? 'Aggregated ✓' : 'Processing ⏳'}
          </span>
        </div>
      </div>
      
      <div class="responses-summary">
        <h5>Response Sources</h5>
        <div class="responses-grid">
          ${stepResult.communication_response && Object.keys(stepResult.communication_response).length > 0 ? `
            <div class="response-source communication">
              <div class="source-header">
                <span class="source-icon">💬</span>
                <span class="source-name">Communication</span>
              </div>
              <div class="source-data">
                ${Object.keys(stepResult.communication_response).length} response items
              </div>
            </div>
          ` : ''}
          
          ${stepResult.memory_response && Object.keys(stepResult.memory_response).length > 0 ? `
            <div class="response-source memory">
              <div class="source-header">
                <span class="source-icon">🧠</span>
                <span class="source-name">Memory</span>
              </div>
              <div class="source-data">
                ${Object.keys(stepResult.memory_response).length} response items
              </div>
            </div>
          ` : ''}
          
          ${stepResult.tool_response && Object.keys(stepResult.tool_response).length > 0 ? `
            <div class="response-source tool">
              <div class="source-header">
                <span class="source-icon">🔧</span>
                <span class="source-name">Tools</span>
              </div>
              <div class="source-data">
                ${Object.keys(stepResult.tool_response).length} response items
              </div>
            </div>
          ` : ''}
        </div>
      </div>
      
      <div class="response-details">
        <h5>Response Data Details</h5>
        <div class="details-sections">
          ${stepResult.communication_response && Object.keys(stepResult.communication_response).length > 0 ? `
            <div class="detail-section communication">
              <h6>Communication Response</h6>
              <div class="response-data">
                ${Object.entries(stepResult.communication_response).map(([key, value]) => `
                  <div class="response-item">
                    <span class="response-key">${key}:</span>
                    <span class="response-value">${typeof value === 'object' ? JSON.stringify(value).slice(0, 100) + '...' : value}</span>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}
          
          ${stepResult.memory_response && Object.keys(stepResult.memory_response).length > 0 ? `
            <div class="detail-section memory">
              <h6>Memory Response</h6>
              <div class="response-data">
                ${Object.entries(stepResult.memory_response).map(([key, value]) => `
                  <div class="response-item">
                    <span class="response-key">${key}:</span>
                    <span class="response-value">${typeof value === 'object' ? JSON.stringify(value).slice(0, 100) + '...' : value}</span>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}
          
          ${stepResult.tool_response && Object.keys(stepResult.tool_response).length > 0 ? `
            <div class="detail-section tool">
              <h6>Tool Response</h6>
              <div class="response-data">
                ${Object.entries(stepResult.tool_response).map(([key, value]) => `
                  <div class="response-item">
                    <span class="response-key">${key}:</span>
                    <span class="response-value">${typeof value === 'object' ? JSON.stringify(value).slice(0, 100) + '...' : value}</span>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}
        </div>
      </div>
      
      <div class="final-result-section">
        <h5>Aggregated Final Result</h5>
        ${stepResult.final_result && Object.keys(stepResult.final_result).length > 0 ? `
          <div class="final-result-display">
            <div class="result-stats">
              <span class="stat-item">Total Items: ${Object.keys(stepResult.final_result).length}</span>
              <span class="stat-item">Status: ${stepResult.responses_aggregated ? 'Complete' : 'Processing'}</span>
            </div>
            <div class="result-preview">
              ${Object.entries(stepResult.final_result).slice(0, 3).map(([key, value]) => `
                <div class="result-item">
                  <span class="result-key">${key}:</span>
                  <span class="result-value">${typeof value === 'object' ? JSON.stringify(value).slice(0, 80) + '...' : value}</span>
                </div>
              `).join('')}
              ${Object.keys(stepResult.final_result).length > 3 ? `
                <div class="result-more">+${Object.keys(stepResult.final_result).length - 3} more items...</div>
              ` : ''}
            </div>
          </div>
        ` : `
          <div class="no-result">
            <p>No final result data available yet.</p>
          </div>
        `}
      </div>
    </div>
  `;
  
  // Response Integration Flow Panel
  document.querySelector('#response-integration-flow').innerHTML = `
    <div class="integration-flow">
      <h4>Response Integration Flow</h4>
      
      <div class="flow-visualization">
        <div class="flow-step completed">
          <div class="step-icon">📤</div>
          <div class="step-info">
            <h5>Outbound Requests</h5>
            <p>Bus operations initiated to external services</p>
          </div>
        </div>
        
        <div class="flow-arrow">→</div>
        
        <div class="flow-step completed">
          <div class="step-icon">⚙️</div>
          <div class="step-info">
            <h5>External Processing</h5>
            <p>Services processed requests and generated responses</p>
          </div>
        </div>
        
        <div class="flow-arrow">→</div>
        
        <div class="flow-step active">
          <div class="step-icon">📥</div>
          <div class="step-info">
            <h5>Response Collection</h5>
            <p>Gathering responses from multiple bus sources</p>
          </div>
        </div>
        
        <div class="flow-arrow">→</div>
        
        <div class="flow-step ${stepResult.responses_aggregated ? 'completed' : 'pending'}">
          <div class="step-icon">🔗</div>
          <div class="step-info">
            <h5>Response Aggregation</h5>
            <p>Combining responses into unified result</p>
          </div>
        </div>
      </div>
      
      <div class="integration-metrics">
        <h5>Integration Metrics</h5>
        <div class="metrics-grid">
          <div class="metric-item">
            <span class="metric-label">Response Sources</span>
            <span class="metric-value">${[
              stepResult.communication_response && Object.keys(stepResult.communication_response).length > 0 ? 'Communication' : null,
              stepResult.memory_response && Object.keys(stepResult.memory_response).length > 0 ? 'Memory' : null,
              stepResult.tool_response && Object.keys(stepResult.tool_response).length > 0 ? 'Tools' : null
            ].filter(Boolean).length}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Total Response Items</span>
            <span class="metric-value">${Object.keys(stepResult.responses_received || {}).length}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Aggregation Status</span>
            <span class="metric-value ${stepResult.responses_aggregated ? 'success' : 'processing'}">
              ${stepResult.responses_aggregated ? 'Complete' : 'Processing'}
            </span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Final Result Size</span>
            <span class="metric-value">${Object.keys(stepResult.final_result || {}).length} items</span>
          </div>
        </div>
      </div>
    </div>
  `;
}
```

**Demo Value**: Shows CIRIS's sophisticated response integration system - how multiple asynchronous operations across different service domains are collected and aggregated into coherent results. Demonstrates the system's coordination capabilities and the fidelity principle through reliable response handling and integration.

---

### Step 15: HANDLER_COMPLETE
**Context**: Final step where handler execution completes, results are processed, and the thought lifecycle concludes with potential cascade effects.

**Data Available** (`StepResultHandlerComplete`):
- `handler_success`: Whether handler succeeded (bool)
- `handler_message`: Result message (str)
- `handler_data`: Handler output data (Dict[str, Any])
- `thought_final_status`: Final thought status (str)
- `task_status_update`: Task status change if any (str)
- `total_processing_time_ms`: Complete processing time for this thought
- `total_tokens_used`: Total LLM resource consumption
- `triggers_new_thoughts`: Whether this creates more work (bool)
- `triggered_thought_ids`: New thoughts generated (str[])

**UI Enhancements**:
```typescript
function updateHandlerCompleteVisualization(stepResult: StepResultHandlerComplete) {
  // Update active step
  document.querySelector('.active-step')?.classList.remove('active-step');
  document.querySelector('#step-handler-complete').classList.add('active-step');
  
  // Create completion summary diagram
  const handlerCompleteDiagram = document.querySelector('#handler-complete-diagram');
  handlerCompleteDiagram.innerHTML = '';
  
  const diagramWidth = 800;
  const diagramHeight = 350;
  
  // Completion status center
  const completionNode = createSvgElement('circle', {
    cx: diagramWidth / 2, cy: diagramHeight / 2 - 50,
    r: 50,
    fill: stepResult.handler_success ? '#4caf50' : '#f44336',
    stroke: 'white',
    'stroke-width': 4
  });
  
  const completionIcon = createSvgElement('text', {
    x: diagramWidth / 2, y: diagramHeight / 2 - 65,
    'text-anchor': 'middle',
    'font-size': '24px',
    fill: 'white'
  });
  completionIcon.textContent = stepResult.handler_success ? '✓' : '✗';
  
  const completionLabel = createSvgElement('text', {
    x: diagramWidth / 2, y: diagramHeight / 2 - 40,
    'text-anchor': 'middle',
    'font-weight': 'bold',
    'font-size': '14px',
    fill: 'white'
  });
  completionLabel.textContent = 'HANDLER';
  
  const completionStatus = createSvgElement('text', {
    x: diagramWidth / 2, y: diagramHeight / 2 - 25,
    'text-anchor': 'middle',
    'font-size': '12px',
    fill: 'white'
  });
  completionStatus.textContent = stepResult.handler_success ? 'SUCCESS' : 'FAILED';
  
  handlerCompleteDiagram.appendChild(completionNode);
  handlerCompleteDiagram.appendChild(completionIcon);
  handlerCompleteDiagram.appendChild(completionLabel);
  handlerCompleteDiagram.appendChild(completionStatus);
  
  // Processing metrics
  const metricsY = diagramHeight / 2 + 30;
  const metrics = [
    { label: 'Processing Time', value: `${stepResult.total_processing_time_ms}ms`, x: diagramWidth / 2 - 150 },
    { label: 'Tokens Used', value: stepResult.total_tokens_used?.toString() || '0', x: diagramWidth / 2 },
    { label: 'Final Status', value: stepResult.thought_final_status, x: diagramWidth / 2 + 150 }
  ];
  
  metrics.forEach(metric => {
    const metricRect = createSvgElement('rect', {
      x: metric.x - 60, y: metricsY,
      width: 120, height: 35,
      fill: '#f5f5f5',
      stroke: '#ddd',
      rx: 5
    });
    
    const metricLabel = createSvgElement('text', {
      x: metric.x, y: metricsY + 15,
      'text-anchor': 'middle',
      'font-size': '10px',
      'font-weight': 'bold'
    });
    metricLabel.textContent = metric.label;
    
    const metricValue = createSvgElement('text', {
      x: metric.x, y: metricsY + 28,
      'text-anchor': 'middle',
      'font-size': '11px',
      fill: '#2e7d32'
    });
    metricValue.textContent = metric.value;
    
    handlerCompleteDiagram.appendChild(metricRect);
    handlerCompleteDiagram.appendChild(metricLabel);
    handlerCompleteDiagram.appendChild(metricValue);
  });
  
  // Cascade effects if any
  if (stepResult.triggers_new_thoughts) {
    const cascadeY = diagramHeight - 80;
    const cascadeRect = createSvgElement('rect', {
      x: diagramWidth / 2 - 120, y: cascadeY,
      width: 240, height: 40,
      fill: '#fff3e0',
      stroke: '#ff9800',
      'stroke-width': 2,
      rx: 8
    });
    
    const cascadeLabel = createSvgElement('text', {
      x: diagramWidth / 2, y: cascadeY + 15,
      'text-anchor': 'middle',
      'font-weight': 'bold',
      'font-size': '12px',
      fill: '#e65100'
    });
    cascadeLabel.textContent = '🔄 TRIGGERS NEW THOUGHTS';
    
    const cascadeCount = createSvgElement('text', {
      x: diagramWidth / 2, y: cascadeY + 30,
      'text-anchor': 'middle',
      'font-size': '10px',
      fill: '#666'
    });
    cascadeCount.textContent = `${stepResult.triggered_thought_ids?.length || 0} new thoughts generated`;
    
    // Cascade arrow
    const cascadeArrow = createSvgElement('line', {
      x1: diagramWidth / 2, y1: metricsY + 40,
      x2: diagramWidth / 2, y2: cascadeY - 10,
      stroke: '#ff9800',
      'stroke-width': 3,
      'marker-end': 'url(#arrowhead)'
    });
    
    handlerCompleteDiagram.appendChild(cascadeRect);
    handlerCompleteDiagram.appendChild(cascadeLabel);
    handlerCompleteDiagram.appendChild(cascadeCount);
    handlerCompleteDiagram.appendChild(cascadeArrow);
  }
  
  // Handler Complete Results Panel
  document.querySelector('#handler-complete-results').innerHTML = `
    <div class="handler-complete-card">
      <div class="completion-header">
        <h4>Handler Execution Complete</h4>
        <div class="completion-badge ${stepResult.handler_success ? 'success' : 'failure'}">
          ${stepResult.handler_success ? '✓ SUCCESS' : '✗ FAILED'}
        </div>
      </div>
      
      <div class="completion-details">
        <div class="result-message">
          <h5>Handler Result</h5>
          <div class="message-content ${stepResult.handler_success ? 'success' : 'error'}">
            "${stepResult.handler_message}"
          </div>
        </div>
        
        <div class="execution-metrics">
          <h5>Execution Metrics</h5>
          <div class="metrics-display">
            <div class="metric-row">
              <div class="metric-item">
                <label>Total Processing Time</label>
                <span class="metric-value">${stepResult.total_processing_time_ms}ms</span>
              </div>
              <div class="metric-item">
                <label>Tokens Consumed</label>
                <span class="metric-value">${stepResult.total_tokens_used || 0}</span>
              </div>
            </div>
            <div class="metric-row">
              <div class="metric-item">
                <label>Thought Final Status</label>
                <span class="status-badge">${stepResult.thought_final_status}</span>
              </div>
              <div class="metric-item">
                <label>Task Status Update</label>
                <span class="status-badge">${stepResult.task_status_update || 'No Change'}</span>
              </div>
            </div>
          </div>
        </div>
        
        ${stepResult.handler_data && Object.keys(stepResult.handler_data).length > 0 ? `
          <div class="handler-output">
            <h5>Handler Output Data</h5>
            <div class="output-display">
              ${Object.entries(stepResult.handler_data).map(([key, value]) => `
                <div class="output-item">
                  <span class="output-key">${key}:</span>
                  <span class="output-value">${typeof value === 'object' ? JSON.stringify(value, null, 2) : value}</span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
        
        <div class="cascade-effects">
          <h5>Cascade Effects</h5>
          <div class="cascade-status ${stepResult.triggers_new_thoughts ? 'active' : 'none'}">
            ${stepResult.triggers_new_thoughts ? `
              <div class="cascade-active">
                <span class="cascade-icon">🔄</span>
                <span class="cascade-text">Triggers ${stepResult.triggered_thought_ids?.length || 0} new thoughts</span>
              </div>
              ${stepResult.triggered_thought_ids && stepResult.triggered_thought_ids.length > 0 ? `
                <div class="new-thoughts-list">
                  <h6>Generated Thoughts</h6>
                  ${stepResult.triggered_thought_ids.map(thoughtId => `
                    <div class="new-thought-item">
                      <span class="thought-icon">💭</span>
                      <span class="thought-id">${thoughtId}</span>
                    </div>
                  `).join('')}
                </div>
              ` : ''}
            ` : `
              <div class="cascade-none">
                <span class="cascade-icon">✋</span>
                <span class="cascade-text">No cascade effects - processing complete</span>
              </div>
            `}
          </div>
        </div>
      </div>
    </div>
  `;
  
  // Complete Ethical Process Summary Panel
  document.querySelector('#complete-process-summary').innerHTML = `
    <div class="complete-process-summary">
      <h4>Complete Ethical Processing Summary</h4>
      
      <div class="process-timeline">
        <h5>🧠 Reasoning Phase Complete</h5>
        <div class="phase-summary reasoning">
          <div class="phase-steps">
            <span class="step-complete">✓ Task prioritization and thought generation</span>
            <span class="step-complete">✓ Context building with identity and constraints</span>
            <span class="step-complete">✓ Multi-DMA ethical evaluation (Ethical, Common Sense, Domain)</span>
            <span class="step-complete">✓ LLM action selection with full transparency</span>
            <span class="step-complete">✓ Conscience validation with safety checks</span>
            <span class="step-complete">✓ Final action determination</span>
          </div>
        </div>
        
        <div class="timeline-arrow">↓</div>
        
        <h5>⚙️ Execution Phase Complete</h5>
        <div class="phase-summary execution">
          <div class="phase-steps">
            <span class="step-complete">✓ Handler initiation with validated parameters</span>
            <span class="step-complete">✓ Bus operations across distributed services</span>
            <span class="step-complete">✓ External service integration with boundary security</span>
            <span class="step-complete">✓ Response aggregation and processing</span>
            <span class="step-complete">✓ Handler completion with ${stepResult.handler_success ? 'success' : 'controlled failure'}</span>
          </div>
        </div>
      </div>
      
      <div class="ethical-principles-fulfilled">
        <h5>CIRIS Ethical Principles Demonstrated</h5>
        <div class="principles-completion">
          <div class="principle-complete">
            <span class="principle-icon">🎯</span>
            <div class="principle-info">
              <strong>Integrity</strong>
              <p>Complete transparency through all 15 processing steps with full auditability</p>
            </div>
          </div>
          <div class="principle-complete">
            <span class="principle-icon">🛡️</span>
            <div class="principle-info">
              <strong>Non-maleficence</strong>
              <p>Multi-layer conscience screening prevented harmful actions</p>
            </div>
          </div>
          <div class="principle-complete">
            <span class="principle-icon">🌟</span>
            <div class="principle-info">
              <strong>Beneficence</strong>
              <p>Action selection optimized for positive outcomes and user benefit</p>
            </div>
          </div>
          <div class="principle-complete">
            <span class="principle-icon">🤝</span>
            <div class="principle-info">
              <strong>Respect for Autonomy</strong>
              <p>Human oversight maintained with override capabilities throughout</p>
            </div>
          </div>
          <div class="principle-complete">
            <span class="principle-icon">⚖️</span>
            <div class="principle-info">
              <strong>Justice</strong>
              <p>Fair task prioritization and resource allocation demonstrated</p>
            </div>
          </div>
          <div class="principle-complete">
            <span class="principle-icon">🔄</span>
            <div class="principle-info">
              <strong>Adaptive Coherence (Meta-Goal M-1)</strong>
              <p>System demonstrated learning, adaptation, and sustainable operation</p>
            </div>
          </div>
        </div>
      </div>
      
      <div class="completion-metrics">
        <h5>Final Processing Metrics</h5>
        <div class="final-metrics-grid">
          <div class="final-metric">
            <span class="metric-label">Total Processing Time</span>
            <span class="metric-value">${stepResult.total_processing_time_ms}ms</span>
          </div>
          <div class="final-metric">
            <span class="metric-label">LLM Token Consumption</span>
            <span class="metric-value">${stepResult.total_tokens_used || 0} tokens</span>
          </div>
          <div class="final-metric">
            <span class="metric-label">Processing Steps Completed</span>
            <span class="metric-value">15/15 steps</span>
          </div>
          <div class="final-metric">
            <span class="metric-label">Ethical Validation</span>
            <span class="metric-value success">✓ Passed</span>
          </div>
          <div class="final-metric">
            <span class="metric-label">Handler Execution</span>
            <span class="metric-value ${stepResult.handler_success ? 'success' : 'controlled-failure'}">
              ${stepResult.handler_success ? '✓ Success' : '⚠ Controlled Failure'}
            </span>
          </div>
          <div class="final-metric">
            <span class="metric-label">System Continuity</span>
            <span class="metric-value ${stepResult.triggers_new_thoughts ? 'continuing' : 'complete'}">
              ${stepResult.triggers_new_thoughts ? '🔄 Continuing' : '✓ Complete'}
            </span>
          </div>
        </div>
      </div>
    </div>
  `;
}
```

**Demo Value**: The culminating demonstration of CIRIS's complete ethical processing pipeline - from initial task selection through final handler completion. This step showcases the full realization of all six ethical principles working in harmony, with complete transparency, robust safety mechanisms, and potential for sustainable continuous operation through cascade effects. Represents the ultimate expression of Meta-Goal M-1: sustainable adaptive coherence in action.

---

## Implementation Summary

This comprehensive guide provides the CIRISGUI Claude Code agent with detailed instructions for enhancing the GUI to display rich single-step debugging data across all 15 step points of the CIRIS ethical reasoning pipeline. Each step includes:

1. **Context Understanding**: Clear explanation of what happens at each step point
2. **Data Schema Awareness**: Complete mapping of available data structures
3. **Visual Enhancement Code**: Production-ready TypeScript for SVG visualizations and data panels
4. **Demo Value Articulation**: Explicit connection to CIRIS ethical principles and demo presentation goals

The visualizations demonstrate CIRIS's commitment to transparency, ethical reasoning, and sustainable AI operation, making the complete processing pipeline accessible for technical demonstrations, ethical auditing, and system understanding.

---
