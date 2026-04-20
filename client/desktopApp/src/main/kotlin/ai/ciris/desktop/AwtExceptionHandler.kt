package ai.ciris.desktop

/**
 * Fallback handler for exceptions that escape Swing/AWT event-dispatch
 * callbacks. Registered via `System.setProperty("sun.awt.exception.handler", ...)`
 * in [Main.main]. The JVM instantiates this class with a zero-arg
 * constructor on first need.
 *
 * Invoked via reflection; must have a single public `handle(Throwable)`
 * method. Returning without rethrowing keeps the event queue alive so
 * one rogue exception doesn't brick the whole UI — matches our mobile
 * story (zero ANRs on both app stores) for the desktop path.
 */
@Suppress("unused")
class AwtExceptionHandler {
    fun handle(t: Throwable) {
        System.err.println(
            "[AwtExceptionHandler] EDT threw ${t::class.qualifiedName}: ${t.message}"
        )
        t.printStackTrace(System.err)
    }
}
