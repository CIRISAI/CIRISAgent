package ai.ciris.mobile.setup

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel

class SetupViewModel : ViewModel() {

    // Step 2: LLM
    private val _llmProvider = MutableLiveData<String>("OpenAI")
    val llmProvider: LiveData<String> = _llmProvider

    private val _llmApiKey = MutableLiveData<String>("")
    val llmApiKey: LiveData<String> = _llmApiKey

    // Step 3: Admin
    private val _adminPassword = MutableLiveData<String>("")
    val adminPassword: LiveData<String> = _adminPassword

    private val _adminPasswordConfirm = MutableLiveData<String>("")
    val adminPasswordConfirm: LiveData<String> = _adminPasswordConfirm

    // Step 4: Account
    private val _username = MutableLiveData<String>("")
    val username: LiveData<String> = _username

    private val _email = MutableLiveData<String>("")
    val email: LiveData<String> = _email

    private val _userPassword = MutableLiveData<String>("")
    val userPassword: LiveData<String> = _userPassword

    // Setters
    fun setLlmProvider(provider: String) { _llmProvider.value = provider }
    fun setLlmApiKey(key: String) { _llmApiKey.value = key }
    fun setAdminPassword(password: String) { _adminPassword.value = password }
    fun setAdminPasswordConfirm(password: String) { _adminPasswordConfirm.value = password }
    fun setUsername(username: String) { _username.value = username }
    fun setEmail(email: String) { _email.value = email }
    fun setUserPassword(password: String) { _userPassword.value = password }
}
