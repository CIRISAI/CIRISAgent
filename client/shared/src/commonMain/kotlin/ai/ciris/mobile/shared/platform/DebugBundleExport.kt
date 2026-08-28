package ai.ciris.mobile.shared.platform

/**
 * Write a debug bundle somewhere the user can actually reach it, and return a
 * human-readable description of where it went (or null if it could not be
 * written).
 *
 * Deliberately "save", not "share". Two of the three call sites are screens the
 * user is stuck on — a login that cannot exchange a token, a startup that never
 * completes — and on those screens a share sheet can itself fail or be
 * unavailable. A file on disk with a path we can name is the thing a user can
 * still get to us over any channel.
 *
 * The returned string is shown verbatim, so it must be a path or a location a
 * person can act on, not a status word.
 */
expect fun saveDebugBundle(fileName: String, content: String): String?

/**
 * Put the bundle on the clipboard. Separate from [saveDebugBundle] because on a
 * phone that cannot write shared storage, copy-and-paste into a chat is the only
 * remaining route out.
 */
expect fun copyToClipboard(text: String): Boolean
