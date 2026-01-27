package ai.ciris.mobile.shared.viewmodels

import ai.ciris.api.models.GraphScope
import ai.ciris.api.models.NodeType
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.ui.screens.graph.*
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * ViewModel for the Memory Graph visualization screen.
 *
 * Manages:
 * - Graph data loading from API
 * - Force simulation state
 * - Node/edge display state
 * - Filter state
 * - Viewport state
 */
class GraphMemoryViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "GraphMemoryViewModel"
        private const val SIMULATION_TICK_MS = 16L // ~60fps
    }

    // Graph display state
    private val _displayState = MutableStateFlow(GraphDisplayState())
    val displayState: StateFlow<GraphDisplayState> = _displayState.asStateFlow()

    // Filter state
    private val _filter = MutableStateFlow(GraphFilter())
    val filter: StateFlow<GraphFilter> = _filter.asStateFlow()

    // Stats
    private val _stats = MutableStateFlow(GraphStats())
    val stats: StateFlow<GraphStats> = _stats.asStateFlow()

    // Force simulation
    private val simulation = ForceSimulation()
    private var simulationJob: Job? = null

    // Canvas dimensions
    private var canvasWidth: Float = 800f
    private var canvasHeight: Float = 600f

    init {
        println("[$TAG] GraphMemoryViewModel created")
    }

    /**
     * Set canvas dimensions for layout calculations.
     */
    fun setCanvasSize(width: Float, height: Float) {
        canvasWidth = width
        canvasHeight = height
        println("[$TAG] Canvas size set to ${width}x${height}")
    }

    /**
     * Load graph data from API.
     */
    fun loadGraphData() {
        println("[$TAG] Loading graph data: hours=${_filter.value.hours}, scope=${_filter.value.scope}")

        viewModelScope.launch {
            _displayState.value = _displayState.value.copy(isLoading = true, error = null)

            try {
                // Always pass a scope - cross-scope edges are not supported
                val graphData = apiClient.getGraphData(
                    hours = _filter.value.hours,
                    scope = _filter.value.scope.value,
                    nodeType = null,
                    limit = 100
                )

                println("[$TAG] Loaded ${graphData.nodes.size} nodes, ${graphData.edges.size} edges")

                // Convert to display models
                val displayNodes = graphData.nodes.map { node ->
                    GraphNodeDisplay.fromGraphNode(node)
                }
                val displayEdges = graphData.edges.map { edge ->
                    GraphEdgeDisplay.fromGraphEdge(edge)
                }

                // Initialize positions
                simulation.initializePositions(displayNodes, canvasWidth, canvasHeight)

                // Calculate stats
                val nodesByType = displayNodes.groupBy { it.type }
                    .mapValues { it.value.size }
                val nodesByScope = displayNodes.groupBy { it.scope }
                    .mapValues { it.value.size }

                _stats.value = GraphStats(
                    totalNodes = displayNodes.size,
                    totalEdges = displayEdges.size,
                    nodesByType = nodesByType,
                    nodesByScope = nodesByScope
                )

                _displayState.value = _displayState.value.copy(
                    nodes = displayNodes,
                    edges = displayEdges,
                    isLoading = false,
                    error = null
                )

                // Start simulation
                startSimulation()

            } catch (e: Exception) {
                println("[$TAG] Failed to load graph data: ${e.message}")
                _displayState.value = _displayState.value.copy(
                    isLoading = false,
                    error = "Failed to load graph: ${e.message}"
                )
            }
        }
    }

    /**
     * Refresh data.
     */
    fun refresh() {
        loadGraphData()
    }

    /**
     * Update filter.
     */
    fun updateFilter(newFilter: GraphFilter) {
        _filter.value = newFilter
        loadGraphData()
    }

    /**
     * Change graph layout.
     */
    fun changeLayout(layout: GraphLayout) {
        stopSimulation()

        val nodes = _displayState.value.nodes.toMutableList()

        when (layout) {
            GraphLayout.FORCE -> {
                simulation.initializePositions(nodes, canvasWidth, canvasHeight)
                startSimulation()
            }
            GraphLayout.TIMELINE -> {
                ForceSimulation.applyTimelineLayout(nodes, canvasWidth, canvasHeight)
            }
            GraphLayout.HIERARCHY -> {
                ForceSimulation.applyHierarchyLayout(nodes, canvasWidth, canvasHeight)
            }
            GraphLayout.CIRCULAR -> {
                ForceSimulation.applyCircularLayout(nodes, canvasWidth, canvasHeight)
            }
        }

        _displayState.value = _displayState.value.copy(
            nodes = nodes,
            layout = layout
        )
    }

    /**
     * Select a node.
     */
    fun selectNode(nodeId: String?) {
        _displayState.value = _displayState.value.copy(selectedNodeId = nodeId)
    }

    /**
     * Update viewport (pan/zoom).
     */
    fun updateViewport(viewport: GraphViewport) {
        _displayState.value = _displayState.value.copy(viewport = viewport)
    }

    /**
     * Start dragging a node (pins it in place).
     */
    fun startNodeDrag(nodeId: String) {
        val nodes = _displayState.value.nodes.map { node ->
            if (node.id == nodeId) node.copy(fixed = true) else node
        }
        _displayState.value = _displayState.value.copy(nodes = nodes)

        // Reheat simulation
        if (_displayState.value.layout == GraphLayout.FORCE) {
            simulation.reheat()
        }
    }

    /**
     * Drag a node.
     */
    fun dragNode(nodeId: String, dx: Float, dy: Float) {
        val nodes = _displayState.value.nodes.map { node ->
            if (node.id == nodeId) {
                node.apply {
                    x += dx
                    y += dy
                }
            } else node
        }
        _displayState.value = _displayState.value.copy(nodes = nodes)
    }

    /**
     * End dragging a node.
     */
    fun endNodeDrag(nodeId: String) {
        val nodes = _displayState.value.nodes.map { node ->
            if (node.id == nodeId) node.copy(fixed = false) else node
        }
        _displayState.value = _displayState.value.copy(nodes = nodes)
    }

    /**
     * Start force simulation.
     */
    fun startSimulation() {
        if (simulationJob?.isActive == true) return
        if (_displayState.value.layout != GraphLayout.FORCE) return

        println("[$TAG] Starting force simulation")
        simulation.restart()

        _displayState.value = _displayState.value.copy(isSimulationRunning = true)

        simulationJob = viewModelScope.launch {
            while (isActive && simulation.isActive()) {
                val nodes = _displayState.value.nodes
                val edges = _displayState.value.edges
                val nodeMap = _displayState.value.nodeMap

                val shouldContinue = simulation.tick(nodes, edges, nodeMap)

                // Trigger recomposition
                _displayState.value = _displayState.value.copy(
                    nodes = nodes.toList()
                )

                if (!shouldContinue) {
                    println("[$TAG] Simulation stabilized")
                    break
                }

                delay(SIMULATION_TICK_MS)
            }

            _displayState.value = _displayState.value.copy(isSimulationRunning = false)
        }
    }

    /**
     * Stop force simulation.
     */
    fun stopSimulation() {
        println("[$TAG] Stopping simulation")
        simulation.stop()
        simulationJob?.cancel()
        simulationJob = null
        _displayState.value = _displayState.value.copy(isSimulationRunning = false)
    }

    override fun onCleared() {
        super.onCleared()
        stopSimulation()
    }
}
