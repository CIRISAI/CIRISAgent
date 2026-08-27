package ai.ciris.mobile.shared.platform

import java.io.File

actual fun isManagedDeployment(): Boolean =
    File("/app/agent").isDirectory || File("/app/.ciris_manager").isDirectory
