package ai.ciris.mobile

import android.app.Application
import ai.ciris.mobile.shared.platform.SecureStorage

/**
 * Application class for CIRIS KMP Android app
 * Initializes global components like SecureStorage
 */
class CIRISApplication : Application() {

    override fun onCreate() {
        super.onCreate()

        // Initialize SecureStorage with application context
        SecureStorage.setContext(this)
    }
}
