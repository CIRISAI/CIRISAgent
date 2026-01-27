package ai.ciris.mobile.shared.viewmodels

import ai.ciris.api.models.APIRole
import ai.ciris.api.models.UserDetail
import ai.ciris.api.models.UserSummary
import ai.ciris.api.models.WARole
import ai.ciris.mobile.shared.api.CIRISApiClient
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Filter options for the Users list.
 */
data class UsersFilter(
    val search: String = "",
    val authType: String? = null,
    val apiRole: APIRole? = null,
    val waRole: WARole? = null,
    val isActive: Boolean? = null
)

/**
 * Pagination state.
 */
data class UsersPagination(
    val page: Int = 1,
    val pageSize: Int = 20,
    val totalPages: Int = 0,
    val totalItems: Int = 0
)

/**
 * State for the Users screen.
 */
data class UsersScreenState(
    val users: List<UserSummary> = emptyList(),
    val selectedUser: UserDetail? = null,
    val filter: UsersFilter = UsersFilter(),
    val pagination: UsersPagination = UsersPagination(),
    val isLoading: Boolean = false,
    val isLoadingDetails: Boolean = false,
    val error: String? = null
)

/**
 * ViewModel for the Users screen.
 *
 * Features:
 * - Paginated user list from /v1/users
 * - Filtering by search, auth type, API role, WA role, active status
 * - User details view
 * - Role-based access (requires ADMIN+ to view)
 */
class UsersViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "UsersViewModel"
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // State
    private val _state = MutableStateFlow(UsersScreenState())
    val state: StateFlow<UsersScreenState> = _state.asStateFlow()

    init {
        logInfo("init", "UsersViewModel initialized - waiting for explicit refresh()")
    }

    /**
     * Refresh users list
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Refreshing users list")
        fetchUsers(resetPage = true)
    }

    /**
     * Update filter and refetch
     */
    fun updateFilter(newFilter: UsersFilter) {
        val method = "updateFilter"
        logInfo(method, "Filter changed: search=${newFilter.search}, authType=${newFilter.authType}, " +
                "apiRole=${newFilter.apiRole}, waRole=${newFilter.waRole}, isActive=${newFilter.isActive}")
        _state.update { it.copy(filter = newFilter) }
        fetchUsers(resetPage = true)
    }

    /**
     * Update search query
     */
    fun updateSearch(query: String) {
        val method = "updateSearch"
        logDebug(method, "Search: $query")
        _state.update { it.copy(filter = it.filter.copy(search = query)) }
        fetchUsers(resetPage = true)
    }

    /**
     * Go to a specific page
     */
    fun goToPage(page: Int) {
        val method = "goToPage"
        if (page < 1 || page > _state.value.pagination.totalPages) {
            logDebug(method, "Invalid page: $page")
            return
        }
        logInfo(method, "Going to page $page")
        _state.update {
            it.copy(pagination = it.pagination.copy(page = page))
        }
        fetchUsers(resetPage = false)
    }

    /**
     * Go to next page
     */
    fun nextPage() {
        val current = _state.value.pagination.page
        val total = _state.value.pagination.totalPages
        if (current < total) {
            goToPage(current + 1)
        }
    }

    /**
     * Go to previous page
     */
    fun previousPage() {
        val current = _state.value.pagination.page
        if (current > 1) {
            goToPage(current - 1)
        }
    }

    /**
     * Select a user to view details
     */
    fun selectUser(userId: String) {
        val method = "selectUser"
        logInfo(method, "Selecting user: $userId")

        viewModelScope.launch {
            _state.update { it.copy(isLoadingDetails = true, error = null) }

            try {
                val user = apiClient.getUser(userId)
                logInfo(method, "Loaded user details: id=${user.userId}, username=${user.username}")
                _state.update { it.copy(selectedUser = user, isLoadingDetails = false) }
            } catch (e: Exception) {
                logError(method, "Failed to load user: ${e::class.simpleName}: ${e.message}")
                _state.update {
                    it.copy(
                        isLoadingDetails = false,
                        error = "Failed to load user: ${e.message}"
                    )
                }
            }
        }
    }

    /**
     * Clear selected user
     */
    fun clearSelection() {
        val method = "clearSelection"
        logDebug(method, "Clearing user selection")
        _state.update { it.copy(selectedUser = null) }
    }

    /**
     * Clear error
     */
    fun clearError() {
        _state.update { it.copy(error = null) }
    }

    /**
     * Fetch users with current filter and pagination
     */
    private fun fetchUsers(resetPage: Boolean) {
        val method = "fetchUsers"

        viewModelScope.launch {
            val filter = _state.value.filter
            val pagination = if (resetPage) {
                _state.value.pagination.copy(page = 1)
            } else {
                _state.value.pagination
            }

            logDebug(method, "Fetching users: page=${pagination.page}, " +
                    "search=${filter.search}, authType=${filter.authType}, apiRole=${filter.apiRole}")

            _state.update { it.copy(isLoading = true, error = null, pagination = pagination) }

            try {
                val response = apiClient.listUsers(
                    page = pagination.page,
                    pageSize = pagination.pageSize,
                    search = filter.search.ifBlank { null },
                    authType = filter.authType,
                    apiRole = filter.apiRole,
                    waRole = filter.waRole,
                    isActive = filter.isActive
                )

                logInfo(method, "Loaded ${response.items.size} users (total: ${response.total}, page ${response.page}/${response.pages})")

                _state.update {
                    it.copy(
                        users = response.items,
                        pagination = UsersPagination(
                            page = response.page,
                            pageSize = response.pageSize,
                            totalPages = response.pages,
                            totalItems = response.total
                        ),
                        isLoading = false
                    )
                }
            } catch (e: Exception) {
                logError(method, "Failed to fetch users: ${e::class.simpleName}: ${e.message}")
                _state.update {
                    it.copy(
                        isLoading = false,
                        error = "Failed to load users: ${e.message}"
                    )
                }
            }
        }
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared")
        super.onCleared()
    }
}
