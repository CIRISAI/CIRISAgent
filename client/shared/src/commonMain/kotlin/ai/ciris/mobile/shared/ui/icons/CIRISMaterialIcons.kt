package ai.ciris.mobile.shared.ui.icons

import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp

/**
 * Drop-in replacements for Material Design extended icons.
 * Eliminates the 113MB compose.materialIconsExtended dependency.
 * All icons use 24dp/24vp standard Material sizing.
 */
object CIRISMaterialIcons {
    object Filled
    val Default = Filled
}

// ─── Visibility ─────────────────────────────────────────────────────────────────

private var _visibility: ImageVector? = null
val CIRISMaterialIcons.Filled.Visibility: ImageVector
    get() {
        if (_visibility != null) return _visibility!!
        _visibility = ImageVector.Builder(
            name = "Filled.Visibility",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 4.5f)
                curveTo(7f, 4.5f, 2.73f, 7.61f, 1f, 12f)
                curveToRelative(1.73f, 4.39f, 6f, 7.5f, 11f, 7.5f)
                reflectiveCurveToRelative(9.27f, -3.11f, 11f, -7.5f)
                curveToRelative(-1.73f, -4.39f, -6f, -7.5f, -11f, -7.5f)
                close()
                moveTo(12f, 17f)
                curveToRelative(-2.76f, 0f, -5f, -2.24f, -5f, -5f)
                reflectiveCurveToRelative(2.24f, -5f, 5f, -5f)
                reflectiveCurveToRelative(5f, 2.24f, 5f, 5f)
                reflectiveCurveToRelative(-2.24f, 5f, -5f, 5f)
                close()
                moveTo(12f, 9f)
                curveToRelative(-1.66f, 0f, -3f, 1.34f, -3f, 3f)
                reflectiveCurveToRelative(1.34f, 3f, 3f, 3f)
                reflectiveCurveToRelative(3f, -1.34f, 3f, -3f)
                reflectiveCurveToRelative(-1.34f, -3f, -3f, -3f)
                close()
            }
        }.build()
        return _visibility!!
    }

// ─── VisibilityOff ──────────────────────────────────────────────────────────────

private var _visibilityOff: ImageVector? = null
val CIRISMaterialIcons.Filled.VisibilityOff: ImageVector
    get() {
        if (_visibilityOff != null) return _visibilityOff!!
        _visibilityOff = ImageVector.Builder(
            name = "Filled.VisibilityOff",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 7f)
                curveToRelative(2.76f, 0f, 5f, 2.24f, 5f, 5f)
                curveToRelative(0f, 0.65f, -0.13f, 1.26f, -0.36f, 1.83f)
                lineToRelative(2.92f, 2.92f)
                curveToRelative(1.51f, -1.26f, 2.7f, -2.89f, 3.43f, -4.75f)
                curveToRelative(-1.73f, -4.39f, -6f, -7.5f, -11f, -7.5f)
                curveToRelative(-1.4f, 0f, -2.74f, 0.25f, -3.98f, 0.7f)
                lineToRelative(2.16f, 2.16f)
                curveTo(10.74f, 7.13f, 11.35f, 7f, 12f, 7f)
                close()
                moveTo(2f, 4.27f)
                lineToRelative(2.28f, 2.28f)
                lineToRelative(0.46f, 0.46f)
                curveTo(3.08f, 8.3f, 1.78f, 10.02f, 1f, 12f)
                curveToRelative(1.73f, 4.39f, 6f, 7.5f, 11f, 7.5f)
                curveToRelative(1.55f, 0f, 3.03f, -0.3f, 4.38f, -0.84f)
                lineToRelative(0.42f, 0.42f)
                lineTo(19.73f, 22f)
                lineTo(21f, 20.73f)
                lineTo(3.27f, 3f)
                lineTo(2f, 4.27f)
                close()
                moveTo(7.53f, 9.8f)
                lineToRelative(1.55f, 1.55f)
                curveToRelative(-0.05f, 0.21f, -0.08f, 0.43f, -0.08f, 0.65f)
                curveToRelative(0f, 1.66f, 1.34f, 3f, 3f, 3f)
                curveToRelative(0.22f, 0f, 0.44f, -0.03f, 0.65f, -0.08f)
                lineToRelative(1.55f, 1.55f)
                curveToRelative(-0.67f, 0.33f, -1.41f, 0.53f, -2.2f, 0.53f)
                curveToRelative(-2.76f, 0f, -5f, -2.24f, -5f, -5f)
                curveToRelative(0f, -0.79f, 0.2f, -1.53f, 0.53f, -2.2f)
                close()
                moveTo(11.84f, 9.02f)
                lineToRelative(3.15f, 3.15f)
                lineToRelative(0.02f, -0.16f)
                curveToRelative(0f, -1.66f, -1.34f, -3f, -3f, -3f)
                lineToRelative(-0.17f, 0.01f)
                close()
            }
        }.build()
        return _visibilityOff!!
    }

// ─── History ────────────────────────────────────────────────────────────────────

private var _history: ImageVector? = null
val CIRISMaterialIcons.Filled.History: ImageVector
    get() {
        if (_history != null) return _history!!
        _history = ImageVector.Builder(
            name = "Filled.History",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(13f, 3f)
                curveToRelative(-4.97f, 0f, -9f, 4.03f, -9f, 9f)
                horizontalLineTo(1f)
                lineToRelative(3.89f, 3.89f)
                lineToRelative(0.07f, 0.14f)
                lineTo(9f, 12f)
                horizontalLineTo(6f)
                curveToRelative(0f, -3.87f, 3.13f, -7f, 7f, -7f)
                reflectiveCurveToRelative(7f, 3.13f, 7f, 7f)
                reflectiveCurveToRelative(-3.13f, 7f, -7f, 7f)
                curveToRelative(-1.93f, 0f, -3.68f, -0.79f, -4.94f, -2.06f)
                lineToRelative(-1.42f, 1.42f)
                curveTo(8.27f, 19.99f, 10.51f, 21f, 13f, 21f)
                curveToRelative(4.97f, 0f, 9f, -4.03f, 9f, -9f)
                reflectiveCurveToRelative(-4.03f, -9f, -9f, -9f)
                close()
                moveTo(12f, 8f)
                verticalLineToRelative(5f)
                lineToRelative(4.28f, 2.54f)
                lineToRelative(0.72f, -1.21f)
                lineToRelative(-3.5f, -2.08f)
                verticalLineTo(8f)
                horizontalLineTo(12f)
                close()
            }
        }.build()
        return _history!!
    }

// ─── Lightbulb ──────────────────────────────────────────────────────────────────

private var _lightbulb: ImageVector? = null
val CIRISMaterialIcons.Filled.Lightbulb: ImageVector
    get() {
        if (_lightbulb != null) return _lightbulb!!
        _lightbulb = ImageVector.Builder(
            name = "Filled.Lightbulb",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(9f, 21f)
                curveToRelative(0f, 0.5f, 0.4f, 1f, 1f, 1f)
                horizontalLineToRelative(4f)
                curveToRelative(0.6f, 0f, 1f, -0.5f, 1f, -1f)
                verticalLineToRelative(-1f)
                horizontalLineTo(9f)
                verticalLineToRelative(1f)
                close()
                moveTo(12f, 2f)
                curveTo(8.1f, 2f, 5f, 5.1f, 5f, 9f)
                curveToRelative(0f, 2.4f, 1.2f, 4.5f, 3f, 5.7f)
                verticalLineTo(17f)
                curveToRelative(0f, 0.5f, 0.4f, 1f, 1f, 1f)
                horizontalLineToRelative(6f)
                curveToRelative(0.6f, 0f, 1f, -0.5f, 1f, -1f)
                verticalLineToRelative(-2.3f)
                curveToRelative(1.8f, -1.3f, 3f, -3.4f, 3f, -5.7f)
                curveToRelative(0f, -3.9f, -3.1f, -7f, -7f, -7f)
                close()
            }
        }.build()
        return _lightbulb!!
    }

// ─── Schedule ───────────────────────────────────────────────────────────────────

private var _schedule: ImageVector? = null
val CIRISMaterialIcons.Filled.Schedule: ImageVector
    get() {
        if (_schedule != null) return _schedule!!
        _schedule = ImageVector.Builder(
            name = "Filled.Schedule",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12.5f, 7f)
                horizontalLineTo(11f)
                verticalLineToRelative(6f)
                lineToRelative(5.25f, 3.15f)
                lineToRelative(0.75f, -1.23f)
                lineToRelative(-4.5f, -2.67f)
                close()
            }
        }.build()
        return _schedule!!
    }

// ─── Error ──────────────────────────────────────────────────────────────────────

private var _error: ImageVector? = null
val CIRISMaterialIcons.Filled.Error: ImageVector
    get() {
        if (_error != null) return _error!!
        _error = ImageVector.Builder(
            name = "Filled.Error",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 2f)
                curveTo(6.48f, 2f, 2f, 6.48f, 2f, 12f)
                reflectiveCurveToRelative(4.48f, 10f, 10f, 10f)
                reflectiveCurveToRelative(10f, -4.48f, 10f, -10f)
                reflectiveCurveTo(17.52f, 2f, 12f, 2f)
                close()
                moveTo(13f, 17f)
                horizontalLineToRelative(-2f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(2f)
                verticalLineToRelative(2f)
                close()
                moveTo(13f, 13f)
                horizontalLineToRelative(-2f)
                verticalLineTo(7f)
                horizontalLineToRelative(2f)
                verticalLineToRelative(6f)
                close()
            }
        }.build()
        return _error!!
    }

// ─── Shield ─────────────────────────────────────────────────────────────────────

private var _shield: ImageVector? = null
val CIRISMaterialIcons.Filled.Shield: ImageVector
    get() {
        if (_shield != null) return _shield!!
        _shield = ImageVector.Builder(
            name = "Filled.Shield",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 1f)
                lineTo(3f, 5f)
                verticalLineToRelative(6f)
                curveToRelative(0f, 5.55f, 3.84f, 10.74f, 9f, 12f)
                curveToRelative(5.16f, -1.26f, 9f, -6.45f, 9f, -12f)
                verticalLineTo(5f)
                lineToRelative(-9f, -4f)
                close()
            }
        }.build()
        return _shield!!
    }

// ─── Security ───────────────────────────────────────────────────────────────────

private var _security: ImageVector? = null
val CIRISMaterialIcons.Filled.Security: ImageVector
    get() {
        if (_security != null) return _security!!
        _security = ImageVector.Builder(
            name = "Filled.Security",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 1f)
                lineTo(3f, 5f)
                verticalLineToRelative(6f)
                curveToRelative(0f, 5.55f, 3.84f, 10.74f, 9f, 12f)
                curveToRelative(5.16f, -1.26f, 9f, -6.45f, 9f, -12f)
                verticalLineTo(5f)
                lineToRelative(-9f, -4f)
                close()
                moveTo(12f, 11.99f)
                horizontalLineToRelative(7f)
                curveToRelative(-0.53f, 4.12f, -3.28f, 7.79f, -7f, 8.94f)
                verticalLineTo(12f)
                horizontalLineTo(5f)
                verticalLineTo(6.3f)
                lineToRelative(7f, -3.11f)
                verticalLineToRelative(8.8f)
                close()
            }
        }.build()
        return _security!!
    }

// ─── Sync ───────────────────────────────────────────────────────────────────────

private var _sync: ImageVector? = null
val CIRISMaterialIcons.Filled.Sync: ImageVector
    get() {
        if (_sync != null) return _sync!!
        _sync = ImageVector.Builder(
            name = "Filled.Sync",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 4f)
                verticalLineTo(1f)
                lineTo(8f, 5f)
                lineToRelative(4f, 4f)
                verticalLineTo(6f)
                curveToRelative(3.31f, 0f, 6f, 2.69f, 6f, 6f)
                curveToRelative(0f, 1.01f, -0.25f, 1.97f, -0.7f, 2.8f)
                lineToRelative(1.46f, 1.46f)
                curveTo(19.54f, 15.03f, 20f, 13.57f, 20f, 12f)
                curveToRelative(0f, -4.42f, -3.58f, -8f, -8f, -8f)
                close()
                moveTo(12f, 18f)
                curveToRelative(-3.31f, 0f, -6f, -2.69f, -6f, -6f)
                curveToRelative(0f, -1.01f, 0.25f, -1.97f, 0.7f, -2.8f)
                lineTo(5.24f, 7.74f)
                curveTo(4.46f, 8.97f, 4f, 10.43f, 4f, 12f)
                curveToRelative(0f, 4.42f, 3.58f, 8f, 8f, 8f)
                verticalLineToRelative(3f)
                lineToRelative(4f, -4f)
                lineToRelative(-4f, -4f)
                verticalLineToRelative(3f)
                close()
            }
        }.build()
        return _sync!!
    }

// ─── CloudOff ───────────────────────────────────────────────────────────────────

private var _cloudOff: ImageVector? = null
val CIRISMaterialIcons.Filled.CloudOff: ImageVector
    get() {
        if (_cloudOff != null) return _cloudOff!!
        _cloudOff = ImageVector.Builder(
            name = "Filled.CloudOff",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(19.35f, 10.04f)
                curveTo(18.67f, 6.59f, 15.64f, 4f, 12f, 4f)
                curveToRelative(-1.48f, 0f, -2.85f, 0.43f, -4.01f, 1.17f)
                lineToRelative(1.46f, 1.46f)
                curveTo(10.21f, 6.23f, 11.08f, 6f, 12f, 6f)
                curveToRelative(3.04f, 0f, 5.5f, 2.46f, 5.5f, 5.5f)
                verticalLineToRelative(0.5f)
                horizontalLineTo(19f)
                curveToRelative(1.66f, 0f, 3f, 1.34f, 3f, 3f)
                curveToRelative(0f, 1.13f, -0.64f, 2.11f, -1.56f, 2.62f)
                lineToRelative(1.45f, 1.45f)
                curveTo(23.16f, 18.16f, 24f, 16.68f, 24f, 15f)
                curveToRelative(0f, -2.64f, -2.05f, -4.78f, -4.65f, -4.96f)
                close()
                moveTo(3f, 5.27f)
                lineToRelative(2.75f, 2.74f)
                curveTo(2.56f, 8.15f, 0f, 10.77f, 0f, 14f)
                curveToRelative(0f, 3.31f, 2.69f, 6f, 6f, 6f)
                horizontalLineToRelative(11.73f)
                lineToRelative(2f, 2f)
                lineTo(21f, 20.73f)
                lineTo(4.27f, 4f)
                lineTo(3f, 5.27f)
                close()
                moveTo(7.73f, 10f)
                lineToRelative(8f, 8f)
                horizontalLineTo(6f)
                curveToRelative(-2.21f, 0f, -4f, -1.79f, -4f, -4f)
                reflectiveCurveToRelative(1.79f, -4f, 4f, -4f)
                horizontalLineToRelative(1.73f)
                close()
            }
        }.build()
        return _cloudOff!!
    }

// ─── ExpandLess ─────────────────────────────────────────────────────────────────

private var _expandLess: ImageVector? = null
val CIRISMaterialIcons.Filled.ExpandLess: ImageVector
    get() {
        if (_expandLess != null) return _expandLess!!
        _expandLess = ImageVector.Builder(
            name = "Filled.ExpandLess",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 8f)
                lineToRelative(-6f, 6f)
                lineToRelative(1.41f, 1.41f)
                lineTo(12f, 10.83f)
                lineToRelative(4.59f, 4.58f)
                lineTo(18f, 14f)
                close()
            }
        }.build()
        return _expandLess!!
    }

// ─── ExpandMore ─────────────────────────────────────────────────────────────────

private var _expandMore: ImageVector? = null
val CIRISMaterialIcons.Filled.ExpandMore: ImageVector
    get() {
        if (_expandMore != null) return _expandMore!!
        _expandMore = ImageVector.Builder(
            name = "Filled.ExpandMore",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(16.59f, 8.59f)
                lineTo(12f, 13.17f)
                lineTo(7.41f, 8.59f)
                lineTo(6f, 10f)
                lineToRelative(6f, 6f)
                lineToRelative(6f, -6f)
                close()
            }
        }.build()
        return _expandMore!!
    }

// ─── Description ────────────────────────────────────────────────────────────────

private var _description: ImageVector? = null
val CIRISMaterialIcons.Filled.Description: ImageVector
    get() {
        if (_description != null) return _description!!
        _description = ImageVector.Builder(
            name = "Filled.Description",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(14f, 2f)
                horizontalLineTo(6f)
                curveToRelative(-1.1f, 0f, -1.99f, 0.9f, -1.99f, 2f)
                lineTo(4f, 20f)
                curveToRelative(0f, 1.1f, 0.89f, 2f, 1.99f, 2f)
                horizontalLineTo(18f)
                curveToRelative(1.1f, 0f, 2f, -0.9f, 2f, -2f)
                verticalLineTo(8f)
                lineToRelative(-6f, -6f)
                close()
                moveTo(16f, 18f)
                horizontalLineTo(8f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(8f)
                verticalLineToRelative(2f)
                close()
                moveTo(16f, 14f)
                horizontalLineTo(8f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(8f)
                verticalLineToRelative(2f)
                close()
                moveTo(13f, 9f)
                verticalLineTo(3.5f)
                lineTo(18.5f, 9f)
                horizontalLineTo(13f)
                close()
            }
        }.build()
        return _description!!
    }

// ─── Analytics ──────────────────────────────────────────────────────────────────

private var _analytics: ImageVector? = null
val CIRISMaterialIcons.Filled.Analytics: ImageVector
    get() {
        if (_analytics != null) return _analytics!!
        _analytics = ImageVector.Builder(
            name = "Filled.Analytics",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(19f, 3f)
                horizontalLineTo(5f)
                curveToRelative(-1.1f, 0f, -2f, 0.9f, -2f, 2f)
                verticalLineToRelative(14f)
                curveToRelative(0f, 1.1f, 0.9f, 2f, 2f, 2f)
                horizontalLineToRelative(14f)
                curveToRelative(1.1f, 0f, 2f, -0.9f, 2f, -2f)
                verticalLineTo(5f)
                curveToRelative(0f, -1.1f, -0.9f, -2f, -2f, -2f)
                close()
                moveTo(9f, 17f)
                horizontalLineTo(7f)
                verticalLineToRelative(-5f)
                horizontalLineToRelative(2f)
                verticalLineToRelative(5f)
                close()
                moveTo(13f, 17f)
                horizontalLineToRelative(-2f)
                verticalLineToRelative(-3f)
                horizontalLineToRelative(2f)
                verticalLineToRelative(3f)
                close()
                moveTo(13f, 12f)
                horizontalLineToRelative(-2f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(2f)
                verticalLineToRelative(2f)
                close()
                moveTo(17f, 17f)
                horizontalLineToRelative(-2f)
                verticalLineTo(7f)
                horizontalLineToRelative(2f)
                verticalLineToRelative(10f)
                close()
            }
        }.build()
        return _analytics!!
    }

// ─── Tune ───────────────────────────────────────────────────────────────────────

private var _tune: ImageVector? = null
val CIRISMaterialIcons.Filled.Tune: ImageVector
    get() {
        if (_tune != null) return _tune!!
        _tune = ImageVector.Builder(
            name = "Filled.Tune",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(3f, 17f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(6f)
                verticalLineToRelative(-2f)
                horizontalLineTo(3f)
                close()
                moveTo(3f, 5f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(10f)
                verticalLineTo(5f)
                horizontalLineTo(3f)
                close()
                moveTo(13f, 21f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(8f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(-8f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(-2f)
                verticalLineToRelative(6f)
                horizontalLineToRelative(2f)
                close()
                moveTo(7f, 9f)
                verticalLineToRelative(2f)
                horizontalLineTo(3f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(4f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(2f)
                verticalLineTo(9f)
                horizontalLineTo(7f)
                close()
                moveTo(21f, 13f)
                verticalLineToRelative(-2f)
                horizontalLineTo(11f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(10f)
                close()
                moveTo(15f, 9f)
                horizontalLineToRelative(2f)
                verticalLineTo(7f)
                horizontalLineToRelative(4f)
                verticalLineTo(5f)
                horizontalLineToRelative(-4f)
                verticalLineTo(3f)
                horizontalLineToRelative(-2f)
                verticalLineToRelative(6f)
                close()
            }
        }.build()
        return _tune!!
    }

// ─── Construction ───────────────────────────────────────────────────────────────

private var _construction: ImageVector? = null
val CIRISMaterialIcons.Filled.Construction: ImageVector
    get() {
        if (_construction != null) return _construction!!
        _construction = ImageVector.Builder(
            name = "Filled.Construction",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(17.5f, 10f)
                curveToRelative(1.93f, 0f, 3.5f, -1.57f, 3.5f, -3.5f)
                curveToRelative(0f, -0.58f, -0.16f, -1.12f, -0.41f, -1.6f)
                lineToRelative(-2.7f, 2.7f)
                lineTo(16.4f, 6.11f)
                lineToRelative(2.7f, -2.7f)
                curveTo(18.62f, 3.16f, 18.08f, 3f, 17.5f, 3f)
                curveTo(15.57f, 3f, 14f, 4.57f, 14f, 6.5f)
                curveToRelative(0f, 0.41f, 0.08f, 0.8f, 0.21f, 1.16f)
                lineToRelative(-1.85f, 1.85f)
                lineToRelative(-1.78f, -1.78f)
                lineToRelative(0.71f, -0.71f)
                lineTo(9.88f, 5.61f)
                lineTo(12f, 3.49f)
                curveToRelative(-1.17f, -1.17f, -3.07f, -1.17f, -4.24f, 0f)
                lineTo(4.22f, 7.03f)
                lineToRelative(1.41f, 1.41f)
                horizontalLineTo(2.81f)
                lineTo(2.1f, 9.15f)
                lineToRelative(3.54f, 3.54f)
                lineToRelative(0.71f, -0.71f)
                verticalLineTo(9.15f)
                lineToRelative(1.41f, 1.41f)
                lineToRelative(0.71f, -0.71f)
                lineToRelative(1.78f, 1.78f)
                lineToRelative(-7.41f, 7.41f)
                lineToRelative(2.12f, 2.12f)
                lineTo(16.34f, 9.79f)
                curveTo(16.7f, 9.92f, 17.09f, 10f, 17.5f, 10f)
                close()
            }
        }.build()
        return _construction!!
    }

// ─── Psychology ─────────────────────────────────────────────────────────────────

private var _psychology: ImageVector? = null
val CIRISMaterialIcons.Filled.Psychology: ImageVector
    get() {
        if (_psychology != null) return _psychology!!
        _psychology = ImageVector.Builder(
            name = "Filled.Psychology",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(13f, 3f)
                curveTo(9.25f, 3f, 6.2f, 5.94f, 6.02f, 9.64f)
                lineTo(4.1f, 12.2f)
                curveTo(3.85f, 12.53f, 4.09f, 13f, 4.5f, 13f)
                horizontalLineTo(6f)
                verticalLineToRelative(3f)
                curveToRelative(0f, 1.1f, 0.9f, 2f, 2f, 2f)
                horizontalLineToRelative(1f)
                verticalLineToRelative(3f)
                horizontalLineToRelative(7f)
                verticalLineToRelative(-4.68f)
                curveToRelative(2.36f, -1.12f, 4f, -3.53f, 4f, -6.32f)
                curveTo(20f, 6.13f, 16.87f, 3f, 13f, 3f)
                close()
                moveTo(16f, 10f)
                curveToRelative(0f, 0.13f, -0.01f, 0.26f, -0.02f, 0.39f)
                lineToRelative(0.83f, 0.66f)
                curveToRelative(0.08f, 0.06f, 0.1f, 0.16f, 0.05f, 0.25f)
                lineToRelative(-0.8f, 1.39f)
                curveToRelative(-0.05f, 0.09f, -0.16f, 0.12f, -0.24f, 0.09f)
                lineToRelative(-0.99f, -0.4f)
                curveToRelative(-0.21f, 0.16f, -0.43f, 0.29f, -0.67f, 0.39f)
                lineTo(14f, 13.83f)
                curveToRelative(-0.01f, 0.1f, -0.1f, 0.17f, -0.2f, 0.17f)
                horizontalLineToRelative(-1.6f)
                curveToRelative(-0.1f, 0f, -0.18f, -0.07f, -0.2f, -0.17f)
                lineToRelative(-0.15f, -1.06f)
                curveToRelative(-0.25f, -0.1f, -0.47f, -0.23f, -0.68f, -0.39f)
                lineToRelative(-0.99f, 0.4f)
                curveToRelative(-0.09f, 0.03f, -0.2f, 0f, -0.25f, -0.09f)
                lineToRelative(-0.8f, -1.39f)
                curveToRelative(-0.05f, -0.08f, -0.03f, -0.19f, 0.05f, -0.25f)
                lineToRelative(0.84f, -0.66f)
                curveTo(10.01f, 10.26f, 10f, 10.13f, 10f, 10f)
                curveToRelative(0f, -0.13f, 0.02f, -0.27f, 0.04f, -0.39f)
                lineTo(9.19f, 8.95f)
                curveToRelative(-0.08f, -0.06f, -0.1f, -0.16f, -0.05f, -0.26f)
                lineToRelative(0.8f, -1.38f)
                curveToRelative(0.05f, -0.09f, 0.15f, -0.12f, 0.24f, -0.09f)
                lineToRelative(1f, 0.4f)
                curveToRelative(0.2f, -0.15f, 0.43f, -0.29f, 0.67f, -0.39f)
                lineToRelative(0.15f, -1.06f)
                curveTo(12.02f, 6.07f, 12.1f, 6f, 12.2f, 6f)
                horizontalLineToRelative(1.6f)
                curveToRelative(0.1f, 0f, 0.18f, 0.07f, 0.2f, 0.17f)
                lineToRelative(0.15f, 1.06f)
                curveToRelative(0.24f, 0.1f, 0.46f, 0.23f, 0.67f, 0.39f)
                lineToRelative(1f, -0.4f)
                curveToRelative(0.09f, -0.03f, 0.2f, 0f, 0.24f, 0.09f)
                lineToRelative(0.8f, 1.38f)
                curveToRelative(0.05f, 0.09f, 0.03f, 0.2f, -0.05f, 0.26f)
                lineToRelative(-0.85f, 0.66f)
                curveTo(15.99f, 9.73f, 16f, 9.86f, 16f, 10f)
                close()
            }
        }.build()
        return _psychology!!
    }

// ─── CameraAlt ──────────────────────────────────────────────────────────────────

private var _cameraAlt: ImageVector? = null
val CIRISMaterialIcons.Filled.CameraAlt: ImageVector
    get() {
        if (_cameraAlt != null) return _cameraAlt!!
        _cameraAlt = ImageVector.Builder(
            name = "Filled.CameraAlt",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(9f, 2f)
                lineTo(7.17f, 4f)
                horizontalLineTo(4f)
                curveToRelative(-1.1f, 0f, -2f, 0.9f, -2f, 2f)
                verticalLineToRelative(12f)
                curveToRelative(0f, 1.1f, 0.9f, 2f, 2f, 2f)
                horizontalLineToRelative(16f)
                curveToRelative(1.1f, 0f, 2f, -0.9f, 2f, -2f)
                verticalLineTo(6f)
                curveToRelative(0f, -1.1f, -0.9f, -2f, -2f, -2f)
                horizontalLineToRelative(-3.17f)
                lineTo(15f, 2f)
                horizontalLineTo(9f)
                close()
                moveTo(12f, 17f)
                curveToRelative(-2.76f, 0f, -5f, -2.24f, -5f, -5f)
                reflectiveCurveToRelative(2.24f, -5f, 5f, -5f)
                reflectiveCurveToRelative(5f, 2.24f, 5f, 5f)
                reflectiveCurveToRelative(-2.24f, 5f, -5f, 5f)
                close()
            }
        }.build()
        return _cameraAlt!!
    }

// ─── Insights ───────────────────────────────────────────────────────────────────

private var _insights: ImageVector? = null
val CIRISMaterialIcons.Filled.Insights: ImageVector
    get() {
        if (_insights != null) return _insights!!
        _insights = ImageVector.Builder(
            name = "Filled.Insights",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(21f, 8f)
                curveToRelative(-1.45f, 0f, -2.26f, 1.44f, -1.93f, 2.51f)
                lineToRelative(-3.55f, 3.56f)
                curveToRelative(-0.3f, -0.09f, -0.74f, -0.09f, -1.04f, 0f)
                lineToRelative(-2.55f, -2.55f)
                curveTo(12.27f, 10.45f, 11.46f, 9f, 10f, 9f)
                curveToRelative(-1.45f, 0f, -2.27f, 1.44f, -1.93f, 2.52f)
                lineToRelative(-4.56f, 4.55f)
                curveTo(2.44f, 15.74f, 1f, 16.55f, 1f, 18f)
                curveToRelative(0f, 1.1f, 0.9f, 2f, 2f, 2f)
                curveToRelative(1.45f, 0f, 2.26f, -1.44f, 1.93f, -2.51f)
                lineToRelative(4.55f, -4.56f)
                curveToRelative(0.3f, 0.09f, 0.74f, 0.09f, 1.04f, 0f)
                lineToRelative(2.55f, 2.55f)
                curveTo(12.73f, 16.55f, 13.54f, 18f, 15f, 18f)
                curveToRelative(1.45f, 0f, 2.27f, -1.44f, 1.93f, -2.52f)
                lineToRelative(3.56f, -3.55f)
                curveTo(21.56f, 12.26f, 23f, 11.45f, 23f, 10f)
                curveTo(23f, 8.9f, 22.1f, 8f, 21f, 8f)
                close()
            }
        }.build()
        return _insights!!
    }

// ─── BugReport ──────────────────────────────────────────────────────────────────

private var _bugReport: ImageVector? = null
val CIRISMaterialIcons.Filled.BugReport: ImageVector
    get() {
        if (_bugReport != null) return _bugReport!!
        _bugReport = ImageVector.Builder(
            name = "Filled.BugReport",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(20f, 8f)
                horizontalLineToRelative(-2.81f)
                curveToRelative(-0.45f, -0.78f, -1.07f, -1.45f, -1.82f, -1.96f)
                lineTo(17f, 4.41f)
                lineTo(15.59f, 3f)
                lineToRelative(-2.17f, 2.17f)
                curveTo(12.96f, 5.06f, 12.49f, 5f, 12f, 5f)
                curveToRelative(-0.49f, 0f, -0.96f, 0.06f, -1.41f, 0.17f)
                lineTo(8.41f, 3f)
                lineTo(7f, 4.41f)
                lineToRelative(1.62f, 1.63f)
                curveTo(7.88f, 6.55f, 7.26f, 7.22f, 6.81f, 8f)
                horizontalLineTo(4f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(2.09f)
                curveToRelative(-0.05f, 0.33f, -0.09f, 0.66f, -0.09f, 1f)
                verticalLineToRelative(1f)
                horizontalLineTo(4f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(2f)
                verticalLineToRelative(1f)
                curveToRelative(0f, 0.34f, 0.04f, 0.67f, 0.09f, 1f)
                horizontalLineTo(4f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(2.81f)
                curveToRelative(1.04f, 1.79f, 2.97f, 3f, 5.19f, 3f)
                reflectiveCurveToRelative(4.15f, -1.21f, 5.19f, -3f)
                horizontalLineTo(20f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(-2.09f)
                curveToRelative(0.05f, -0.33f, 0.09f, -0.66f, 0.09f, -1f)
                verticalLineToRelative(-1f)
                horizontalLineToRelative(2f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(-2f)
                verticalLineToRelative(-1f)
                curveToRelative(0f, -0.34f, -0.04f, -0.67f, -0.09f, -1f)
                horizontalLineTo(20f)
                verticalLineTo(8f)
                close()
                moveTo(14f, 16f)
                horizontalLineToRelative(-4f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(4f)
                verticalLineToRelative(2f)
                close()
                moveTo(14f, 12f)
                horizontalLineToRelative(-4f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(4f)
                verticalLineToRelative(2f)
                close()
            }
        }.build()
        return _bugReport!!
    }

// ─── RadioButtonUnchecked ───────────────────────────────────────────────────────

private var _radioButtonUnchecked: ImageVector? = null
val CIRISMaterialIcons.Filled.RadioButtonUnchecked: ImageVector
    get() {
        if (_radioButtonUnchecked != null) return _radioButtonUnchecked!!
        _radioButtonUnchecked = ImageVector.Builder(
            name = "Filled.RadioButtonUnchecked",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 2f)
                curveTo(6.48f, 2f, 2f, 6.48f, 2f, 12f)
                reflectiveCurveToRelative(4.48f, 10f, 10f, 10f)
                reflectiveCurveToRelative(10f, -4.48f, 10f, -10f)
                reflectiveCurveTo(17.52f, 2f, 12f, 2f)
                close()
                moveTo(12f, 20f)
                curveToRelative(-4.42f, 0f, -8f, -3.58f, -8f, -8f)
                reflectiveCurveToRelative(3.58f, -8f, 8f, -8f)
                reflectiveCurveToRelative(8f, 3.58f, 8f, 8f)
                reflectiveCurveToRelative(-3.58f, 8f, -8f, 8f)
                close()
            }
        }.build()
        return _radioButtonUnchecked!!
    }

// ─── Hub ────────────────────────────────────────────────────────────────────────

private var _hub: ImageVector? = null
val CIRISMaterialIcons.Filled.Hub: ImageVector
    get() {
        if (_hub != null) return _hub!!
        _hub = ImageVector.Builder(
            name = "Filled.Hub",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(8.4f, 18.2f)
                curveTo(8.78f, 18.7f, 9f, 19.32f, 9f, 20f)
                curveToRelative(0f, 1.66f, -1.34f, 3f, -3f, 3f)
                reflectiveCurveToRelative(-3f, -1.34f, -3f, -3f)
                reflectiveCurveToRelative(1.34f, -3f, 3f, -3f)
                curveToRelative(0.44f, 0f, 0.85f, 0.09f, 1.23f, 0.26f)
                lineToRelative(1.41f, -1.77f)
                curveToRelative(-0.92f, -1.03f, -1.29f, -2.39f, -1.09f, -3.69f)
                lineToRelative(-2.03f, -0.68f)
                curveTo(4.98f, 11.95f, 4.06f, 12.5f, 3f, 12.5f)
                curveToRelative(-1.66f, 0f, -3f, -1.34f, -3f, -3f)
                reflectiveCurveToRelative(1.34f, -3f, 3f, -3f)
                reflectiveCurveToRelative(3f, 1.34f, 3f, 3f)
                curveToRelative(0f, 0.07f, 0f, 0.14f, -0.01f, 0.21f)
                lineToRelative(2.03f, 0.68f)
                curveToRelative(0.64f, -1.21f, 1.82f, -2.09f, 3.22f, -2.32f)
                lineToRelative(0f, -2.16f)
                curveTo(9.96f, 5.57f, 9f, 4.4f, 9f, 3f)
                curveToRelative(0f, -1.66f, 1.34f, -3f, 3f, -3f)
                reflectiveCurveToRelative(3f, 1.34f, 3f, 3f)
                curveToRelative(0f, 1.4f, -0.96f, 2.57f, -2.25f, 2.91f)
                verticalLineToRelative(2.16f)
                curveToRelative(1.4f, 0.23f, 2.58f, 1.11f, 3.22f, 2.32f)
                lineToRelative(2.03f, -0.68f)
                curveTo(18f, 9.64f, 18f, 9.57f, 18f, 9.5f)
                curveToRelative(0f, -1.66f, 1.34f, -3f, 3f, -3f)
                reflectiveCurveToRelative(3f, 1.34f, 3f, 3f)
                reflectiveCurveToRelative(-1.34f, 3f, -3f, 3f)
                curveToRelative(-1.06f, 0f, -1.98f, -0.55f, -2.52f, -1.37f)
                lineToRelative(-2.03f, 0.68f)
                curveToRelative(0.2f, 1.29f, -0.16f, 2.65f, -1.09f, 3.69f)
                lineToRelative(1.41f, 1.77f)
                curveTo(17.15f, 17.09f, 17.56f, 17f, 18f, 17f)
                curveToRelative(1.66f, 0f, 3f, 1.34f, 3f, 3f)
                reflectiveCurveToRelative(-1.34f, 3f, -3f, 3f)
                reflectiveCurveToRelative(-3f, -1.34f, -3f, -3f)
                curveToRelative(0f, -0.68f, 0.22f, -1.3f, 0.6f, -1.8f)
                lineToRelative(-1.41f, -1.77f)
                curveToRelative(-1.35f, 0.75f, -3.01f, 0.76f, -4.37f, 0f)
                lineTo(8.4f, 18.2f)
                close()
            }
        }.build()
        return _hub!!
    }

// ─── FlashOn ────────────────────────────────────────────────────────────────────

private var _flashOn: ImageVector? = null
val CIRISMaterialIcons.Filled.FlashOn: ImageVector
    get() {
        if (_flashOn != null) return _flashOn!!
        _flashOn = ImageVector.Builder(
            name = "Filled.FlashOn",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(7f, 2f)
                verticalLineToRelative(11f)
                horizontalLineToRelative(3f)
                verticalLineToRelative(9f)
                lineToRelative(7f, -12f)
                horizontalLineToRelative(-4f)
                lineToRelative(4f, -8f)
                close()
            }
        }.build()
        return _flashOn!!
    }

// ─── HealthAndSafety ────────────────────────────────────────────────────────────

private var _healthAndSafety: ImageVector? = null
val CIRISMaterialIcons.Filled.HealthAndSafety: ImageVector
    get() {
        if (_healthAndSafety != null) return _healthAndSafety!!
        _healthAndSafety = ImageVector.Builder(
            name = "Filled.HealthAndSafety",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(10.5f, 13f)
                horizontalLineTo(8f)
                verticalLineToRelative(-3f)
                horizontalLineToRelative(2.5f)
                verticalLineTo(7.5f)
                horizontalLineToRelative(3f)
                verticalLineTo(10f)
                horizontalLineTo(16f)
                verticalLineToRelative(3f)
                horizontalLineToRelative(-2.5f)
                verticalLineToRelative(2.5f)
                horizontalLineToRelative(-3f)
                verticalLineTo(13f)
                close()
                moveTo(12f, 2f)
                lineTo(4f, 5f)
                verticalLineToRelative(6.09f)
                curveToRelative(0f, 5.05f, 3.41f, 9.76f, 8f, 10.91f)
                curveToRelative(4.59f, -1.15f, 8f, -5.86f, 8f, -10.91f)
                verticalLineTo(5f)
                lineTo(12f, 2f)
                close()
            }
        }.build()
        return _healthAndSafety!!
    }

// ─── Badge ──────────────────────────────────────────────────────────────────────

private var _badge: ImageVector? = null
val CIRISMaterialIcons.Filled.Badge: ImageVector
    get() {
        if (_badge != null) return _badge!!
        _badge = ImageVector.Builder(
            name = "Filled.Badge",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(20f, 7f)
                horizontalLineToRelative(-5f)
                verticalLineTo(4f)
                curveToRelative(0f, -1.1f, -0.9f, -2f, -2f, -2f)
                horizontalLineToRelative(-2f)
                curveTo(9.9f, 2f, 9f, 2.9f, 9f, 4f)
                verticalLineToRelative(3f)
                horizontalLineTo(4f)
                curveTo(2.9f, 7f, 2f, 7.9f, 2f, 9f)
                verticalLineToRelative(11f)
                curveToRelative(0f, 1.1f, 0.9f, 2f, 2f, 2f)
                horizontalLineToRelative(16f)
                curveToRelative(1.1f, 0f, 2f, -0.9f, 2f, -2f)
                verticalLineTo(9f)
                curveTo(22f, 7.9f, 21.1f, 7f, 20f, 7f)
                close()
                moveTo(9f, 12f)
                curveToRelative(0.83f, 0f, 1.5f, 0.67f, 1.5f, 1.5f)
                reflectiveCurveTo(9.83f, 15f, 9f, 15f)
                reflectiveCurveToRelative(-1.5f, -0.67f, -1.5f, -1.5f)
                reflectiveCurveTo(8.17f, 12f, 9f, 12f)
                close()
                moveTo(12f, 18f)
                horizontalLineTo(6f)
                verticalLineToRelative(-0.75f)
                curveToRelative(0f, -1f, 2f, -1.5f, 3f, -1.5f)
                reflectiveCurveToRelative(3f, 0.5f, 3f, 1.5f)
                verticalLineTo(18f)
                close()
                moveTo(13f, 9f)
                horizontalLineToRelative(-2f)
                verticalLineTo(4f)
                horizontalLineToRelative(2f)
                verticalLineTo(9f)
                close()
                moveTo(18f, 16.5f)
                horizontalLineToRelative(-4f)
                verticalLineTo(15f)
                horizontalLineToRelative(4f)
                verticalLineTo(16.5f)
                close()
                moveTo(18f, 13.5f)
                horizontalLineToRelative(-4f)
                verticalLineTo(12f)
                horizontalLineToRelative(4f)
                verticalLineTo(13.5f)
                close()
            }
        }.build()
        return _badge!!
    }

// ─── Inventory2 ─────────────────────────────────────────────────────────────────

private var _inventory2: ImageVector? = null
val CIRISMaterialIcons.Filled.Inventory2: ImageVector
    get() {
        if (_inventory2 != null) return _inventory2!!
        _inventory2 = ImageVector.Builder(
            name = "Filled.Inventory2",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(20f, 2f)
                horizontalLineTo(4f)
                curveTo(3f, 2f, 2f, 2.9f, 2f, 4f)
                verticalLineToRelative(3.01f)
                curveTo(2f, 7.73f, 2.43f, 8.35f, 3f, 8.7f)
                verticalLineTo(20f)
                curveToRelative(0f, 1.1f, 1.1f, 2f, 2f, 2f)
                horizontalLineToRelative(14f)
                curveToRelative(0.9f, 0f, 2f, -0.9f, 2f, -2f)
                verticalLineTo(8.7f)
                curveToRelative(0.57f, -0.35f, 1f, -0.97f, 1f, -1.69f)
                verticalLineTo(4f)
                curveTo(22f, 2.9f, 21f, 2f, 20f, 2f)
                close()
                moveTo(15f, 14f)
                horizontalLineTo(9f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(6f)
                verticalLineTo(14f)
                close()
                moveTo(20f, 7f)
                horizontalLineTo(4f)
                verticalLineTo(4f)
                horizontalLineToRelative(16f)
                verticalLineTo(7f)
                close()
            }
        }.build()
        return _inventory2!!
    }

// ─── Cancel ─────────────────────────────────────────────────────────────────────

private var _cancel: ImageVector? = null
val CIRISMaterialIcons.Filled.Cancel: ImageVector
    get() {
        if (_cancel != null) return _cancel!!
        _cancel = ImageVector.Builder(
            name = "Filled.Cancel",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 2f)
                curveTo(6.47f, 2f, 2f, 6.47f, 2f, 12f)
                reflectiveCurveToRelative(4.47f, 10f, 10f, 10f)
                reflectiveCurveToRelative(10f, -4.47f, 10f, -10f)
                reflectiveCurveTo(17.53f, 2f, 12f, 2f)
                close()
                moveTo(17f, 15.59f)
                lineTo(15.59f, 17f)
                lineTo(12f, 13.41f)
                lineTo(8.41f, 17f)
                lineTo(7f, 15.59f)
                lineTo(10.59f, 12f)
                lineTo(7f, 8.41f)
                lineTo(8.41f, 7f)
                lineTo(12f, 10.59f)
                lineTo(15.59f, 7f)
                lineTo(17f, 8.41f)
                lineTo(13.41f, 12f)
                lineTo(17f, 15.59f)
                close()
            }
        }.build()
        return _cancel!!
    }

// ─── Circle ─────────────────────────────────────────────────────────────────────

private var _circle: ImageVector? = null
val CIRISMaterialIcons.Filled.Circle: ImageVector
    get() {
        if (_circle != null) return _circle!!
        _circle = ImageVector.Builder(
            name = "Filled.Circle",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 2f)
                curveTo(6.47f, 2f, 2f, 6.47f, 2f, 12f)
                reflectiveCurveToRelative(4.47f, 10f, 10f, 10f)
                reflectiveCurveToRelative(10f, -4.47f, 10f, -10f)
                reflectiveCurveTo(17.53f, 2f, 12f, 2f)
                close()
            }
        }.build()
        return _circle!!
    }

// ─── ContentCopy ────────────────────────────────────────────────────────────────

private var _contentCopy: ImageVector? = null
val CIRISMaterialIcons.Filled.ContentCopy: ImageVector
    get() {
        if (_contentCopy != null) return _contentCopy!!
        _contentCopy = ImageVector.Builder(
            name = "Filled.ContentCopy",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(16f, 1f)
                horizontalLineTo(4f)
                curveToRelative(-1.1f, 0f, -2f, 0.9f, -2f, 2f)
                verticalLineToRelative(14f)
                horizontalLineToRelative(2f)
                verticalLineTo(3f)
                horizontalLineToRelative(12f)
                verticalLineTo(1f)
                close()
                moveTo(19f, 5f)
                horizontalLineTo(8f)
                curveToRelative(-1.1f, 0f, -2f, 0.9f, -2f, 2f)
                verticalLineToRelative(14f)
                curveToRelative(0f, 1.1f, 0.9f, 2f, 2f, 2f)
                horizontalLineToRelative(11f)
                curveToRelative(1.1f, 0f, 2f, -0.9f, 2f, -2f)
                verticalLineTo(7f)
                curveToRelative(0f, -1.1f, -0.9f, -2f, -2f, -2f)
                close()
                moveTo(19f, 21f)
                horizontalLineTo(8f)
                verticalLineTo(7f)
                horizontalLineToRelative(11f)
                verticalLineToRelative(14f)
                close()
            }
        }.build()
        return _contentCopy!!
    }

// ─── Download ───────────────────────────────────────────────────────────────────

private var _download: ImageVector? = null
val CIRISMaterialIcons.Filled.Download: ImageVector
    get() {
        if (_download != null) return _download!!
        _download = ImageVector.Builder(
            name = "Filled.Download",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(5f, 20f)
                horizontalLineToRelative(14f)
                verticalLineToRelative(-2f)
                horizontalLineTo(5f)
                verticalLineTo(20f)
                close()
                moveTo(19f, 9f)
                horizontalLineToRelative(-4f)
                verticalLineTo(3f)
                horizontalLineTo(9f)
                verticalLineToRelative(6f)
                horizontalLineTo(5f)
                lineToRelative(7f, 7f)
                lineTo(19f, 9f)
                close()
            }
        }.build()
        return _download!!
    }

// ─── Extension ──────────────────────────────────────────────────────────────────

private var _extension: ImageVector? = null
val CIRISMaterialIcons.Filled.Extension: ImageVector
    get() {
        if (_extension != null) return _extension!!
        _extension = ImageVector.Builder(
            name = "Filled.Extension",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(20.5f, 11f)
                horizontalLineTo(19f)
                verticalLineTo(7f)
                curveToRelative(0f, -1.1f, -0.9f, -2f, -2f, -2f)
                horizontalLineToRelative(-4f)
                verticalLineTo(3.5f)
                curveTo(13f, 2.12f, 11.88f, 1f, 10.5f, 1f)
                reflectiveCurveTo(8f, 2.12f, 8f, 3.5f)
                verticalLineTo(5f)
                horizontalLineTo(4f)
                curveToRelative(-1.1f, 0f, -1.99f, 0.9f, -1.99f, 2f)
                verticalLineToRelative(3.8f)
                horizontalLineTo(3.5f)
                curveToRelative(1.49f, 0f, 2.7f, 1.21f, 2.7f, 2.7f)
                reflectiveCurveToRelative(-1.21f, 2.7f, -2.7f, 2.7f)
                horizontalLineTo(2f)
                verticalLineTo(20f)
                curveToRelative(0f, 1.1f, 0.9f, 2f, 2f, 2f)
                horizontalLineToRelative(3.8f)
                verticalLineToRelative(-1.5f)
                curveToRelative(0f, -1.49f, 1.21f, -2.7f, 2.7f, -2.7f)
                curveToRelative(1.49f, 0f, 2.7f, 1.21f, 2.7f, 2.7f)
                verticalLineTo(22f)
                horizontalLineTo(17f)
                curveToRelative(1.1f, 0f, 2f, -0.9f, 2f, -2f)
                verticalLineToRelative(-4f)
                horizontalLineToRelative(1.5f)
                curveToRelative(1.38f, 0f, 2.5f, -1.12f, 2.5f, -2.5f)
                reflectiveCurveTo(21.88f, 11f, 20.5f, 11f)
                close()
            }
        }.build()
        return _extension!!
    }

// ─── Language ───────────────────────────────────────────────────────────────────

private var _language: ImageVector? = null
val CIRISMaterialIcons.Filled.Language: ImageVector
    get() {
        if (_language != null) return _language!!
        _language = ImageVector.Builder(
            name = "Filled.Language",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(11.99f, 2f)
                curveTo(6.47f, 2f, 2f, 6.48f, 2f, 12f)
                reflectiveCurveToRelative(4.47f, 10f, 9.99f, 10f)
                curveTo(17.52f, 22f, 22f, 17.52f, 22f, 12f)
                reflectiveCurveTo(17.52f, 2f, 11.99f, 2f)
                close()
                moveTo(18.92f, 8f)
                horizontalLineToRelative(-2.95f)
                curveToRelative(-0.32f, -1.25f, -0.78f, -2.45f, -1.38f, -3.56f)
                curveToRelative(1.84f, 0.63f, 3.37f, 1.91f, 4.33f, 3.56f)
                close()
                moveTo(12f, 4.04f)
                curveToRelative(0.83f, 1.2f, 1.48f, 2.53f, 1.91f, 3.96f)
                horizontalLineToRelative(-3.82f)
                curveToRelative(0.43f, -1.43f, 1.08f, -2.76f, 1.91f, -3.96f)
                close()
                moveTo(4.26f, 14f)
                curveTo(4.1f, 13.36f, 4f, 12.69f, 4f, 12f)
                reflectiveCurveToRelative(0.1f, -1.36f, 0.26f, -2f)
                horizontalLineToRelative(3.38f)
                curveToRelative(-0.08f, 0.66f, -0.14f, 1.32f, -0.14f, 2f)
                curveToRelative(0f, 0.68f, 0.06f, 1.34f, 0.14f, 2f)
                horizontalLineTo(4.26f)
                close()
                moveTo(5.08f, 16f)
                horizontalLineToRelative(2.95f)
                curveToRelative(0.32f, 1.25f, 0.78f, 2.45f, 1.38f, 3.56f)
                curveToRelative(-1.84f, -0.63f, -3.37f, -1.9f, -4.33f, -3.56f)
                close()
                moveTo(8.03f, 8f)
                horizontalLineTo(5.08f)
                curveToRelative(0.96f, -1.66f, 2.49f, -2.93f, 4.33f, -3.56f)
                curveTo(8.81f, 5.55f, 8.35f, 6.75f, 8.03f, 8f)
                close()
                moveTo(12f, 19.96f)
                curveToRelative(-0.83f, -1.2f, -1.48f, -2.53f, -1.91f, -3.96f)
                horizontalLineToRelative(3.82f)
                curveToRelative(-0.43f, 1.43f, -1.08f, 2.76f, -1.91f, 3.96f)
                close()
                moveTo(14.34f, 14f)
                horizontalLineTo(9.66f)
                curveToRelative(-0.09f, -0.66f, -0.16f, -1.32f, -0.16f, -2f)
                curveToRelative(0f, -0.68f, 0.07f, -1.35f, 0.16f, -2f)
                horizontalLineToRelative(4.68f)
                curveToRelative(0.09f, 0.65f, 0.16f, 1.32f, 0.16f, 2f)
                curveToRelative(0f, 0.68f, -0.07f, 1.34f, -0.16f, 2f)
                close()
                moveTo(14.59f, 19.56f)
                curveToRelative(0.6f, -1.11f, 1.06f, -2.31f, 1.38f, -3.56f)
                horizontalLineToRelative(2.95f)
                curveToRelative(-0.96f, 1.65f, -2.49f, 2.93f, -4.33f, 3.56f)
                close()
                moveTo(16.36f, 14f)
                curveToRelative(0.08f, -0.66f, 0.14f, -1.32f, 0.14f, -2f)
                curveToRelative(0f, -0.68f, -0.06f, -1.34f, -0.14f, -2f)
                horizontalLineToRelative(3.38f)
                curveToRelative(0.16f, 0.64f, 0.26f, 1.31f, 0.26f, 2f)
                reflectiveCurveToRelative(-0.1f, 1.36f, -0.26f, 2f)
                horizontalLineToRelative(-3.38f)
                close()
            }
        }.build()
        return _language!!
    }

// ─── PhoneAndroid ───────────────────────────────────────────────────────────────

private var _phoneAndroid: ImageVector? = null
val CIRISMaterialIcons.Filled.PhoneAndroid: ImageVector
    get() {
        if (_phoneAndroid != null) return _phoneAndroid!!
        _phoneAndroid = ImageVector.Builder(
            name = "Filled.PhoneAndroid",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(16f, 1f)
                horizontalLineTo(8f)
                curveTo(6.34f, 1f, 5f, 2.34f, 5f, 4f)
                verticalLineToRelative(16f)
                curveToRelative(0f, 1.66f, 1.34f, 3f, 3f, 3f)
                horizontalLineToRelative(8f)
                curveToRelative(1.66f, 0f, 3f, -1.34f, 3f, -3f)
                verticalLineTo(4f)
                curveToRelative(0f, -1.66f, -1.34f, -3f, -3f, -3f)
                close()
                moveTo(14f, 21f)
                horizontalLineToRelative(-4f)
                verticalLineToRelative(-1f)
                horizontalLineToRelative(4f)
                verticalLineToRelative(1f)
                close()
                moveTo(17.25f, 18f)
                horizontalLineTo(6.75f)
                verticalLineTo(4f)
                horizontalLineToRelative(10.5f)
                verticalLineToRelative(14f)
                close()
            }
        }.build()
        return _phoneAndroid!!
    }

// ─── Remove ─────────────────────────────────────────────────────────────────────

private var _remove: ImageVector? = null
val CIRISMaterialIcons.Filled.Remove: ImageVector
    get() {
        if (_remove != null) return _remove!!
        _remove = ImageVector.Builder(
            name = "Filled.Remove",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(19f, 13f)
                horizontalLineTo(5f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(14f)
                verticalLineToRelative(2f)
                close()
            }
        }.build()
        return _remove!!
    }

// ─── Sensors ────────────────────────────────────────────────────────────────────

private var _sensors: ImageVector? = null
val CIRISMaterialIcons.Filled.Sensors: ImageVector
    get() {
        if (_sensors != null) return _sensors!!
        _sensors = ImageVector.Builder(
            name = "Filled.Sensors",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(7.76f, 16.24f)
                curveTo(6.67f, 15.16f, 6f, 13.66f, 6f, 12f)
                reflectiveCurveToRelative(0.67f, -3.16f, 1.76f, -4.24f)
                lineToRelative(1.42f, 1.42f)
                curveTo(8.45f, 9.9f, 8f, 10.9f, 8f, 12f)
                curveToRelative(0f, 1.1f, 0.45f, 2.1f, 1.17f, 2.83f)
                lineTo(7.76f, 16.24f)
                close()
                moveTo(16.24f, 16.24f)
                curveTo(17.33f, 15.16f, 18f, 13.66f, 18f, 12f)
                reflectiveCurveToRelative(-0.67f, -3.16f, -1.76f, -4.24f)
                lineToRelative(-1.42f, 1.42f)
                curveTo(15.55f, 9.9f, 16f, 10.9f, 16f, 12f)
                curveToRelative(0f, 1.1f, -0.45f, 2.1f, -1.17f, 2.83f)
                lineTo(16.24f, 16.24f)
                close()
                moveTo(12f, 10f)
                curveToRelative(-1.1f, 0f, -2f, 0.9f, -2f, 2f)
                reflectiveCurveToRelative(0.9f, 2f, 2f, 2f)
                reflectiveCurveToRelative(2f, -0.9f, 2f, -2f)
                reflectiveCurveTo(13.1f, 10f, 12f, 10f)
                close()
                moveTo(20f, 12f)
                curveToRelative(0f, 2.21f, -0.9f, 4.21f, -2.35f, 5.65f)
                lineToRelative(1.42f, 1.42f)
                curveTo(20.88f, 17.26f, 22f, 14.76f, 22f, 12f)
                reflectiveCurveToRelative(-1.12f, -5.26f, -2.93f, -7.07f)
                lineToRelative(-1.42f, 1.42f)
                curveTo(19.1f, 7.79f, 20f, 9.79f, 20f, 12f)
                close()
                moveTo(6.35f, 6.35f)
                lineTo(4.93f, 4.93f)
                curveTo(3.12f, 6.74f, 2f, 9.24f, 2f, 12f)
                reflectiveCurveToRelative(1.12f, 5.26f, 2.93f, 7.07f)
                lineToRelative(1.42f, -1.42f)
                curveTo(4.9f, 16.21f, 4f, 14.21f, 4f, 12f)
                reflectiveCurveTo(4.9f, 7.79f, 6.35f, 6.35f)
                close()
            }
        }.build()
        return _sensors!!
    }

// ─── Speaker ────────────────────────────────────────────────────────────────────

private var _speaker: ImageVector? = null
val CIRISMaterialIcons.Filled.Speaker: ImageVector
    get() {
        if (_speaker != null) return _speaker!!
        _speaker = ImageVector.Builder(
            name = "Filled.Speaker",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(17f, 2f)
                horizontalLineTo(7f)
                curveToRelative(-1.1f, 0f, -2f, 0.9f, -2f, 2f)
                verticalLineToRelative(16f)
                curveToRelative(0f, 1.1f, 0.9f, 1.99f, 2f, 1.99f)
                lineTo(17f, 22f)
                curveToRelative(1.1f, 0f, 2f, -0.9f, 2f, -2f)
                verticalLineTo(4f)
                curveToRelative(0f, -1.1f, -0.9f, -2f, -2f, -2f)
                close()
                moveTo(12f, 4f)
                curveToRelative(1.1f, 0f, 2f, 0.9f, 2f, 2f)
                reflectiveCurveToRelative(-0.9f, 2f, -2f, 2f)
                curveToRelative(-1.11f, 0f, -2f, -0.9f, -2f, -2f)
                reflectiveCurveToRelative(0.89f, -2f, 2f, -2f)
                close()
                moveTo(12f, 20f)
                curveToRelative(-2.76f, 0f, -5f, -2.24f, -5f, -5f)
                reflectiveCurveToRelative(2.24f, -5f, 5f, -5f)
                reflectiveCurveToRelative(5f, 2.24f, 5f, 5f)
                reflectiveCurveToRelative(-2.24f, 5f, -5f, 5f)
                close()
                moveTo(12f, 12f)
                curveToRelative(-1.66f, 0f, -3f, 1.34f, -3f, 3f)
                reflectiveCurveToRelative(1.34f, 3f, 3f, 3f)
                reflectiveCurveToRelative(3f, -1.34f, 3f, -3f)
                reflectiveCurveToRelative(-1.34f, -3f, -3f, -3f)
                close()
            }
        }.build()
        return _speaker!!
    }

// ─── Speed ──────────────────────────────────────────────────────────────────────

private var _speed: ImageVector? = null
val CIRISMaterialIcons.Filled.Speed: ImageVector
    get() {
        if (_speed != null) return _speed!!
        _speed = ImageVector.Builder(
            name = "Filled.Speed",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(20.38f, 8.57f)
                lineToRelative(-1.23f, 1.85f)
                curveToRelative(0.78f, 1.22f, 1.24f, 2.65f, 1.24f, 4.18f)
                curveToRelative(0f, 0.97f, -0.18f, 1.9f, -0.5f, 2.76f)
                lineToRelative(-0.02f, 0.22f)
                horizontalLineTo(5.07f)
                curveTo(3.76f, 15.9f, 3.39f, 13.99f, 3.61f, 12.13f)
                curveToRelative(0.25f, -2.08f, 1.2f, -3.94f, 2.65f, -5.33f)
                curveToRelative(1.6f, -1.53f, 3.7f, -2.39f, 5.89f, -2.39f)
                curveToRelative(1.36f, 0f, 2.67f, 0.31f, 3.84f, 0.89f)
                lineToRelative(1.85f, -1.23f)
                curveTo(16.09f, 3.11f, 14.09f, 2.5f, 12f, 2.5f)
                curveToRelative(-2.63f, 0f, -5.11f, 1.03f, -6.97f, 2.89f)
                curveTo(3.12f, 7.31f, 2.06f, 9.82f, 2.06f, 12.5f)
                curveToRelative(0f, 2.36f, 0.78f, 4.54f, 2.07f, 6.31f)
                lineToRelative(-0.78f, 0.19f)
                curveToRelative(0.52f, 0.6f, 1.06f, 0.6f, 1.72f, 1f)
                horizontalLineToRelative(13.85f)
                curveToRelative(0.66f, -0.4f, 1.2f, -0.4f, 1.74f, -1f)
                curveToRelative(1.5f, -1.94f, 2.4f, -4.37f, 2.4f, -7f)
                curveToRelative(0f, -2.37f, -0.73f, -4.57f, -1.97f, -6.39f)
                lineToRelative(-0.7f, -0.04f)
                close()
                moveTo(10.59f, 15.41f)
                curveToRelative(0.78f, 0.78f, 2.05f, 0.78f, 2.83f, 0f)
                lineToRelative(5.66f, -8.49f)
                lineToRelative(-8.49f, 5.66f)
                curveToRelative(-0.78f, 0.78f, -0.78f, 2.05f, 0f, 2.83f)
                close()
            }
        }.build()
        return _speed!!
    }

// ─── Terminal ───────────────────────────────────────────────────────────────────

private var _terminal: ImageVector? = null
val CIRISMaterialIcons.Filled.Terminal: ImageVector
    get() {
        if (_terminal != null) return _terminal!!
        _terminal = ImageVector.Builder(
            name = "Filled.Terminal",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(20f, 4f)
                horizontalLineTo(4f)
                curveTo(2.89f, 4f, 2f, 4.9f, 2f, 6f)
                verticalLineToRelative(12f)
                curveToRelative(0f, 1.1f, 0.89f, 2f, 2f, 2f)
                horizontalLineToRelative(16f)
                curveToRelative(1.1f, 0f, 2f, -0.9f, 2f, -2f)
                verticalLineTo(6f)
                curveTo(22f, 4.9f, 21.11f, 4f, 20f, 4f)
                close()
                moveTo(20f, 18f)
                horizontalLineTo(4f)
                verticalLineTo(8f)
                horizontalLineToRelative(16f)
                verticalLineTo(18f)
                close()
                moveTo(18f, 17f)
                horizontalLineToRelative(-6f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(6f)
                verticalLineTo(17f)
                close()
                moveTo(7.5f, 17f)
                lineToRelative(-1.41f, -1.41f)
                lineTo(8.67f, 13f)
                lineToRelative(-2.59f, -2.59f)
                lineTo(7.5f, 9f)
                lineToRelative(4f, 4f)
                lineTo(7.5f, 17f)
                close()
            }
        }.build()
        return _terminal!!
    }

// ─── Thermostat ─────────────────────────────────────────────────────────────────

private var _thermostat: ImageVector? = null
val CIRISMaterialIcons.Filled.Thermostat: ImageVector
    get() {
        if (_thermostat != null) return _thermostat!!
        _thermostat = ImageVector.Builder(
            name = "Filled.Thermostat",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(15f, 13f)
                verticalLineTo(5f)
                curveToRelative(0f, -1.66f, -1.34f, -3f, -3f, -3f)
                reflectiveCurveTo(9f, 3.34f, 9f, 5f)
                verticalLineToRelative(8f)
                curveToRelative(-1.21f, 0.91f, -2f, 2.37f, -2f, 4f)
                curveToRelative(0f, 2.76f, 2.24f, 5f, 5f, 5f)
                reflectiveCurveToRelative(5f, -2.24f, 5f, -5f)
                curveTo(17f, 15.37f, 16.21f, 13.91f, 15f, 13f)
                close()
                moveTo(11f, 11f)
                verticalLineTo(5f)
                curveToRelative(0f, -0.55f, 0.45f, -1f, 1f, -1f)
                reflectiveCurveToRelative(1f, 0.45f, 1f, 1f)
                verticalLineToRelative(1f)
                horizontalLineToRelative(-1f)
                verticalLineToRelative(1f)
                horizontalLineToRelative(1f)
                verticalLineToRelative(1f)
                verticalLineToRelative(1f)
                horizontalLineToRelative(-1f)
                verticalLineToRelative(1f)
                horizontalLineToRelative(1f)
                verticalLineToRelative(1f)
                horizontalLineTo(11f)
                close()
            }
        }.build()
        return _thermostat!!
    }

// ─── ToggleOn ───────────────────────────────────────────────────────────────────

private var _toggleOn: ImageVector? = null
val CIRISMaterialIcons.Filled.ToggleOn: ImageVector
    get() {
        if (_toggleOn != null) return _toggleOn!!
        _toggleOn = ImageVector.Builder(
            name = "Filled.ToggleOn",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(17f, 7f)
                horizontalLineTo(7f)
                curveToRelative(-2.76f, 0f, -5f, 2.24f, -5f, 5f)
                reflectiveCurveToRelative(2.24f, 5f, 5f, 5f)
                horizontalLineToRelative(10f)
                curveToRelative(2.76f, 0f, 5f, -2.24f, 5f, -5f)
                reflectiveCurveToRelative(-2.24f, -5f, -5f, -5f)
                close()
                moveTo(17f, 15f)
                curveToRelative(-1.66f, 0f, -3f, -1.34f, -3f, -3f)
                reflectiveCurveToRelative(1.34f, -3f, 3f, -3f)
                reflectiveCurveToRelative(3f, 1.34f, 3f, 3f)
                reflectiveCurveToRelative(-1.34f, 3f, -3f, 3f)
                close()
            }
        }.build()
        return _toggleOn!!
    }

// ─── WbSunny ────────────────────────────────────────────────────────────────────

private var _wbSunny: ImageVector? = null
val CIRISMaterialIcons.Filled.WbSunny: ImageVector
    get() {
        if (_wbSunny != null) return _wbSunny!!
        _wbSunny = ImageVector.Builder(
            name = "Filled.WbSunny",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(6.76f, 4.84f)
                lineToRelative(-1.8f, -1.79f)
                lineToRelative(-1.41f, 1.41f)
                lineToRelative(1.79f, 1.79f)
                lineToRelative(1.42f, -1.41f)
                close()
                moveTo(4f, 10.5f)
                horizontalLineTo(1f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(3f)
                verticalLineToRelative(-2f)
                close()
                moveTo(13f, 0.55f)
                horizontalLineToRelative(-2f)
                verticalLineTo(3.5f)
                horizontalLineToRelative(2f)
                verticalLineTo(0.55f)
                close()
                moveTo(20.45f, 4.46f)
                lineToRelative(-1.41f, -1.41f)
                lineToRelative(-1.79f, 1.79f)
                lineToRelative(1.41f, 1.41f)
                lineToRelative(1.79f, -1.79f)
                close()
                moveTo(17.24f, 18.16f)
                lineToRelative(1.79f, 1.8f)
                lineToRelative(1.41f, -1.41f)
                lineToRelative(-1.8f, -1.79f)
                lineToRelative(-1.4f, 1.4f)
                close()
                moveTo(20f, 10.5f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(3f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(-3f)
                close()
                moveTo(12f, 5.5f)
                curveToRelative(-3.31f, 0f, -6f, 2.69f, -6f, 6f)
                reflectiveCurveToRelative(2.69f, 6f, 6f, 6f)
                reflectiveCurveToRelative(6f, -2.69f, 6f, -6f)
                reflectiveCurveToRelative(-2.69f, -6f, -6f, -6f)
                close()
                moveTo(11f, 22.45f)
                horizontalLineToRelative(2f)
                verticalLineTo(19.5f)
                horizontalLineToRelative(-2f)
                verticalLineToRelative(2.95f)
                close()
                moveTo(3.55f, 18.54f)
                lineToRelative(1.41f, 1.41f)
                lineToRelative(1.79f, -1.8f)
                lineToRelative(-1.41f, -1.41f)
                lineToRelative(-1.79f, 1.8f)
                close()
            }
        }.build()
        return _wbSunny!!
    }

// ─── Wifi ───────────────────────────────────────────────────────────────────────

private var _wifi: ImageVector? = null
val CIRISMaterialIcons.Filled.Wifi: ImageVector
    get() {
        if (_wifi != null) return _wifi!!
        _wifi = ImageVector.Builder(
            name = "Filled.Wifi",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(1f, 9f)
                lineToRelative(2f, 2f)
                curveToRelative(4.97f, -4.97f, 13.03f, -4.97f, 18f, 0f)
                lineToRelative(2f, -2f)
                curveTo(16.93f, 2.93f, 7.08f, 2.93f, 1f, 9f)
                close()
                moveTo(9f, 17f)
                lineToRelative(3f, 3f)
                lineToRelative(3f, -3f)
                curveToRelative(-1.65f, -1.66f, -4.34f, -1.66f, -6f, 0f)
                close()
                moveTo(5f, 13f)
                lineToRelative(2f, 2f)
                curveToRelative(2.76f, -2.76f, 7.24f, -2.76f, 10f, 0f)
                lineToRelative(2f, -2f)
                curveTo(15.14f, 9.14f, 8.87f, 9.14f, 5f, 13f)
                close()
            }
        }.build()
        return _wifi!!
    }

// ─── Air ────────────────────────────────────────────────────────────────────────

private var _air: ImageVector? = null
val CIRISMaterialIcons.Filled.Air: ImageVector
    get() {
        if (_air != null) return _air!!
        _air = ImageVector.Builder(
            name = "Filled.Air",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(14.5f, 17f)
                curveToRelative(0f, 1.65f, -1.35f, 3f, -3f, 3f)
                reflectiveCurveToRelative(-3f, -1.35f, -3f, -3f)
                horizontalLineToRelative(2f)
                curveToRelative(0f, 0.55f, 0.45f, 1f, 1f, 1f)
                reflectiveCurveToRelative(1f, -0.45f, 1f, -1f)
                reflectiveCurveToRelative(-0.45f, -1f, -1f, -1f)
                horizontalLineTo(2f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(9.5f)
                curveTo(13.15f, 14f, 14.5f, 15.35f, 14.5f, 17f)
                close()
                moveTo(19f, 6.5f)
                curveTo(19f, 4.57f, 17.43f, 3f, 15.5f, 3f)
                reflectiveCurveTo(12f, 4.57f, 12f, 6.5f)
                horizontalLineToRelative(2f)
                curveTo(14f, 5.67f, 14.67f, 5f, 15.5f, 5f)
                reflectiveCurveTo(17f, 5.67f, 17f, 6.5f)
                reflectiveCurveTo(16.33f, 8f, 15.5f, 8f)
                horizontalLineTo(2f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(13.5f)
                curveTo(17.43f, 10f, 19f, 8.43f, 19f, 6.5f)
                close()
                moveTo(18.5f, 11f)
                horizontalLineTo(2f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(16.5f)
                curveToRelative(0.83f, 0f, 1.5f, 0.67f, 1.5f, 1.5f)
                reflectiveCurveTo(19.33f, 16f, 18.5f, 16f)
                verticalLineToRelative(2f)
                curveToRelative(1.93f, 0f, 3.5f, -1.57f, 3.5f, -3.5f)
                reflectiveCurveTo(20.43f, 11f, 18.5f, 11f)
                close()
            }
        }.build()
        return _air!!
    }

// ─── DataObject ─────────────────────────────────────────────────────────────────

private var _dataObject: ImageVector? = null
val CIRISMaterialIcons.Filled.DataObject: ImageVector
    get() {
        if (_dataObject != null) return _dataObject!!
        _dataObject = ImageVector.Builder(
            name = "Filled.DataObject",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(21f, 10f)
                curveToRelative(-0.55f, 0f, -1f, -0.45f, -1f, -1f)
                verticalLineTo(7f)
                curveToRelative(0f, -1.65f, -1.35f, -3f, -3f, -3f)
                horizontalLineToRelative(-3f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(3f)
                curveToRelative(0.55f, 0f, 1f, 0.45f, 1f, 1f)
                verticalLineToRelative(2f)
                curveToRelative(0f, 1.3f, 0.84f, 2.42f, 2f, 2.83f)
                verticalLineToRelative(0.34f)
                curveToRelative(-1.16f, 0.41f, -2f, 1.52f, -2f, 2.83f)
                verticalLineToRelative(2f)
                curveToRelative(0f, 0.55f, -0.45f, 1f, -1f, 1f)
                horizontalLineToRelative(-3f)
                verticalLineToRelative(2f)
                horizontalLineToRelative(3f)
                curveToRelative(1.65f, 0f, 3f, -1.35f, 3f, -3f)
                verticalLineToRelative(-2f)
                curveToRelative(0f, -0.55f, 0.45f, -1f, 1f, -1f)
                horizontalLineToRelative(1f)
                verticalLineToRelative(-4f)
                horizontalLineTo(21f)
                close()
            }
        }.build()
        return _dataObject!!
    }

// ─── Devices ────────────────────────────────────────────────────────────────────

private var _devices: ImageVector? = null
val CIRISMaterialIcons.Filled.Devices: ImageVector
    get() {
        if (_devices != null) return _devices!!
        _devices = ImageVector.Builder(
            name = "Filled.Devices",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(4f, 6f)
                horizontalLineToRelative(18f)
                verticalLineTo(4f)
                horizontalLineTo(4f)
                curveToRelative(-1.1f, 0f, -2f, 0.9f, -2f, 2f)
                verticalLineToRelative(11f)
                horizontalLineTo(0f)
                verticalLineToRelative(3f)
                horizontalLineToRelative(14f)
                verticalLineToRelative(-3f)
                horizontalLineTo(4f)
                verticalLineTo(6f)
                close()
                moveTo(23f, 8f)
                horizontalLineToRelative(-6f)
                curveToRelative(-0.55f, 0f, -1f, 0.45f, -1f, 1f)
                verticalLineToRelative(10f)
                curveToRelative(0f, 0.55f, 0.45f, 1f, 1f, 1f)
                horizontalLineToRelative(6f)
                curveToRelative(0.55f, 0f, 1f, -0.45f, 1f, -1f)
                verticalLineTo(9f)
                curveToRelative(0f, -0.55f, -0.45f, -1f, -1f, -1f)
                close()
                moveTo(22f, 17f)
                horizontalLineToRelative(-4f)
                verticalLineToRelative(-7f)
                horizontalLineToRelative(4f)
                verticalLineToRelative(7f)
                close()
            }
        }.build()
        return _devices!!
    }

// ─── PowerOff ───────────────────────────────────────────────────────────────────

private var _powerOff: ImageVector? = null
val CIRISMaterialIcons.Filled.PowerOff: ImageVector
    get() {
        if (_powerOff != null) return _powerOff!!
        _powerOff = ImageVector.Builder(
            name = "Filled.PowerOff",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(18f, 14.49f)
                verticalLineTo(9f)
                curveToRelative(0f, -1f, -1.01f, -2.01f, -2f, -2f)
                verticalLineTo(3f)
                horizontalLineToRelative(-2f)
                verticalLineToRelative(4f)
                horizontalLineToRelative(-4f)
                verticalLineTo(3f)
                horizontalLineTo(8f)
                verticalLineToRelative(2.48f)
                lineToRelative(9.51f, 9.5f)
                lineToRelative(0.49f, -0.49f)
                close()
                moveTo(16.24f, 16.26f)
                lineTo(7.2f, 7.2f)
                lineToRelative(-0.01f, 0.01f)
                lineTo(3.98f, 4f)
                lineTo(2.71f, 5.25f)
                lineToRelative(3.36f, 3.36f)
                curveTo(6.04f, 8.74f, 6f, 8.87f, 6f, 9f)
                verticalLineToRelative(5.48f)
                lineTo(9.5f, 18f)
                verticalLineToRelative(3f)
                horizontalLineToRelative(5f)
                verticalLineToRelative(-3f)
                lineToRelative(0.48f, -0.48f)
                lineTo(19.45f, 22f)
                lineToRelative(1.26f, -1.28f)
                lineToRelative(-4.47f, -4.46f)
                close()
            }
        }.build()
        return _powerOff!!
    }

// ─── RadioButtonChecked ─────────────────────────────────────────────────────────

private var _radioButtonChecked: ImageVector? = null
val CIRISMaterialIcons.Filled.RadioButtonChecked: ImageVector
    get() {
        if (_radioButtonChecked != null) return _radioButtonChecked!!
        _radioButtonChecked = ImageVector.Builder(
            name = "Filled.RadioButtonChecked",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 7f)
                curveToRelative(-2.76f, 0f, -5f, 2.24f, -5f, 5f)
                reflectiveCurveToRelative(2.24f, 5f, 5f, 5f)
                reflectiveCurveToRelative(5f, -2.24f, 5f, -5f)
                reflectiveCurveToRelative(-2.24f, -5f, -5f, -5f)
                close()
                moveTo(12f, 2f)
                curveTo(6.48f, 2f, 2f, 6.48f, 2f, 12f)
                reflectiveCurveToRelative(4.48f, 10f, 10f, 10f)
                reflectiveCurveToRelative(10f, -4.48f, 10f, -10f)
                reflectiveCurveTo(17.52f, 2f, 12f, 2f)
                close()
                moveTo(12f, 20f)
                curveToRelative(-4.42f, 0f, -8f, -3.58f, -8f, -8f)
                reflectiveCurveToRelative(3.58f, -8f, 8f, -8f)
                reflectiveCurveToRelative(8f, 3.58f, 8f, 8f)
                reflectiveCurveToRelative(-3.58f, 8f, -8f, 8f)
                close()
            }
        }.build()
        return _radioButtonChecked!!
    }

// ─── AccountBalance (uses Security path as substitute) ──────────────────────────

private var _accountBalance: ImageVector? = null
val CIRISMaterialIcons.Filled.AccountBalance: ImageVector
    get() {
        if (_accountBalance != null) return _accountBalance!!
        _accountBalance = ImageVector.Builder(
            name = "Filled.AccountBalance",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 1f)
                lineTo(3f, 5f)
                verticalLineToRelative(6f)
                curveToRelative(0f, 5.55f, 3.84f, 10.74f, 9f, 12f)
                curveToRelative(5.16f, -1.26f, 9f, -6.45f, 9f, -12f)
                verticalLineTo(5f)
                lineToRelative(-9f, -4f)
                close()
                moveTo(12f, 11.99f)
                horizontalLineToRelative(7f)
                curveToRelative(-0.53f, 4.12f, -3.28f, 7.79f, -7f, 8.94f)
                verticalLineTo(12f)
                horizontalLineTo(5f)
                verticalLineTo(6.3f)
                lineToRelative(7f, -3.11f)
                verticalLineToRelative(8.8f)
                close()
            }
        }.build()
        return _accountBalance!!
    }

// ─── Blinds (uses Remove/horizontal line as placeholder) ────────────────────────

private var _blinds: ImageVector? = null
val CIRISMaterialIcons.Filled.Blinds: ImageVector
    get() {
        if (_blinds != null) return _blinds!!
        _blinds = ImageVector.Builder(
            name = "Filled.Blinds",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(19f, 13f)
                horizontalLineTo(5f)
                verticalLineToRelative(-2f)
                horizontalLineToRelative(14f)
                verticalLineToRelative(2f)
                close()
            }
        }.build()
        return _blinds!!
    }

// ─── AutoMode (uses Sync path as substitute) ────────────────────────────────────

private var _autoMode: ImageVector? = null
val CIRISMaterialIcons.Filled.AutoMode: ImageVector
    get() {
        if (_autoMode != null) return _autoMode!!
        _autoMode = ImageVector.Builder(
            name = "Filled.AutoMode",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path {
                moveTo(12f, 4f)
                verticalLineTo(1f)
                lineTo(8f, 5f)
                lineToRelative(4f, 4f)
                verticalLineTo(6f)
                curveToRelative(3.31f, 0f, 6f, 2.69f, 6f, 6f)
                curveToRelative(0f, 1.01f, -0.25f, 1.97f, -0.7f, 2.8f)
                lineToRelative(1.46f, 1.46f)
                curveTo(19.54f, 15.03f, 20f, 13.57f, 20f, 12f)
                curveToRelative(0f, -4.42f, -3.58f, -8f, -8f, -8f)
                close()
                moveTo(12f, 18f)
                curveToRelative(-3.31f, 0f, -6f, -2.69f, -6f, -6f)
                curveToRelative(0f, -1.01f, 0.25f, -1.97f, 0.7f, -2.8f)
                lineTo(5.24f, 7.74f)
                curveTo(4.46f, 8.97f, 4f, 10.43f, 4f, 12f)
                curveToRelative(0f, 4.42f, 3.58f, 8f, 8f, 8f)
                verticalLineToRelative(3f)
                lineToRelative(4f, -4f)
                lineToRelative(-4f, -4f)
                verticalLineToRelative(3f)
                close()
            }
        }.build()
        return _autoMode!!
    }

// =============================================================================
// CIRIS Custom Icons (from Icon Redesign spec)
// =============================================================================
// These icons are custom-designed for CIRIS to replace generic Material icons.
// Each icon uses the bus color palette and is designed for 24dp at 2px strokes.

// ─── CIRISSpeak (paper-plane) ───────────────────────────────────────────────────

private var _cirisSpeak: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISSpeak: ImageVector
    get() {
        if (_cirisSpeak != null) return _cirisSpeak!!
        _cirisSpeak = ImageVector.Builder(
            name = "Filled.CIRISSpeak",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Paper-plane outline
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(4f, 5.5f)
                lineTo(20f, 12f)
                lineTo(4f, 18.5f)
                lineTo(6.5f, 12f)
                close()
            }
            // Inner message spine
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round,
                pathFillType = androidx.compose.ui.graphics.PathFillType.NonZero
            ) {
                moveTo(6.5f, 12f)
                lineTo(13f, 12f)
            }
        }.build()
        return _cirisSpeak!!
    }

// ─── CIRISObserve (eye with catchlight) ─────────────────────────────────────────

private var _cirisObserve: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISObserve: ImageVector
    get() {
        if (_cirisObserve != null) return _cirisObserve!!
        _cirisObserve = ImageVector.Builder(
            name = "Filled.CIRISObserve",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Eye outline
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(2.5f, 12f)
                curveTo(5f, 7f, 9f, 5f, 12f, 5f)
                curveTo(15f, 5f, 19f, 7f, 21.5f, 12f)
                curveTo(19f, 17f, 15f, 19f, 12f, 19f)
                curveTo(9f, 19f, 5f, 17f, 2.5f, 12f)
                close()
            }
            // Filled iris
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 8.8f)
                curveToRelative(1.77f, 0f, 3.2f, 1.43f, 3.2f, 3.2f)
                reflectiveCurveToRelative(-1.43f, 3.2f, -3.2f, 3.2f)
                reflectiveCurveToRelative(-3.2f, -1.43f, -3.2f, -3.2f)
                reflectiveCurveToRelative(1.43f, -3.2f, 3.2f, -3.2f)
                close()
            }
        }.build()
        return _cirisObserve!!
    }

// ─── CIRISMemorize (graph node with timestamp) ──────────────────────────────────

private var _cirisMemorize: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISMemorize: ImageVector
    get() {
        if (_cirisMemorize != null) return _cirisMemorize!!
        _cirisMemorize = ImageVector.Builder(
            name = "Filled.CIRISMemorize",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Outer ring
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(12f, 4.5f)
                curveToRelative(4.14f, 0f, 7.5f, 3.36f, 7.5f, 7.5f)
                reflectiveCurveToRelative(-3.36f, 7.5f, -7.5f, 7.5f)
                reflectiveCurveToRelative(-7.5f, -3.36f, -7.5f, -7.5f)
                reflectiveCurveToRelative(3.36f, -7.5f, 7.5f, -7.5f)
            }
            // Center node (filled)
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 8.8f)
                curveToRelative(1.77f, 0f, 3.2f, 1.43f, 3.2f, 3.2f)
                reflectiveCurveToRelative(-1.43f, 3.2f, -3.2f, 3.2f)
                reflectiveCurveToRelative(-3.2f, -1.43f, -3.2f, -3.2f)
                reflectiveCurveToRelative(1.43f, -3.2f, 3.2f, -3.2f)
                close()
            }
            // Timestamp ticks
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 4.5f)
                verticalLineTo(2.5f)
                moveTo(12f, 21.5f)
                verticalLineTo(19.5f)
                moveTo(4.5f, 12f)
                horizontalLineTo(2.5f)
                moveTo(21.5f, 12f)
                horizontalLineTo(19.5f)
            }
        }.build()
        return _cirisMemorize!!
    }

// ─── CIRISRecall (edges to center - FIX for red ?) ──────────────────────────────

private var _cirisRecall: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISRecall: ImageVector
    get() {
        if (_cirisRecall != null) return _cirisRecall!!
        _cirisRecall = ImageVector.Builder(
            name = "Filled.CIRISRecall",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Center node (filled)
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 8.8f)
                curveToRelative(1.77f, 0f, 3.2f, 1.43f, 3.2f, 3.2f)
                reflectiveCurveToRelative(-1.43f, 3.2f, -3.2f, 3.2f)
                reflectiveCurveToRelative(-3.2f, -1.43f, -3.2f, -3.2f)
                reflectiveCurveToRelative(1.43f, -3.2f, 3.2f, -3.2f)
                close()
            }
            // Satellite nodes
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                // Top-left satellite
                moveTo(5f, 6.8f)
                curveToRelative(0f, 0.94f, 0.76f, 1.7f, 1.7f, 1.7f)
                reflectiveCurveToRelative(1.7f, -0.76f, 1.7f, -1.7f)
                reflectiveCurveToRelative(-0.76f, -1.7f, -1.7f, -1.7f)
                reflectiveCurveToRelative(-1.7f, 0.76f, -1.7f, 1.7f)
                // Top-right satellite
                moveTo(17.3f, 6.8f)
                curveToRelative(0f, 0.94f, 0.76f, 1.7f, 1.7f, 1.7f)
                reflectiveCurveToRelative(1.7f, -0.76f, 1.7f, -1.7f)
                reflectiveCurveToRelative(-0.76f, -1.7f, -1.7f, -1.7f)
                reflectiveCurveToRelative(-1.7f, 0.76f, -1.7f, 1.7f)
                // Bottom-left satellite
                moveTo(5f, 17.2f)
                curveToRelative(0f, 0.94f, 0.76f, 1.7f, 1.7f, 1.7f)
                reflectiveCurveToRelative(1.7f, -0.76f, 1.7f, -1.7f)
                reflectiveCurveToRelative(-0.76f, -1.7f, -1.7f, -1.7f)
                reflectiveCurveToRelative(-1.7f, 0.76f, -1.7f, 1.7f)
                // Bottom-right satellite
                moveTo(17.3f, 17.2f)
                curveToRelative(0f, 0.94f, 0.76f, 1.7f, 1.7f, 1.7f)
                reflectiveCurveToRelative(1.7f, -0.76f, 1.7f, -1.7f)
                reflectiveCurveToRelative(-0.76f, -1.7f, -1.7f, -1.7f)
                reflectiveCurveToRelative(-1.7f, 0.76f, -1.7f, 1.7f)
            }
            // Edge lines to center
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(6.3f, 9.3f)
                lineTo(10f, 11.2f)
                moveTo(17.7f, 9.3f)
                lineTo(14f, 11.2f)
                moveTo(6.3f, 14.7f)
                lineTo(10f, 12.8f)
                moveTo(17.7f, 14.7f)
                lineTo(14f, 12.8f)
            }
        }.build()
        return _cirisRecall!!
    }

// ─── CIRISForget (dissolving node) ──────────────────────────────────────────────

private var _cirisForget: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISForget: ImageVector
    get() {
        if (_cirisForget != null) return _cirisForget!!
        _cirisForget = ImageVector.Builder(
            name = "Filled.CIRISForget",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Main node (fading left)
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(9f, 9f)
                curveToRelative(1.66f, 0f, 3f, 1.34f, 3f, 3f)
                reflectiveCurveToRelative(-1.34f, 3f, -3f, 3f)
                reflectiveCurveToRelative(-3f, -1.34f, -3f, -3f)
                reflectiveCurveToRelative(1.34f, -3f, 3f, -3f)
                close()
            }
            // Dissolving circles (fading right)
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(14f, 9.8f)
                curveToRelative(1.21f, 0f, 2.2f, 0.99f, 2.2f, 2.2f)
                reflectiveCurveToRelative(-0.99f, 2.2f, -2.2f, 2.2f)
                reflectiveCurveToRelative(-2.2f, -0.99f, -2.2f, -2.2f)
                reflectiveCurveToRelative(0.99f, -2.2f, 2.2f, -2.2f)
            }
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(18f, 10.6f)
                curveToRelative(0.77f, 0f, 1.4f, 0.63f, 1.4f, 1.4f)
                reflectiveCurveToRelative(-0.63f, 1.4f, -1.4f, 1.4f)
                reflectiveCurveToRelative(-1.4f, -0.63f, -1.4f, -1.4f)
                reflectiveCurveToRelative(0.63f, -1.4f, 1.4f, -1.4f)
            }
            path(
                strokeLineWidth = 1f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(21.2f, 11.2f)
                curveToRelative(0.44f, 0f, 0.8f, 0.36f, 0.8f, 0.8f)
                reflectiveCurveToRelative(-0.36f, 0.8f, -0.8f, 0.8f)
                reflectiveCurveToRelative(-0.8f, -0.36f, -0.8f, -0.8f)
                reflectiveCurveToRelative(0.36f, -0.8f, 0.8f, -0.8f)
            }
            // Fade arrow
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(3f, 8f)
                lineTo(6.5f, 12f)
                lineTo(3f, 16f)
            }
        }.build()
        return _cirisForget!!
    }

// ─── CIRISTool (wrench head) ────────────────────────────────────────────────────

private var _cirisTool: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISTool: ImageVector
    get() {
        if (_cirisTool != null) return _cirisTool!!
        _cirisTool = ImageVector.Builder(
            name = "Filled.CIRISTool",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Handle
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(4.5f, 19.5f)
                lineTo(11f, 13f)
            }
            // Wrench head
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(10f, 9f)
                lineTo(15f, 14f)
                lineTo(19f, 10f)
                curveTo(19f, 10f, 20f, 8f, 18.5f, 6.5f)
                curveTo(17f, 5f, 15f, 6f, 15f, 6f)
                lineTo(10f, 9f)
                close()
            }
            // Handle end dot
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(5.2f, 17.8f)
                curveToRelative(0.55f, 0f, 1f, 0.45f, 1f, 1f)
                reflectiveCurveToRelative(-0.45f, 1f, -1f, 1f)
                reflectiveCurveToRelative(-1f, -0.45f, -1f, -1f)
                reflectiveCurveToRelative(0.45f, -1f, 1f, -1f)
                close()
            }
        }.build()
        return _cirisTool!!
    }

// ─── CIRISPonder (orbiting thought) ─────────────────────────────────────────────

private var _cirisPonder: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISPonder: ImageVector
    get() {
        if (_cirisPonder != null) return _cirisPonder!!
        _cirisPonder = ImageVector.Builder(
            name = "Filled.CIRISPonder",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Center kernel (filled)
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 9.8f)
                curveToRelative(1.21f, 0f, 2.2f, 0.99f, 2.2f, 2.2f)
                reflectiveCurveToRelative(-0.99f, 2.2f, -2.2f, 2.2f)
                reflectiveCurveToRelative(-2.2f, -0.99f, -2.2f, -2.2f)
                reflectiveCurveToRelative(0.99f, -2.2f, 2.2f, -2.2f)
                close()
            }
            // Inner orbit
            path(
                strokeLineWidth = 1.5f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 6.5f)
                curveToRelative(3.04f, 0f, 5.5f, 2.46f, 5.5f, 5.5f)
                reflectiveCurveToRelative(-2.46f, 5.5f, -5.5f, 5.5f)
                reflectiveCurveToRelative(-5.5f, -2.46f, -5.5f, -5.5f)
                reflectiveCurveToRelative(2.46f, -5.5f, 5.5f, -5.5f)
            }
            // Outer orbit (dashed)
            path(
                strokeLineWidth = 1.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 3f)
                curveToRelative(4.97f, 0f, 9f, 4.03f, 9f, 9f)
                reflectiveCurveToRelative(-4.03f, 9f, -9f, 9f)
                reflectiveCurveToRelative(-9f, -4.03f, -9f, -9f)
                reflectiveCurveToRelative(4.03f, -9f, 9f, -9f)
            }
            // Orbiting satellite
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(20f, 6f)
                curveToRelative(0.55f, 0f, 1f, 0.45f, 1f, 1f)
                reflectiveCurveToRelative(-0.45f, 1f, -1f, 1f)
                reflectiveCurveToRelative(-1f, -0.45f, -1f, -1f)
                reflectiveCurveToRelative(0.45f, -1f, 1f, -1f)
                close()
            }
        }.build()
        return _cirisPonder!!
    }

// ─── CIRISDefer (escalation path) ───────────────────────────────────────────────

private var _cirisDefer: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISDefer: ImageVector
    get() {
        if (_cirisDefer != null) return _cirisDefer!!
        _cirisDefer = ImageVector.Builder(
            name = "Filled.CIRISDefer",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Escalation path
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(5f, 18f)
                lineTo(10f, 13f)
                lineTo(13f, 16f)
                lineTo(19f, 10f)
            }
            // Arrow head
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(15f, 10f)
                horizontalLineTo(19f)
                verticalLineTo(14f)
            }
            // Base line (faded)
            path(
                strokeLineWidth = 1.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(5f, 18f)
                horizontalLineTo(19f)
            }
            // Endpoint dot
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(19f, 8.6f)
                curveToRelative(0.77f, 0f, 1.4f, 0.63f, 1.4f, 1.4f)
                reflectiveCurveToRelative(-0.63f, 1.4f, -1.4f, 1.4f)
                reflectiveCurveToRelative(-1.4f, -0.63f, -1.4f, -1.4f)
                reflectiveCurveToRelative(0.63f, -1.4f, 1.4f, -1.4f)
                close()
            }
        }.build()
        return _cirisDefer!!
    }

// ─── CIRISReject (circle-slash) ─────────────────────────────────────────────────

private var _cirisReject: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISReject: ImageVector
    get() {
        if (_cirisReject != null) return _cirisReject!!
        _cirisReject = ImageVector.Builder(
            name = "Filled.CIRISReject",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Circle
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(12f, 4f)
                curveToRelative(4.42f, 0f, 8f, 3.58f, 8f, 8f)
                reflectiveCurveToRelative(-3.58f, 8f, -8f, 8f)
                reflectiveCurveToRelative(-8f, -3.58f, -8f, -8f)
                reflectiveCurveToRelative(3.58f, -8f, 8f, -8f)
            }
            // Slash
            path(
                strokeLineWidth = 2.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(6.5f, 6.5f)
                lineTo(17.5f, 17.5f)
            }
        }.build()
        return _cirisReject!!
    }

// ─── CIRISTaskComplete (check-disc) ─────────────────────────────────────────────

private var _cirisTaskComplete: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISTaskComplete: ImageVector
    get() {
        if (_cirisTaskComplete != null) return _cirisTaskComplete!!
        _cirisTaskComplete = ImageVector.Builder(
            name = "Filled.CIRISTaskComplete",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Filled circle background (will be tinted)
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 4f)
                curveToRelative(4.42f, 0f, 8f, 3.58f, 8f, 8f)
                reflectiveCurveToRelative(-3.58f, 8f, -8f, 8f)
                reflectiveCurveToRelative(-8f, -3.58f, -8f, -8f)
                reflectiveCurveToRelative(3.58f, -8f, 8f, -8f)
                close()
            }
            // Checkmark (will show through as background color)
            path(
                strokeLineWidth = 2.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(7.5f, 12.2f)
                lineTo(10.8f, 15.5f)
                lineTo(16.5f, 8.5f)
            }
        }.build()
        return _cirisTaskComplete!!
    }

// ─── CIRISThoughtStart (radiating seed) ─────────────────────────────────────────

private var _cirisThoughtStart: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISThoughtStart: ImageVector
    get() {
        if (_cirisThoughtStart != null) return _cirisThoughtStart!!
        _cirisThoughtStart = ImageVector.Builder(
            name = "Filled.CIRISThoughtStart",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Center seed (filled)
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 9.6f)
                curveToRelative(1.32f, 0f, 2.4f, 1.08f, 2.4f, 2.4f)
                reflectiveCurveToRelative(-1.08f, 2.4f, -2.4f, 2.4f)
                reflectiveCurveToRelative(-2.4f, -1.08f, -2.4f, -2.4f)
                reflectiveCurveToRelative(1.08f, -2.4f, 2.4f, -2.4f)
                close()
            }
            // Radiating rays (strong)
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 12f)
                lineTo(12f, 3f)
                moveTo(12f, 12f)
                lineTo(19f, 8f)
                moveTo(12f, 12f)
                lineTo(19f, 16f)
            }
            // Radiating rays (faded)
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 12f)
                lineTo(12f, 21f)
                moveTo(12f, 12f)
                lineTo(5f, 16f)
                moveTo(12f, 12f)
                lineTo(5f, 8f)
            }
        }.build()
        return _cirisThoughtStart!!
    }

// ─── CIRISSnapshot (camera viewport) ────────────────────────────────────────────

private var _cirisSnapshot: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISSnapshot: ImageVector
    get() {
        if (_cirisSnapshot != null) return _cirisSnapshot!!
        _cirisSnapshot = ImageVector.Builder(
            name = "Filled.CIRISSnapshot",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Camera body
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(3.5f, 8.5f)
                curveToRelative(0f, -1.38f, 1.12f, -2.5f, 2.5f, -2.5f)
                horizontalLineToRelative(12f)
                curveToRelative(1.38f, 0f, 2.5f, 1.12f, 2.5f, 2.5f)
                verticalLineToRelative(10f)
                curveToRelative(0f, 1.38f, -1.12f, 2.5f, -2.5f, 2.5f)
                horizontalLineToRelative(-12f)
                curveToRelative(-1.38f, 0f, -2.5f, -1.12f, -2.5f, -2.5f)
                close()
            }
            // Top notch
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(9f, 6f)
                lineTo(9.8f, 4.2f)
                horizontalLineTo(14.2f)
                lineTo(15f, 6f)
            }
            // Lens (filled center)
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 11.3f)
                curveToRelative(0.66f, 0f, 1.2f, 0.54f, 1.2f, 1.2f)
                reflectiveCurveToRelative(-0.54f, 1.2f, -1.2f, 1.2f)
                reflectiveCurveToRelative(-1.2f, -0.54f, -1.2f, -1.2f)
                reflectiveCurveToRelative(0.54f, -1.2f, 1.2f, -1.2f)
                close()
            }
            // Lens ring
            path(
                strokeLineWidth = 1.6f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 9.3f)
                curveToRelative(1.77f, 0f, 3.2f, 1.43f, 3.2f, 3.2f)
                reflectiveCurveToRelative(-1.43f, 3.2f, -3.2f, 3.2f)
                reflectiveCurveToRelative(-3.2f, -1.43f, -3.2f, -3.2f)
                reflectiveCurveToRelative(1.43f, -3.2f, 3.2f, -3.2f)
            }
        }.build()
        return _cirisSnapshot!!
    }

// ─── CIRISDMA (bar chart ensemble) ──────────────────────────────────────────────

private var _cirisDMA: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISDMA: ImageVector
    get() {
        if (_cirisDMA != null) return _cirisDMA!!
        _cirisDMA = ImageVector.Builder(
            name = "Filled.CIRISDMA",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Base line
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(3f, 20f)
                horizontalLineTo(21f)
            }
            // Bars
            path(
                strokeLineWidth = 2.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(6f, 20f)
                verticalLineTo(14f)
                moveTo(10f, 20f)
                verticalLineTo(10f)
                moveTo(14f, 20f)
                verticalLineTo(6f)
                moveTo(18f, 20f)
                verticalLineTo(12f)
            }
            // Active highlight on tallest bar
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(14f, 4.4f)
                curveToRelative(0.88f, 0f, 1.6f, 0.72f, 1.6f, 1.6f)
                reflectiveCurveToRelative(-0.72f, 1.6f, -1.6f, 1.6f)
                reflectiveCurveToRelative(-1.6f, -0.72f, -1.6f, -1.6f)
                reflectiveCurveToRelative(0.72f, -1.6f, 1.6f, -1.6f)
                close()
            }
        }.build()
        return _cirisDMA!!
    }

// ─── CIRISIDMA (coherence ring with probe) ──────────────────────────────────────

private var _cirisIDMA: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISIDMA: ImageVector
    get() {
        if (_cirisIDMA != null) return _cirisIDMA!!
        _cirisIDMA = ImageVector.Builder(
            name = "Filled.CIRISIDMA",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Center kernel
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 9.4f)
                curveToRelative(1.44f, 0f, 2.6f, 1.16f, 2.6f, 2.6f)
                reflectiveCurveToRelative(-1.16f, 2.6f, -2.6f, 2.6f)
                reflectiveCurveToRelative(-2.6f, -1.16f, -2.6f, -2.6f)
                reflectiveCurveToRelative(1.16f, -2.6f, 2.6f, -2.6f)
                close()
            }
            // Inner coherence ring (dashed)
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 6.5f)
                curveToRelative(3.04f, 0f, 5.5f, 2.46f, 5.5f, 5.5f)
                reflectiveCurveToRelative(-2.46f, 5.5f, -5.5f, 5.5f)
                reflectiveCurveToRelative(-5.5f, -2.46f, -5.5f, -5.5f)
                reflectiveCurveToRelative(2.46f, -5.5f, 5.5f, -5.5f)
            }
            // Outer ring (more dashed)
            path(
                strokeLineWidth = 1f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 3f)
                curveToRelative(4.97f, 0f, 9f, 4.03f, 9f, 9f)
                reflectiveCurveToRelative(-4.03f, 9f, -9f, 9f)
                reflectiveCurveToRelative(-9f, -4.03f, -9f, -9f)
                reflectiveCurveToRelative(4.03f, -9f, 9f, -9f)
            }
            // Vertical probe
            path(
                strokeLineWidth = 1.6f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 3f)
                lineTo(12f, 7f)
            }
        }.build()
        return _cirisIDMA!!
    }

// ─── CIRISActionSelection (tuning axis) ─────────────────────────────────────────

private var _cirisActionSelection: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISActionSelection: ImageVector
    get() {
        if (_cirisActionSelection != null) return _cirisActionSelection!!
        _cirisActionSelection = ImageVector.Builder(
            name = "Filled.CIRISActionSelection",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Horizontal axis
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(4f, 12f)
                horizontalLineTo(20f)
            }
            // Active node (first/selected)
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(8f, 10.6f)
                curveToRelative(0.77f, 0f, 1.4f, 0.63f, 1.4f, 1.4f)
                reflectiveCurveToRelative(-0.63f, 1.4f, -1.4f, 1.4f)
                reflectiveCurveToRelative(-1.4f, -0.63f, -1.4f, -1.4f)
                reflectiveCurveToRelative(0.63f, -1.4f, 1.4f, -1.4f)
                close()
            }
            // Inactive nodes
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(13f, 10.6f)
                curveToRelative(0.77f, 0f, 1.4f, 0.63f, 1.4f, 1.4f)
                reflectiveCurveToRelative(-0.63f, 1.4f, -1.4f, 1.4f)
                reflectiveCurveToRelative(-1.4f, -0.63f, -1.4f, -1.4f)
                reflectiveCurveToRelative(0.63f, -1.4f, 1.4f, -1.4f)
                moveTo(18f, 10.6f)
                curveToRelative(0.77f, 0f, 1.4f, 0.63f, 1.4f, 1.4f)
                reflectiveCurveToRelative(-0.63f, 1.4f, -1.4f, 1.4f)
                reflectiveCurveToRelative(-1.4f, -0.63f, -1.4f, -1.4f)
                reflectiveCurveToRelative(0.63f, -1.4f, 1.4f, -1.4f)
            }
            // Vertical selection lines
            path(
                strokeLineWidth = 1.6f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(8f, 4f)
                verticalLineTo(12f)
                moveTo(8f, 20f)
                verticalLineTo(12f)
            }
            // Selection endpoints
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(8f, 2.4f)
                curveToRelative(0.88f, 0f, 1.6f, 0.72f, 1.6f, 1.6f)
                reflectiveCurveToRelative(-0.72f, 1.6f, -1.6f, 1.6f)
                reflectiveCurveToRelative(-1.6f, -0.72f, -1.6f, -1.6f)
                reflectiveCurveToRelative(0.72f, -1.6f, 1.6f, -1.6f)
                moveTo(8f, 18.4f)
                curveToRelative(0.88f, 0f, 1.6f, 0.72f, 1.6f, 1.6f)
                reflectiveCurveToRelative(-0.72f, 1.6f, -1.6f, 1.6f)
                reflectiveCurveToRelative(-1.6f, -0.72f, -1.6f, -1.6f)
                reflectiveCurveToRelative(0.72f, -1.6f, 1.6f, -1.6f)
            }
        }.build()
        return _cirisActionSelection!!
    }

// ─── CIRISTSASPDMA (wireframe cube) ─────────────────────────────────────────────

private var _cirisTSASPDMA: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISTSASPDMA: ImageVector
    get() {
        if (_cirisTSASPDMA != null) return _cirisTSASPDMA!!
        _cirisTSASPDMA = ImageVector.Builder(
            name = "Filled.CIRISTSASPDMA",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Hexagonal outline (3-axis wireframe)
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(12f, 3f)
                lineTo(19.5f, 7.5f)
                verticalLineTo(16.5f)
                lineTo(12f, 21f)
                lineTo(4.5f, 16.5f)
                verticalLineTo(7.5f)
                close()
            }
            // Internal spokes to center
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 3f)
                verticalLineTo(12f)
                moveTo(19.5f, 7.5f)
                lineTo(12f, 12f)
                moveTo(4.5f, 7.5f)
                lineTo(12f, 12f)
                moveTo(12f, 12f)
                verticalLineTo(21f)
            }
            // Center node
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 10.2f)
                curveToRelative(0.99f, 0f, 1.8f, 0.81f, 1.8f, 1.8f)
                reflectiveCurveToRelative(-0.81f, 1.8f, -1.8f, 1.8f)
                reflectiveCurveToRelative(-1.8f, -0.81f, -1.8f, -1.8f)
                reflectiveCurveToRelative(0.81f, -1.8f, 1.8f, -1.8f)
                close()
            }
        }.build()
        return _cirisTSASPDMA!!
    }

// ─── CIRISConscience (shield + cross) ───────────────────────────────────────────

private var _cirisConscience: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISConscience: ImageVector
    get() {
        if (_cirisConscience != null) return _cirisConscience!!
        _cirisConscience = ImageVector.Builder(
            name = "Filled.CIRISConscience",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Shield outline
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(12f, 3f)
                lineTo(20f, 6f)
                verticalLineTo(12f)
                curveTo(20f, 17f, 16f, 20.5f, 12f, 21.5f)
                curveTo(8f, 20.5f, 4f, 17f, 4f, 12f)
                verticalLineTo(6f)
                close()
            }
            // Ethical cross
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 8.5f)
                verticalLineTo(15.5f)
                moveTo(8.5f, 12f)
                horizontalLineTo(15.5f)
            }
        }.build()
        return _cirisConscience!!
    }

// ─── CIRISWarning (triangle) ────────────────────────────────────────────────────

private var _cirisWarning: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISWarning: ImageVector
    get() {
        if (_cirisWarning != null) return _cirisWarning!!
        _cirisWarning = ImageVector.Builder(
            name = "Filled.CIRISWarning",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Triangle outline
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(12f, 3f)
                lineTo(21f, 20f)
                horizontalLineTo(3f)
                close()
            }
            // Exclamation line
            path(
                strokeLineWidth = 2.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 9f)
                verticalLineTo(14f)
            }
            // Exclamation dot
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 16.5f)
                curveToRelative(0.55f, 0f, 1f, 0.45f, 1f, 1f)
                reflectiveCurveToRelative(-0.45f, 1f, -1f, 1f)
                reflectiveCurveToRelative(-1f, -0.45f, -1f, -1f)
                reflectiveCurveToRelative(0.45f, -1f, 1f, -1f)
                close()
            }
        }.build()
        return _cirisWarning!!
    }

// ─── CIRISError (circle exclamation) ────────────────────────────────────────────

private var _cirisError: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISError: ImageVector
    get() {
        if (_cirisError != null) return _cirisError!!
        _cirisError = ImageVector.Builder(
            name = "Filled.CIRISError",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Circle
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 4f)
                curveToRelative(4.42f, 0f, 8f, 3.58f, 8f, 8f)
                reflectiveCurveToRelative(-3.58f, 8f, -8f, 8f)
                reflectiveCurveToRelative(-8f, -3.58f, -8f, -8f)
                reflectiveCurveToRelative(3.58f, -8f, 8f, -8f)
            }
            // Exclamation line
            path(
                strokeLineWidth = 2.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 7.5f)
                verticalLineTo(13f)
            }
            // Exclamation dot
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 15.5f)
                curveToRelative(0.55f, 0f, 1f, 0.45f, 1f, 1f)
                reflectiveCurveToRelative(-0.45f, 1f, -1f, 1f)
                reflectiveCurveToRelative(-1f, -0.45f, -1f, -1f)
                reflectiveCurveToRelative(0.45f, -1f, 1f, -1f)
                close()
            }
        }.build()
        return _cirisError!!
    }

// ─── CIRISInfo (circle with i) ──────────────────────────────────────────────────

private var _cirisInfo: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISInfo: ImageVector
    get() {
        if (_cirisInfo != null) return _cirisInfo!!
        _cirisInfo = ImageVector.Builder(
            name = "Filled.CIRISInfo",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Circle
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 4f)
                curveToRelative(4.42f, 0f, 8f, 3.58f, 8f, 8f)
                reflectiveCurveToRelative(-3.58f, 8f, -8f, 8f)
                reflectiveCurveToRelative(-8f, -3.58f, -8f, -8f)
                reflectiveCurveToRelative(3.58f, -8f, 8f, -8f)
            }
            // Info line
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 11f)
                verticalLineTo(16f)
            }
            // Info dot
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 7f)
                curveToRelative(0.55f, 0f, 1f, 0.45f, 1f, 1f)
                reflectiveCurveToRelative(-0.45f, 1f, -1f, 1f)
                reflectiveCurveToRelative(-1f, -0.45f, -1f, -1f)
                reflectiveCurveToRelative(0.45f, -1f, 1f, -1f)
                close()
            }
        }.build()
        return _cirisInfo!!
    }

// ─── CIRISSuccess (check circle) ────────────────────────────────────────────────

private var _cirisSuccess: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISSuccess: ImageVector
    get() {
        if (_cirisSuccess != null) return _cirisSuccess!!
        _cirisSuccess = ImageVector.Builder(
            name = "Filled.CIRISSuccess",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Circle
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 4f)
                curveToRelative(4.42f, 0f, 8f, 3.58f, 8f, 8f)
                reflectiveCurveToRelative(-3.58f, 8f, -8f, 8f)
                reflectiveCurveToRelative(-8f, -3.58f, -8f, -8f)
                reflectiveCurveToRelative(3.58f, -8f, 8f, -8f)
            }
            // Checkmark
            path(
                strokeLineWidth = 2.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(8f, 12.4f)
                lineTo(10.8f, 15f)
                lineTo(16.5f, 9f)
            }
        }.build()
        return _cirisSuccess!!
    }

// ─── CIRISTrust (shield with check) ─────────────────────────────────────────────

private var _cirisTrust: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISTrust: ImageVector
    get() {
        if (_cirisTrust != null) return _cirisTrust!!
        _cirisTrust = ImageVector.Builder(
            name = "Filled.CIRISTrust",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Shield outline
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(12f, 3f)
                lineTo(20f, 6f)
                verticalLineTo(12f)
                curveTo(20f, 17f, 16f, 20.5f, 12f, 21.5f)
                curveTo(8f, 20.5f, 4f, 17f, 4f, 12f)
                verticalLineTo(6f)
                close()
            }
            // Checkmark
            path(
                strokeLineWidth = 2.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(8.5f, 12f)
                lineTo(11f, 14.5f)
                lineTo(16f, 9.5f)
            }
        }.build()
        return _cirisTrust!!
    }

// ─── CIRISIdle (concentric rings) ───────────────────────────────────────────────

private var _cirisIdle: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISIdle: ImageVector
    get() {
        if (_cirisIdle != null) return _cirisIdle!!
        _cirisIdle = ImageVector.Builder(
            name = "Filled.CIRISIdle",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Center dot
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 9f)
                curveToRelative(1.66f, 0f, 3f, 1.34f, 3f, 3f)
                reflectiveCurveToRelative(-1.34f, 3f, -3f, 3f)
                reflectiveCurveToRelative(-3f, -1.34f, -3f, -3f)
                reflectiveCurveToRelative(1.34f, -3f, 3f, -3f)
                close()
            }
            // Inner ring
            path(
                strokeLineWidth = 1.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 4.5f)
                curveToRelative(4.14f, 0f, 7.5f, 3.36f, 7.5f, 7.5f)
                reflectiveCurveToRelative(-3.36f, 7.5f, -7.5f, 7.5f)
                reflectiveCurveToRelative(-7.5f, -3.36f, -7.5f, -7.5f)
                reflectiveCurveToRelative(3.36f, -7.5f, 7.5f, -7.5f)
            }
            // Outer ring (dashed effect)
            path(
                strokeLineWidth = 0.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 2f)
                curveToRelative(5.52f, 0f, 10f, 4.48f, 10f, 10f)
                reflectiveCurveToRelative(-4.48f, 10f, -10f, 10f)
                reflectiveCurveToRelative(-10f, -4.48f, -10f, -10f)
                reflectiveCurveToRelative(4.48f, -10f, 10f, -10f)
            }
        }.build()
        return _cirisIdle!!
    }

// ─── CIRISProcessing (sync arrows) ──────────────────────────────────────────────

private var _cirisProcessing: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISProcessing: ImageVector
    get() {
        if (_cirisProcessing != null) return _cirisProcessing!!
        _cirisProcessing = ImageVector.Builder(
            name = "Filled.CIRISProcessing",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Upper arc with arrow
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(4f, 12f)
                curveToRelative(0f, -4.42f, 3.58f, -8f, 8f, -8f)
                curveToRelative(2.76f, 0f, 5.2f, 1.4f, 6.64f, 3.52f)
                moveTo(17f, 3f)
                verticalLineTo(7f)
                horizontalLineTo(13f)
            }
            // Lower arc with arrow (faded)
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(20f, 12f)
                curveToRelative(0f, 4.42f, -3.58f, 8f, -8f, 8f)
                curveToRelative(-2.76f, 0f, -5.2f, -1.4f, -6.64f, -3.52f)
                moveTo(7f, 21f)
                verticalLineTo(17f)
                horizontalLineTo(11f)
            }
        }.build()
        return _cirisProcessing!!
    }

// ─── CIRISDisconnected (cloud off slash) ────────────────────────────────────────

private var _cirisDisconnected: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISDisconnected: ImageVector
    get() {
        if (_cirisDisconnected != null) return _cirisDisconnected!!
        _cirisDisconnected = ImageVector.Builder(
            name = "Filled.CIRISDisconnected",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Cloud outline
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(6f, 16f)
                curveTo(3.5f, 16f, 2f, 14f, 2f, 12f)
                curveTo(2f, 10f, 3.5f, 8f, 6f, 8f)
                curveTo(6.3f, 6f, 8.5f, 4f, 11f, 4f)
                curveTo(13f, 4f, 15f, 5f, 16f, 7f)
            }
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(16f, 11f)
                curveTo(18.5f, 11f, 20f, 13f, 20f, 15f)
                curveTo(20f, 17f, 18.5f, 19f, 16f, 19f)
                horizontalLineTo(10f)
            }
            // Strike-through
            path(
                strokeLineWidth = 2.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(4f, 4f)
                lineTo(20f, 20f)
            }
        }.build()
        return _cirisDisconnected!!
    }

// ─── CIRISLightning (bolt) ──────────────────────────────────────────────────────

private var _cirisLightning: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISLightning: ImageVector
    get() {
        if (_cirisLightning != null) return _cirisLightning!!
        _cirisLightning = ImageVector.Builder(
            name = "Filled.CIRISLightning",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Lightning bolt
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(13f, 3f)
                lineTo(5f, 13f)
                horizontalLineTo(11f)
                lineTo(10f, 21f)
                lineTo(18f, 11f)
                horizontalLineTo(12f)
                close()
            }
        }.build()
        return _cirisLightning!!
    }

// ─── CIRISIdentity (badge/ID card) ──────────────────────────────────────────────

private var _cirisIdentity: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISIdentity: ImageVector
    get() {
        if (_cirisIdentity != null) return _cirisIdentity!!
        _cirisIdentity = ImageVector.Builder(
            name = "Filled.CIRISIdentity",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Card outline
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(3.5f, 7.5f)
                curveToRelative(0f, -1.38f, 1.12f, -2.5f, 2.5f, -2.5f)
                horizontalLineToRelative(12f)
                curveToRelative(1.38f, 0f, 2.5f, 1.12f, 2.5f, 2.5f)
                verticalLineToRelative(9f)
                curveToRelative(0f, 1.38f, -1.12f, 2.5f, -2.5f, 2.5f)
                horizontalLineToRelative(-12f)
                curveToRelative(-1.38f, 0f, -2.5f, -1.12f, -2.5f, -2.5f)
                close()
            }
            // Avatar circle
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(9f, 9.2f)
                curveToRelative(1.27f, 0f, 2.3f, 1.03f, 2.3f, 2.3f)
                reflectiveCurveToRelative(-1.03f, 2.3f, -2.3f, 2.3f)
                reflectiveCurveToRelative(-2.3f, -1.03f, -2.3f, -2.3f)
                reflectiveCurveToRelative(1.03f, -2.3f, 2.3f, -2.3f)
            }
            // Avatar shoulders
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(5.5f, 16.5f)
                curveTo(6.5f, 14.8f, 11.5f, 14.8f, 12.5f, 16.5f)
            }
            // Text lines
            path(
                strokeLineWidth = 1.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(15f, 10f)
                horizontalLineTo(18f)
                moveTo(15f, 13f)
                horizontalLineTo(18f)
                moveTo(15f, 16f)
                horizontalLineTo(17f)
            }
        }.build()
        return _cirisIdentity!!
    }

// =============================================================================
// CIRIS Utility Icons (replacements for emoji)
// =============================================================================
// These icons replace emoji characters for cross-platform consistency.

// ─── CIRISCheck (checkmark ✓) ───────────────────────────────────────────────────

private var _cirisCheck: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISCheck: ImageVector
    get() {
        if (_cirisCheck != null) return _cirisCheck!!
        _cirisCheck = ImageVector.Builder(
            name = "Filled.CIRISCheck",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path(
                strokeLineWidth = 2.5f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(5f, 12f)
                lineTo(10f, 17f)
                lineTo(19f, 7f)
            }
        }.build()
        return _cirisCheck!!
    }

// ─── CIRISXMark (x mark ✗) ──────────────────────────────────────────────────────

private var _cirisXMark: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISXMark: ImageVector
    get() {
        if (_cirisXMark != null) return _cirisXMark!!
        _cirisXMark = ImageVector.Builder(
            name = "Filled.CIRISXMark",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path(
                strokeLineWidth = 2.5f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(6f, 6f)
                lineTo(18f, 18f)
                moveTo(18f, 6f)
                lineTo(6f, 18f)
            }
        }.build()
        return _cirisXMark!!
    }

// ─── CIRISKey (key/lock 🔐) ─────────────────────────────────────────────────────

private var _cirisKey: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISKey: ImageVector
    get() {
        if (_cirisKey != null) return _cirisKey!!
        _cirisKey = ImageVector.Builder(
            name = "Filled.CIRISKey",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Key head (circle)
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(8f, 4f)
                curveToRelative(2.21f, 0f, 4f, 1.79f, 4f, 4f)
                curveToRelative(0f, 2.21f, -1.79f, 4f, -4f, 4f)
                reflectiveCurveToRelative(-4f, -1.79f, -4f, -4f)
                curveToRelative(0f, -2.21f, 1.79f, -4f, 4f, -4f)
            }
            // Key inner circle
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(8f, 6.5f)
                curveToRelative(0.83f, 0f, 1.5f, 0.67f, 1.5f, 1.5f)
                reflectiveCurveToRelative(-0.67f, 1.5f, -1.5f, 1.5f)
                reflectiveCurveToRelative(-1.5f, -0.67f, -1.5f, -1.5f)
                reflectiveCurveToRelative(0.67f, -1.5f, 1.5f, -1.5f)
            }
            // Key shaft and teeth
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(11f, 11f)
                lineTo(20f, 20f)
                moveTo(17f, 17f)
                lineTo(20f, 14f)
                moveTo(14f, 14f)
                lineTo(17f, 11f)
            }
        }.build()
        return _cirisKey!!
    }

// ─── CIRISGlobe (world 🌍) ──────────────────────────────────────────────────────

private var _cirisGlobe: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISGlobe: ImageVector
    get() {
        if (_cirisGlobe != null) return _cirisGlobe!!
        _cirisGlobe = ImageVector.Builder(
            name = "Filled.CIRISGlobe",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Outer circle
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 3f)
                curveToRelative(4.97f, 0f, 9f, 4.03f, 9f, 9f)
                reflectiveCurveToRelative(-4.03f, 9f, -9f, 9f)
                reflectiveCurveToRelative(-9f, -4.03f, -9f, -9f)
                reflectiveCurveToRelative(4.03f, -9f, 9f, -9f)
            }
            // Vertical meridian
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 3f)
                curveToRelative(-2.5f, 0f, -4.5f, 4.03f, -4.5f, 9f)
                reflectiveCurveToRelative(2f, 9f, 4.5f, 9f)
                curveToRelative(2.5f, 0f, 4.5f, -4.03f, 4.5f, -9f)
                reflectiveCurveToRelative(-2f, -9f, -4.5f, -9f)
            }
            // Horizontal lines
            path(
                strokeLineWidth = 1.2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(3f, 12f)
                horizontalLineTo(21f)
                moveTo(4f, 8f)
                horizontalLineTo(20f)
                moveTo(4f, 16f)
                horizontalLineTo(20f)
            }
        }.build()
        return _cirisGlobe!!
    }

// ─── CIRISChart (telemetry 📊) ──────────────────────────────────────────────────

private var _cirisChart: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISChart: ImageVector
    get() {
        if (_cirisChart != null) return _cirisChart!!
        _cirisChart = ImageVector.Builder(
            name = "Filled.CIRISChart",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Bars
            path(
                strokeLineWidth = 2.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(5f, 18f)
                verticalLineTo(12f)
                moveTo(9f, 18f)
                verticalLineTo(8f)
                moveTo(13f, 18f)
                verticalLineTo(14f)
                moveTo(17f, 18f)
                verticalLineTo(6f)
            }
            // Base line
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(3f, 20f)
                horizontalLineTo(21f)
            }
        }.build()
        return _cirisChart!!
    }

// ─── CIRISRefresh (sync/reload 🔄) ──────────────────────────────────────────────

private var _cirisRefresh: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISRefresh: ImageVector
    get() {
        if (_cirisRefresh != null) return _cirisRefresh!!
        _cirisRefresh = ImageVector.Builder(
            name = "Filled.CIRISRefresh",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Circular arrow
            path(
                strokeLineWidth = 2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(4f, 12f)
                curveToRelative(0f, -4.42f, 3.58f, -8f, 8f, -8f)
                curveToRelative(3.1f, 0f, 5.8f, 1.77f, 7.12f, 4.35f)
                moveTo(17f, 4f)
                lineTo(20f, 8f)
                lineTo(16f, 9f)
            }
            path(
                strokeLineWidth = 2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(20f, 12f)
                curveToRelative(0f, 4.42f, -3.58f, 8f, -8f, 8f)
                curveToRelative(-3.1f, 0f, -5.8f, -1.77f, -7.12f, -4.35f)
                moveTo(7f, 20f)
                lineTo(4f, 16f)
                lineTo(8f, 15f)
            }
        }.build()
        return _cirisRefresh!!
    }

// ─── CIRISWallet (money 💰) ─────────────────────────────────────────────────────

private var _cirisWallet: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISWallet: ImageVector
    get() {
        if (_cirisWallet != null) return _cirisWallet!!
        _cirisWallet = ImageVector.Builder(
            name = "Filled.CIRISWallet",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Wallet body
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(3f, 7f)
                curveToRelative(0f, -1.1f, 0.9f, -2f, 2f, -2f)
                horizontalLineToRelative(14f)
                curveToRelative(1.1f, 0f, 2f, 0.9f, 2f, 2f)
                verticalLineToRelative(10f)
                curveToRelative(0f, 1.1f, -0.9f, 2f, -2f, 2f)
                horizontalLineTo(5f)
                curveToRelative(-1.1f, 0f, -2f, -0.9f, -2f, -2f)
                close()
            }
            // Flap
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(3f, 10f)
                horizontalLineTo(21f)
            }
            // Clasp area
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(17f, 13f)
                horizontalLineTo(21f)
                verticalLineTo(16f)
                horizontalLineTo(17f)
                curveToRelative(-0.83f, 0f, -1.5f, -0.67f, -1.5f, -1.5f)
                reflectiveCurveToRelative(0.67f, -1.5f, 1.5f, -1.5f)
            }
            // Coin dot
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(17.5f, 13.5f)
                curveToRelative(0.55f, 0f, 1f, 0.45f, 1f, 1f)
                reflectiveCurveToRelative(-0.45f, 1f, -1f, 1f)
                reflectiveCurveToRelative(-1f, -0.45f, -1f, -1f)
                reflectiveCurveToRelative(0.45f, -1f, 1f, -1f)
            }
        }.build()
        return _cirisWallet!!
    }

// ─── CIRISGas (gas pump ⛽) ─────────────────────────────────────────────────────

private var _cirisGas: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISGas: ImageVector
    get() {
        if (_cirisGas != null) return _cirisGas!!
        _cirisGas = ImageVector.Builder(
            name = "Filled.CIRISGas",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Pump body
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(4f, 20f)
                verticalLineTo(6f)
                curveToRelative(0f, -1.1f, 0.9f, -2f, 2f, -2f)
                horizontalLineToRelative(6f)
                curveToRelative(1.1f, 0f, 2f, 0.9f, 2f, 2f)
                verticalLineToRelative(14f)
                horizontalLineTo(4f)
            }
            // Display window
            path(
                strokeLineWidth = 1.4f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(6f, 6f)
                horizontalLineToRelative(6f)
                verticalLineToRelative(4f)
                horizontalLineTo(6f)
                close()
            }
            // Nozzle
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(14f, 8f)
                horizontalLineTo(16f)
                curveToRelative(1.1f, 0f, 2f, 0.9f, 2f, 2f)
                verticalLineTo(14f)
                moveTo(18f, 14f)
                lineTo(20f, 12f)
            }
            // Base
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(2f, 20f)
                horizontalLineTo(16f)
            }
        }.build()
        return _cirisGas!!
    }

// ─── CIRISQuestion (question mark ❓) ───────────────────────────────────────────

private var _cirisQuestion: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISQuestion: ImageVector
    get() {
        if (_cirisQuestion != null) return _cirisQuestion!!
        _cirisQuestion = ImageVector.Builder(
            name = "Filled.CIRISQuestion",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Question mark curve
            path(
                strokeLineWidth = 2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(8f, 8f)
                curveToRelative(0f, -2.21f, 1.79f, -4f, 4f, -4f)
                reflectiveCurveToRelative(4f, 1.79f, 4f, 4f)
                curveToRelative(0f, 2f, -1.5f, 3f, -2.5f, 3.5f)
                curveTo(12.5f, 12f, 12f, 13f, 12f, 14f)
            }
            // Dot
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 17f)
                curveToRelative(0.55f, 0f, 1f, 0.45f, 1f, 1f)
                reflectiveCurveToRelative(-0.45f, 1f, -1f, 1f)
                reflectiveCurveToRelative(-1f, -0.45f, -1f, -1f)
                reflectiveCurveToRelative(0.45f, -1f, 1f, -1f)
            }
        }.build()
        return _cirisQuestion!!
    }

// ─── CIRISPlus (plus ➕) ────────────────────────────────────────────────────────

private var _cirisPlus: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISPlus: ImageVector
    get() {
        if (_cirisPlus != null) return _cirisPlus!!
        _cirisPlus = ImageVector.Builder(
            name = "Filled.CIRISPlus",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path(
                strokeLineWidth = 2.5f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 5f)
                verticalLineTo(19f)
                moveTo(5f, 12f)
                horizontalLineTo(19f)
            }
        }.build()
        return _cirisPlus!!
    }

// ─── CIRISMinus (minus ➖) ──────────────────────────────────────────────────────

private var _cirisMinus: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISMinus: ImageVector
    get() {
        if (_cirisMinus != null) return _cirisMinus!!
        _cirisMinus = ImageVector.Builder(
            name = "Filled.CIRISMinus",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path(
                strokeLineWidth = 2.5f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(5f, 12f)
                horizontalLineTo(19f)
            }
        }.build()
        return _cirisMinus!!
    }

// ─── CIRISPause (pause ❚❚) ──────────────────────────────────────────────────────

private var _cirisPause: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISPause: ImageVector
    get() {
        if (_cirisPause != null) return _cirisPause!!
        _cirisPause = ImageVector.Builder(
            name = "Filled.CIRISPause",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path(
                strokeLineWidth = 3f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(8f, 5f)
                verticalLineTo(19f)
                moveTo(16f, 5f)
                verticalLineTo(19f)
            }
        }.build()
        return _cirisPause!!
    }

// ─── CIRISStar (star ⭐) ────────────────────────────────────────────────────────

private var _cirisStar: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISStar: ImageVector
    get() {
        if (_cirisStar != null) return _cirisStar!!
        _cirisStar = ImageVector.Builder(
            name = "Filled.CIRISStar",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 2f)
                lineTo(14.4f, 8.8f)
                lineTo(22f, 9.2f)
                lineTo(16.2f, 14f)
                lineTo(18f, 21.5f)
                lineTo(12f, 17.5f)
                lineTo(6f, 21.5f)
                lineTo(7.8f, 14f)
                lineTo(2f, 9.2f)
                lineTo(9.6f, 8.8f)
                close()
            }
        }.build()
        return _cirisStar!!
    }

// ─── CIRISCircle (empty circle ○) ──────────────────────────────────────────────

private var _cirisCircle: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISCircle: ImageVector
    get() {
        if (_cirisCircle != null) return _cirisCircle!!
        _cirisCircle = ImageVector.Builder(
            name = "Filled.CIRISCircle",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path(
                strokeLineWidth = 2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 4f)
                curveToRelative(4.42f, 0f, 8f, 3.58f, 8f, 8f)
                reflectiveCurveToRelative(-3.58f, 8f, -8f, 8f)
                reflectiveCurveToRelative(-8f, -3.58f, -8f, -8f)
                reflectiveCurveToRelative(3.58f, -8f, 8f, -8f)
            }
        }.build()
        return _cirisCircle!!
    }

// ─── CIRISLocation (map pin 📍) ────────────────────────────────────────────────

private var _cirisLocation: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISLocation: ImageVector
    get() {
        if (_cirisLocation != null) return _cirisLocation!!
        _cirisLocation = ImageVector.Builder(
            name = "Filled.CIRISLocation",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(12f, 2f)
                curveToRelative(-4f, 0f, -7f, 3f, -7f, 7f)
                curveToRelative(0f, 5.25f, 7f, 13f, 7f, 13f)
                reflectiveCurveToRelative(7f, -7.75f, 7f, -13f)
                curveToRelative(0f, -4f, -3f, -7f, -7f, -7f)
            }
            // Center dot
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 6.5f)
                curveToRelative(1.38f, 0f, 2.5f, 1.12f, 2.5f, 2.5f)
                reflectiveCurveToRelative(-1.12f, 2.5f, -2.5f, 2.5f)
                reflectiveCurveToRelative(-2.5f, -1.12f, -2.5f, -2.5f)
                reflectiveCurveToRelative(1.12f, -2.5f, 2.5f, -2.5f)
            }
        }.build()
        return _cirisLocation!!
    }

// ─── CIRISClear (clear/close ✕) ────────────────────────────────────────────────

private var _cirisClear: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISClear: ImageVector
    get() {
        if (_cirisClear != null) return _cirisClear!!
        _cirisClear = ImageVector.Builder(
            name = "Filled.CIRISClear",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Circle background
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(12f, 4f)
                curveToRelative(4.42f, 0f, 8f, 3.58f, 8f, 8f)
                reflectiveCurveToRelative(-3.58f, 8f, -8f, 8f)
                reflectiveCurveToRelative(-8f, -3.58f, -8f, -8f)
                reflectiveCurveToRelative(3.58f, -8f, 8f, -8f)
            }
            // X inside
            path(
                strokeLineWidth = 2f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round
            ) {
                moveTo(8f, 8f)
                lineTo(16f, 16f)
                moveTo(16f, 8f)
                lineTo(8f, 16f)
            }
        }.build()
        return _cirisClear!!
    }

// ─── CIRISTools (hammer ⚒) ─────────────────────────────────────────────────────

private var _cirisTools: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISTools: ImageVector
    get() {
        if (_cirisTools != null) return _cirisTools!!
        _cirisTools = ImageVector.Builder(
            name = "Filled.CIRISTools",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            // Wrench
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(4f, 17f)
                lineTo(9f, 12f)
                moveTo(7f, 5f)
                curveToRelative(2f, -2f, 5f, -1f, 6f, 1f)
                lineTo(9f, 10f)
                lineTo(14f, 15f)
                lineTo(18f, 11f)
                curveToRelative(2f, 1f, 3f, 4f, 1f, 6f)
            }
            // Hammer head
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(15f, 15f)
                lineTo(20f, 20f)
            }
        }.build()
        return _cirisTools!!
    }

// ─── CIRISDiamond (diamond ❖) ──────────────────────────────────────────────────

private var _cirisDiamond: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISDiamond: ImageVector
    get() {
        if (_cirisDiamond != null) return _cirisDiamond!!
        _cirisDiamond = ImageVector.Builder(
            name = "Filled.CIRISDiamond",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f
        ).apply {
            path(
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round
            ) {
                moveTo(12f, 2f)
                lineTo(22f, 12f)
                lineTo(12f, 22f)
                lineTo(2f, 12f)
                close()
            }
            // Inner diamond
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(12f, 7f)
                lineTo(17f, 12f)
                lineTo(12f, 17f)
                lineTo(7f, 12f)
                close()
            }
        }.build()
        return _cirisDiamond!!
    }

// ============================================================================
// EMOJI REPLACEMENT ICONS - From CIRIS Icon Redesign spec
// 22x22 viewport with 1.75 stroke width, scaled to 24dp
// ============================================================================

// ─── CIRISKeySecure (replaces 🔐, hardware key) ───────────────────────────────

private var _cirisKeySecure: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISKeySecure: ImageVector
    get() {
        if (_cirisKeySecure != null) return _cirisKeySecure!!
        _cirisKeySecure = ImageVector.Builder(
            name = "Filled.CIRISKeySecure",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Shield
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 2.5f)
                lineTo(18f, 5f)
                lineTo(18f, 11f)
                curveTo(18f, 15f, 15f, 18f, 11f, 19.5f)
                curveTo(7f, 18f, 4f, 15f, 4f, 11f)
                lineTo(4f, 5f)
                close()
            }
            // Key circle (approximated with curves)
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(10.75f, 10f)
                curveTo(10.75f, 8.5f, 9.5f, 8.25f, 9f, 8.25f)
                curveTo(7.75f, 8.25f, 7.25f, 9.5f, 7.25f, 10f)
                curveTo(7.25f, 11.5f, 8.5f, 11.75f, 9f, 11.75f)
                curveTo(10.25f, 11.75f, 10.75f, 10.5f, 10.75f, 10f)
                close()
            }
            // Key shaft
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(10.5f, 10.5f)
                lineTo(14.5f, 14.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(12.5f, 12.5f)
                lineTo(13.75f, 11.25f)
            }
        }.build()
        return _cirisKeySecure!!
    }

// ─── CIRISTelemetry (replaces 📊) ─────────────────────────────────────────────

private var _cirisTelemetry: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISTelemetry: ImageVector
    get() {
        if (_cirisTelemetry != null) return _cirisTelemetry!!
        _cirisTelemetry = ImageVector.Builder(
            name = "Filled.CIRISTelemetry",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Axes
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 3.5f)
                lineTo(3.5f, 18.5f)
                lineTo(18.5f, 18.5f)
            }
            // Bars
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7f, 14.5f)
                lineTo(7f, 18.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(10.5f, 10f)
                lineTo(10.5f, 18.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(14f, 12.5f)
                lineTo(14f, 18.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(17.5f, 6.5f)
                lineTo(17.5f, 18.5f)
            }
        }.build()
        return _cirisTelemetry!!
    }

// ─── CIRISRequirements (replaces ■) ───────────────────────────────────────────

private var _cirisRequirements: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISRequirements: ImageVector
    get() {
        if (_cirisRequirements != null) return _cirisRequirements!!
        _cirisRequirements = ImageVector.Builder(
            name = "Filled.CIRISRequirements",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Left bracket
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(4f, 3.5f)
                lineTo(4f, 18.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(4f, 3.5f)
                lineTo(6f, 3.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(4f, 18.5f)
                lineTo(6f, 18.5f)
            }
            // First checkbox
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 6.25f)
                lineTo(10f, 8.25f)
                lineTo(13.5f, 4.75f)
            }
            // First line
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 11f)
                lineTo(18f, 11f)
            }
            // Second checkbox
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 15.75f)
                lineTo(10f, 17.75f)
                lineTo(13.5f, 14.25f)
            }
        }.build()
        return _cirisRequirements!!
    }

// ─── CIRISInstructions (replaces ≡) ───────────────────────────────────────────

private var _cirisInstructions: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISInstructions: ImageVector
    get() {
        if (_cirisInstructions != null) return _cirisInstructions!!
        _cirisInstructions = ImageVector.Builder(
            name = "Filled.CIRISInstructions",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Number 1
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 5.75f)
                lineTo(4.5f, 5f)
                lineTo(4.5f, 8.25f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 8.25f)
                lineTo(5.25f, 8.25f)
            }
            // Number 2
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.25f, 12.5f)
                lineTo(4f, 12f)
                lineTo(5f, 12f)
                lineTo(5f, 13f)
                lineTo(3.25f, 14.5f)
                lineTo(5.25f, 14.5f)
            }
            // Number 3
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 18f)
                lineTo(4.5f, 17.25f)
                lineTo(5f, 17.75f)
                lineTo(4.25f, 18.5f)
                lineTo(5f, 19.25f)
                lineTo(4.5f, 19.75f)
                lineTo(3.5f, 19f)
            }
            // Lines
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 6.25f)
                lineTo(18.5f, 6.25f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 12.25f)
                lineTo(18.5f, 12.25f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 18.25f)
                lineTo(18.5f, 18.25f)
            }
        }.build()
        return _cirisInstructions!!
    }

// ─── CIRISSafety (replaces ◆, shield) ─────────────────────────────────────────

private var _cirisSafety: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISSafety: ImageVector
    get() {
        if (_cirisSafety != null) return _cirisSafety!!
        _cirisSafety = ImageVector.Builder(
            name = "Filled.CIRISSafety",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Shield
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 2.5f)
                lineTo(18.25f, 5f)
                lineTo(18.25f, 11f)
                curveTo(18.25f, 15.25f, 15f, 18.5f, 11f, 19.75f)
                curveTo(7f, 18.5f, 3.75f, 15.25f, 3.75f, 11f)
                lineTo(3.75f, 5f)
                close()
            }
            // Inner diamond
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 7.75f)
                lineTo(14f, 11f)
                lineTo(11f, 14.25f)
                lineTo(8f, 11f)
                close()
            }
        }.build()
        return _cirisSafety!!
    }

// ─── CIRISMemory (memory chip) ────────────────────────────────────────────────

private var _cirisMemory: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISMemory: ImageVector
    get() {
        if (_cirisMemory != null) return _cirisMemory!!
        _cirisMemory = ImageVector.Builder(
            name = "Filled.CIRISMemory",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Chip body
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 6f)
                lineTo(18.5f, 6f)
                lineTo(18.5f, 16f)
                lineTo(3.5f, 16f)
                close()
            }
            // Internal lines
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 9.5f)
                lineTo(18.5f, 9.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 12.5f)
                lineTo(18.5f, 12.5f)
            }
            // Top pins
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(6.5f, 4f)
                lineTo(6.5f, 6f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(10f, 4f)
                lineTo(10f, 6f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(13.5f, 4f)
                lineTo(13.5f, 6f)
            }
            // Bottom pins
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(6.5f, 16f)
                lineTo(6.5f, 18f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(10f, 16f)
                lineTo(10f, 18f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(13.5f, 16f)
                lineTo(13.5f, 18f)
            }
        }.build()
        return _cirisMemory!!
    }

// ─── CIRISSkill (skill card) ──────────────────────────────────────────────────

private var _cirisSkill: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISSkill: ImageVector
    get() {
        if (_cirisSkill != null) return _cirisSkill!!
        _cirisSkill = ImageVector.Builder(
            name = "Filled.CIRISSkill",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Outer box
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.75f, 3.75f)
                lineTo(18.25f, 3.75f)
                lineTo(18.25f, 18.25f)
                lineTo(3.75f, 18.25f)
                close()
            }
            // Inner diamond
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 7f)
                lineTo(14.25f, 11f)
                lineTo(11f, 15f)
                lineTo(7.75f, 11f)
                close()
            }
            // Cross inside diamond
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 7f)
                lineTo(11f, 15f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7.75f, 11f)
                lineTo(14.25f, 11f)
            }
        }.build()
        return _cirisSkill!!
    }

// ─── CIRISModel (LLM model) ───────────────────────────────────────────────────

private var _cirisModel: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISModel: ImageVector
    get() {
        if (_cirisModel != null) return _cirisModel!!
        _cirisModel = ImageVector.Builder(
            name = "Filled.CIRISModel",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Three layers
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(5f, 3.75f)
                lineTo(17f, 3.75f)
                lineTo(17f, 7.25f)
                lineTo(5f, 7.25f)
                close()
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(5f, 9.25f)
                lineTo(17f, 9.25f)
                lineTo(17f, 12.75f)
                lineTo(5f, 12.75f)
                close()
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(5f, 14.75f)
                lineTo(17f, 14.75f)
                lineTo(17f, 18.25f)
                lineTo(5f, 18.25f)
                close()
            }
            // Connectors
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 7.25f)
                lineTo(11f, 9.25f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 12.75f)
                lineTo(11f, 14.75f)
            }
            // Lines in layers
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 5.5f)
                lineTo(14f, 5.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 11f)
                lineTo(14f, 11f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 16.5f)
                lineTo(14f, 16.5f)
            }
        }.build()
        return _cirisModel!!
    }

// ─── CIRISAudit (log/audit) ───────────────────────────────────────────────────

private var _cirisAudit: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISAudit: ImageVector
    get() {
        if (_cirisAudit != null) return _cirisAudit!!
        _cirisAudit = ImageVector.Builder(
            name = "Filled.CIRISAudit",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Document body
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(4.5f, 2.75f)
                lineTo(14.5f, 2.75f)
                lineTo(17.5f, 5.75f)
                lineTo(17.5f, 19.25f)
                lineTo(4.5f, 19.25f)
                close()
            }
            // Corner fold
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(14.5f, 2.75f)
                lineTo(14.5f, 5.75f)
                lineTo(17.5f, 5.75f)
            }
            // Lines
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7.5f, 9.5f)
                lineTo(14.5f, 9.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7.5f, 12.5f)
                lineTo(14.5f, 12.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7.5f, 15.5f)
                lineTo(11.5f, 15.5f)
            }
        }.build()
        return _cirisAudit!!
    }

// ─── CIRISAdapter (adapter plug) ──────────────────────────────────────────────

private var _cirisAdapter: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISAdapter: ImageVector
    get() {
        if (_cirisAdapter != null) return _cirisAdapter!!
        _cirisAdapter = ImageVector.Builder(
            name = "Filled.CIRISAdapter",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Left side
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 11f)
                lineTo(8.5f, 11f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8.5f, 8f)
                lineTo(8.5f, 14f)
                lineTo(11f, 14f)
                lineTo(11f, 8f)
                close()
            }
            // Connector
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 11f)
                lineTo(14f, 11f)
            }
            // Right side
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(14f, 7.5f)
                lineTo(18.5f, 7.5f)
                lineTo(18.5f, 14.5f)
                lineTo(14f, 14.5f)
                close()
            }
            // Pins
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(15.75f, 9.5f)
                lineTo(16.75f, 9.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(15.75f, 12.5f)
                lineTo(16.75f, 12.5f)
            }
        }.build()
        return _cirisAdapter!!
    }

// ─── CIRISThought (chat bubble with plus) ─────────────────────────────────────

private var _cirisThought: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISThought: ImageVector
    get() {
        if (_cirisThought != null) return _cirisThought!!
        _cirisThought = ImageVector.Builder(
            name = "Filled.CIRISThought",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Chat bubble
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 4f)
                lineTo(18.5f, 4f)
                lineTo(18.5f, 15f)
                lineTo(12f, 15f)
                lineTo(8.5f, 18.5f)
                lineTo(8.5f, 15f)
                lineTo(3.5f, 15f)
                close()
            }
            // Plus sign
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 7f)
                lineTo(11f, 12f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8.5f, 9.5f)
                lineTo(13.5f, 9.5f)
            }
        }.build()
        return _cirisThought!!
    }

// ─── CIRISTask (task clipboard) ───────────────────────────────────────────────

private var _cirisTask: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISTask: ImageVector
    get() {
        if (_cirisTask != null) return _cirisTask!!
        _cirisTask = ImageVector.Builder(
            name = "Filled.CIRISTask",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Clipboard body
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 3.5f)
                lineTo(13f, 3.5f)
                lineTo(13f, 6f)
                lineTo(18.5f, 6f)
                lineTo(18.5f, 18.5f)
                lineTo(3.5f, 18.5f)
                close()
            }
            // Checkmark
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7f, 12f)
                lineTo(10f, 15f)
                lineTo(15f, 9.5f)
            }
        }.build()
        return _cirisTask!!
    }

// ─── CIRISHandler (action handler) ────────────────────────────────────────────

private var _cirisHandler: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISHandler: ImageVector
    get() {
        if (_cirisHandler != null) return _cirisHandler!!
        _cirisHandler = ImageVector.Builder(
            name = "Filled.CIRISHandler",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Box
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 3.5f)
                lineTo(18.5f, 3.5f)
                lineTo(18.5f, 18.5f)
                lineTo(3.5f, 18.5f)
                close()
            }
            // Lightning bolt
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(12f, 5.5f)
                lineTo(7f, 12f)
                lineTo(10.5f, 12f)
                lineTo(9.5f, 16.5f)
                lineTo(14.5f, 10f)
                lineTo(11f, 10f)
                close()
            }
        }.build()
        return _cirisHandler!!
    }

// ─── CIRISGraph (memory graph) ────────────────────────────────────────────────

private var _cirisGraph: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISGraph: ImageVector
    get() {
        if (_cirisGraph != null) return _cirisGraph!!
        _cirisGraph = ImageVector.Builder(
            name = "Filled.CIRISGraph",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Three nodes (circles drawn with curves)
            // Top-left node
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7.75f, 5.5f)
                curveTo(7.75f, 6.74f, 6.74f, 7.75f, 5.5f, 7.75f)
                curveTo(4.26f, 7.75f, 3.25f, 6.74f, 3.25f, 5.5f)
                curveTo(3.25f, 4.26f, 4.26f, 3.25f, 5.5f, 3.25f)
                curveTo(6.74f, 3.25f, 7.75f, 4.26f, 7.75f, 5.5f)
                close()
            }
            // Top-right node
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(18.75f, 5.5f)
                curveTo(18.75f, 6.74f, 17.74f, 7.75f, 16.5f, 7.75f)
                curveTo(15.26f, 7.75f, 14.25f, 6.74f, 14.25f, 5.5f)
                curveTo(14.25f, 4.26f, 15.26f, 3.25f, 16.5f, 3.25f)
                curveTo(17.74f, 3.25f, 18.75f, 4.26f, 18.75f, 5.5f)
                close()
            }
            // Bottom node
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(13.25f, 16.5f)
                curveTo(13.25f, 17.74f, 12.24f, 18.75f, 11f, 18.75f)
                curveTo(9.76f, 18.75f, 8.75f, 17.74f, 8.75f, 16.5f)
                curveTo(8.75f, 15.26f, 9.76f, 14.25f, 11f, 14.25f)
                curveTo(12.24f, 14.25f, 13.25f, 15.26f, 13.25f, 16.5f)
                close()
            }
            // Edges
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7.75f, 5.5f)
                lineTo(14.25f, 5.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(6.75f, 7.5f)
                lineTo(9.75f, 14.5f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(15.25f, 7.5f)
                lineTo(12.25f, 14.5f)
            }
        }.build()
        return _cirisGraph!!
    }

// ─── CIRISAgent (wise authority shield) ───────────────────────────────────────

private var _cirisAgent: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISAgent: ImageVector
    get() {
        if (_cirisAgent != null) return _cirisAgent!!
        _cirisAgent = ImageVector.Builder(
            name = "Filled.CIRISAgent",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Shield
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 2.5f)
                lineTo(18f, 5.5f)
                lineTo(18f, 11f)
                curveTo(18f, 15f, 15f, 18f, 11f, 19.5f)
                curveTo(7f, 18f, 4f, 15f, 4f, 11f)
                lineTo(4f, 5.5f)
                close()
            }
            // Cross inside
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7.25f, 10f)
                lineTo(14.75f, 10f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 8f)
                lineTo(11f, 13f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(9f, 13f)
                lineTo(13f, 13f)
            }
        }.build()
        return _cirisAgent!!
    }

// ─── CIRISBus (message bus) ───────────────────────────────────────────────────

private var _cirisBus: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISBus: ImageVector
    get() {
        if (_cirisBus != null) return _cirisBus!!
        _cirisBus = ImageVector.Builder(
            name = "Filled.CIRISBus",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Main bus line
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3f, 11f)
                lineTo(19f, 11f)
            }
            // End caps
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3f, 8f)
                lineTo(3f, 14f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(19f, 8f)
                lineTo(19f, 14f)
            }
            // Top connectors
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7.5f, 11f)
                lineTo(7.5f, 5f)
            }
            // Connector boxes (filled rectangles drawn with paths)
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(6f, 3f)
                lineTo(9f, 3f)
                lineTo(9f, 5f)
                lineTo(6f, 5f)
                close()
            }
            // Bottom connector
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 11f)
                lineTo(11f, 17f)
            }
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(9.5f, 17f)
                lineTo(12.5f, 17f)
                lineTo(12.5f, 19f)
                lineTo(9.5f, 19f)
                close()
            }
            // Right top connector
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(14.5f, 11f)
                lineTo(14.5f, 5f)
            }
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(13f, 3f)
                lineTo(16f, 3f)
                lineTo(16f, 5f)
                lineTo(13f, 5f)
                close()
            }
        }.build()
        return _cirisBus!!
    }

// ─── CIRISStage (pipeline stage) ──────────────────────────────────────────────

private var _cirisStage: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISStage: ImageVector
    get() {
        if (_cirisStage != null) return _cirisStage!!
        _cirisStage = ImageVector.Builder(
            name = "Filled.CIRISStage",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Chevron shape
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(2.5f, 7f)
                lineTo(10f, 7f)
                lineTo(13f, 11f)
                lineTo(10f, 15f)
                lineTo(2.5f, 15f)
                close()
            }
            // Arrow
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(13f, 11f)
                lineTo(19.5f, 11f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(17f, 8.5f)
                lineTo(19.5f, 11f)
                lineTo(17f, 13.5f)
            }
        }.build()
        return _cirisStage!!
    }

// ─── CIRISUpload ──────────────────────────────────────────────────────────────

private var _cirisUpload: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISUpload: ImageVector
    get() {
        if (_cirisUpload != null) return _cirisUpload!!
        _cirisUpload = ImageVector.Builder(
            name = "Filled.CIRISUpload",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Base
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 14f)
                lineTo(3.5f, 18.5f)
                lineTo(18.5f, 18.5f)
                lineTo(18.5f, 14f)
            }
            // Arrow shaft
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 3f)
                lineTo(11f, 14f)
            }
            // Arrow head
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(6f, 8f)
                lineTo(11f, 3f)
                lineTo(16f, 8f)
            }
        }.build()
        return _cirisUpload!!
    }

// ─── CIRISDownload ────────────────────────────────────────────────────────────

private var _cirisDownload: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISDownload: ImageVector
    get() {
        if (_cirisDownload != null) return _cirisDownload!!
        _cirisDownload = ImageVector.Builder(
            name = "Filled.CIRISDownload",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Base
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 14f)
                lineTo(3.5f, 18.5f)
                lineTo(18.5f, 18.5f)
                lineTo(18.5f, 14f)
            }
            // Arrow shaft
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(11f, 3f)
                lineTo(11f, 14f)
            }
            // Arrow head pointing down
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(6f, 9f)
                lineTo(11f, 14f)
                lineTo(16f, 9f)
            }
        }.build()
        return _cirisDownload!!
    }

// ─── CIRISSearch ──────────────────────────────────────────────────────────────

private var _cirisSearch: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISSearch: ImageVector
    get() {
        if (_cirisSearch != null) return _cirisSearch!!
        _cirisSearch = ImageVector.Builder(
            name = "Filled.CIRISSearch",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Circle (magnifying glass lens)
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(14.5f, 9.25f)
                curveTo(14.5f, 12.15f, 12.15f, 14.5f, 9.25f, 14.5f)
                curveTo(6.35f, 14.5f, 4f, 12.15f, 4f, 9.25f)
                curveTo(4f, 6.35f, 6.35f, 4f, 9.25f, 4f)
                curveTo(12.15f, 4f, 14.5f, 6.35f, 14.5f, 9.25f)
                close()
            }
            // Handle
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(13.25f, 13.25f)
                lineTo(18.25f, 18.25f)
            }
        }.build()
        return _cirisSearch!!
    }

// ─── CIRISFilter ──────────────────────────────────────────────────────────────

private var _cirisFilter: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISFilter: ImageVector
    get() {
        if (_cirisFilter != null) return _cirisFilter!!
        _cirisFilter = ImageVector.Builder(
            name = "Filled.CIRISFilter",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Funnel
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 4f)
                lineTo(18.5f, 4f)
                lineTo(13f, 11f)
                lineTo(13f, 18f)
                lineTo(9f, 16.5f)
                lineTo(9f, 11f)
                close()
            }
        }.build()
        return _cirisFilter!!
    }

// ─── CIRISArrowBack ───────────────────────────────────────────────────────────

private var _cirisArrowBack: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISArrowBack: ImageVector
    get() {
        if (_cirisArrowBack != null) return _cirisArrowBack!!
        _cirisArrowBack = ImageVector.Builder(
            name = "Filled.CIRISArrowBack",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(17f, 11f)
                lineTo(5f, 11f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(10f, 5f)
                lineTo(4f, 11f)
                lineTo(10f, 17f)
            }
        }.build()
        return _cirisArrowBack!!
    }

// ─── CIRISArrowForward ────────────────────────────────────────────────────────

private var _cirisArrowForward: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISArrowForward: ImageVector
    get() {
        if (_cirisArrowForward != null) return _cirisArrowForward!!
        _cirisArrowForward = ImageVector.Builder(
            name = "Filled.CIRISArrowForward",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(5f, 11f)
                lineTo(17f, 11f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(12f, 5f)
                lineTo(18f, 11f)
                lineTo(12f, 17f)
            }
        }.build()
        return _cirisArrowForward!!
    }

// ─── CIRISArrowUp ─────────────────────────────────────────────────────────────

private var _cirisArrowUp: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISArrowUp: ImageVector
    get() {
        if (_cirisArrowUp != null) return _cirisArrowUp!!
        _cirisArrowUp = ImageVector.Builder(
            name = "Filled.CIRISArrowUp",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(5f, 13.5f)
                lineTo(11f, 7.5f)
                lineTo(17f, 13.5f)
            }
        }.build()
        return _cirisArrowUp!!
    }

// ─── CIRISArrowDown ───────────────────────────────────────────────────────────

private var _cirisArrowDown: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISArrowDown: ImageVector
    get() {
        if (_cirisArrowDown != null) return _cirisArrowDown!!
        _cirisArrowDown = ImageVector.Builder(
            name = "Filled.CIRISArrowDown",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(5f, 8.5f)
                lineTo(11f, 14.5f)
                lineTo(17f, 8.5f)
            }
        }.build()
        return _cirisArrowDown!!
    }

// ─── CIRISArrowRight ──────────────────────────────────────────────────────────

private var _cirisArrowRight: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISArrowRight: ImageVector
    get() {
        if (_cirisArrowRight != null) return _cirisArrowRight!!
        _cirisArrowRight = ImageVector.Builder(
            name = "Filled.CIRISArrowRight",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8.5f, 5f)
                lineTo(14.5f, 11f)
                lineTo(8.5f, 17f)
            }
        }.build()
        return _cirisArrowRight!!
    }

// ─── CIRISDelete ──────────────────────────────────────────────────────────────

private var _cirisDelete: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISDelete: ImageVector
    get() {
        if (_cirisDelete != null) return _cirisDelete!!
        _cirisDelete = ImageVector.Builder(
            name = "Filled.CIRISDelete",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Lid
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(4f, 6f)
                lineTo(18f, 6f)
            }
            // Handle
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 6f)
                lineTo(8f, 4f)
                lineTo(14f, 4f)
                lineTo(14f, 6f)
            }
            // Body
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(5.5f, 6f)
                lineTo(6.5f, 19f)
                lineTo(15.5f, 19f)
                lineTo(16.5f, 6f)
            }
            // Lines
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(9f, 9f)
                lineTo(9f, 16f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(13f, 9f)
                lineTo(13f, 16f)
            }
        }.build()
        return _cirisDelete!!
    }

// ─── CIRISEdit ────────────────────────────────────────────────────────────────

private var _cirisEdit: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISEdit: ImageVector
    get() {
        if (_cirisEdit != null) return _cirisEdit!!
        _cirisEdit = ImageVector.Builder(
            name = "Filled.CIRISEdit",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Pencil body
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(14f, 3.5f)
                lineTo(18.5f, 8f)
                lineTo(7.5f, 19f)
                lineTo(3f, 19f)
                lineTo(3f, 14.5f)
                close()
            }
            // Collar line
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(12f, 5.5f)
                lineTo(16.5f, 10f)
            }
        }.build()
        return _cirisEdit!!
    }

// ─── CIRISSettings ────────────────────────────────────────────────────────────

private var _cirisSettings: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISSettings: ImageVector
    get() {
        if (_cirisSettings != null) return _cirisSettings!!
        _cirisSettings = ImageVector.Builder(
            name = "Filled.CIRISSettings",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Center circle
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(13.75f, 11f)
                curveTo(13.75f, 12.52f, 12.52f, 13.75f, 11f, 13.75f)
                curveTo(9.48f, 13.75f, 8.25f, 12.52f, 8.25f, 11f)
                curveTo(8.25f, 9.48f, 9.48f, 8.25f, 11f, 8.25f)
                curveTo(12.52f, 8.25f, 13.75f, 9.48f, 13.75f, 11f)
                close()
            }
            // Spokes
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(11f, 3f); lineTo(11f, 5.5f)
            }
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(11f, 16.5f); lineTo(11f, 19f)
            }
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(3f, 11f); lineTo(5.5f, 11f)
            }
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(16.5f, 11f); lineTo(19f, 11f)
            }
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(5.5f, 5.5f); lineTo(7.25f, 7.25f)
            }
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(14.75f, 14.75f); lineTo(16.5f, 16.5f)
            }
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(5.5f, 16.5f); lineTo(7.25f, 14.75f)
            }
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(14.75f, 7.25f); lineTo(16.5f, 5.5f)
            }
        }.build()
        return _cirisSettings!!
    }

// ─── CIRISPerson ──────────────────────────────────────────────────────────────

private var _cirisPerson: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISPerson: ImageVector
    get() {
        if (_cirisPerson != null) return _cirisPerson!!
        _cirisPerson = ImageVector.Builder(
            name = "Filled.CIRISPerson",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Head
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(14.25f, 7.5f)
                curveTo(14.25f, 9.3f, 12.8f, 10.75f, 11f, 10.75f)
                curveTo(9.2f, 10.75f, 7.75f, 9.3f, 7.75f, 7.5f)
                curveTo(7.75f, 5.7f, 9.2f, 4.25f, 11f, 4.25f)
                curveTo(12.8f, 4.25f, 14.25f, 5.7f, 14.25f, 7.5f)
                close()
            }
            // Body
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(4f, 18.5f)
                curveTo(4f, 14.75f, 7f, 12.5f, 11f, 12.5f)
                curveTo(15f, 12.5f, 18f, 14.75f, 18f, 18.5f)
            }
        }.build()
        return _cirisPerson!!
    }

// ─── CIRISBuild ───────────────────────────────────────────────────────────────

private var _cirisBuild: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISBuild: ImageVector
    get() {
        if (_cirisBuild != null) return _cirisBuild!!
        _cirisBuild = ImageVector.Builder(
            name = "Filled.CIRISBuild",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Wrench shape
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(14.5f, 3f)
                lineTo(19f, 7.5f)
                lineTo(17f, 9.5f)
                lineTo(15.5f, 8f)
                lineTo(13.5f, 10f)
                lineTo(15f, 11.5f)
                lineTo(13f, 13.5f)
                lineTo(11.5f, 12f)
                lineTo(9f, 14.5f)
                lineTo(10.5f, 16f)
                lineTo(8f, 18.5f)
                lineTo(3.5f, 14f)
                close()
            }
        }.build()
        return _cirisBuild!!
    }

// ─── CIRISHome ────────────────────────────────────────────────────────────────

private var _cirisHome: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISHome: ImageVector
    get() {
        if (_cirisHome != null) return _cirisHome!!
        _cirisHome = ImageVector.Builder(
            name = "Filled.CIRISHome",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3f, 10f)
                lineTo(11f, 3f)
                lineTo(19f, 10f)
                lineTo(19f, 19f)
                lineTo(13f, 19f)
                lineTo(13f, 13f)
                lineTo(9f, 13f)
                lineTo(9f, 19f)
                lineTo(3f, 19f)
                close()
            }
        }.build()
        return _cirisHome!!
    }

// ─── CIRISLock ────────────────────────────────────────────────────────────────

private var _cirisLock: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISLock: ImageVector
    get() {
        if (_cirisLock != null) return _cirisLock!!
        _cirisLock = ImageVector.Builder(
            name = "Filled.CIRISLock",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Lock body
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(4f, 10f)
                lineTo(18f, 10f)
                lineTo(18f, 19f)
                lineTo(4f, 19f)
                close()
            }
            // Shackle
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7f, 10f)
                lineTo(7f, 7f)
                curveTo(7f, 5f, 8.75f, 3f, 11f, 3f)
                curveTo(13.25f, 3f, 15f, 5f, 15f, 7f)
                lineTo(15f, 10f)
            }
            // Keyhole
            path(
                fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)
            ) {
                moveTo(10.25f, 13.25f)
                lineTo(11.75f, 13.25f)
                lineTo(11.75f, 15.75f)
                lineTo(10.25f, 15.75f)
                close()
            }
        }.build()
        return _cirisLock!!
    }

// ─── CIRISDateRange ───────────────────────────────────────────────────────────

private var _cirisDateRange: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISDateRange: ImageVector
    get() {
        if (_cirisDateRange != null) return _cirisDateRange!!
        _cirisDateRange = ImageVector.Builder(
            name = "Filled.CIRISDateRange",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Calendar body
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 5f)
                lineTo(18.5f, 5f)
                lineTo(18.5f, 18.5f)
                lineTo(3.5f, 18.5f)
                close()
            }
            // Header line
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3.5f, 9f)
                lineTo(18.5f, 9f)
            }
            // Hangers
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(7f, 3f)
                lineTo(7f, 6f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(15f, 3f)
                lineTo(15f, 6f)
            }
            // Date dots
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(6.5f, 11.5f); lineTo(8.5f, 11.5f); lineTo(8.5f, 13.5f); lineTo(6.5f, 13.5f); close()
            }
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(10f, 11.5f); lineTo(12f, 11.5f); lineTo(12f, 13.5f); lineTo(10f, 13.5f); close()
            }
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(13.5f, 11.5f); lineTo(15.5f, 11.5f); lineTo(15.5f, 13.5f); lineTo(13.5f, 13.5f); close()
            }
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(6.5f, 15f); lineTo(8.5f, 15f); lineTo(8.5f, 17f); lineTo(6.5f, 17f); close()
            }
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(10f, 15f); lineTo(12f, 15f); lineTo(12f, 17f); lineTo(10f, 17f); close()
            }
        }.build()
        return _cirisDateRange!!
    }

// ─── CIRISSend ────────────────────────────────────────────────────────────────

private var _cirisSend: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISSend: ImageVector
    get() {
        if (_cirisSend != null) return _cirisSend!!
        _cirisSend = ImageVector.Builder(
            name = "Filled.CIRISSend",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Paper plane
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(3f, 3f)
                lineTo(19f, 11f)
                lineTo(3f, 19f)
                lineTo(5f, 11f)
                close()
            }
            // Center line
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(5f, 11f)
                lineTo(12f, 11f)
            }
        }.build()
        return _cirisSend!!
    }

// ─── CIRISPlay ────────────────────────────────────────────────────────────────

private var _cirisPlay: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISPlay: ImageVector
    get() {
        if (_cirisPlay != null) return _cirisPlay!!
        _cirisPlay = ImageVector.Builder(
            name = "Filled.CIRISPlay",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Play triangle
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(6f, 4f)
                lineTo(18f, 11f)
                lineTo(6f, 18f)
                close()
            }
        }.build()
        return _cirisPlay!!
    }

// ─── CIRISStop ────────────────────────────────────────────────────────────────

private var _cirisStop: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISStop: ImageVector
    get() {
        if (_cirisStop != null) return _cirisStop!!
        _cirisStop = ImageVector.Builder(
            name = "Filled.CIRISStop",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(4.5f, 4.5f)
                lineTo(17.5f, 4.5f)
                lineTo(17.5f, 17.5f)
                lineTo(4.5f, 17.5f)
                close()
            }
        }.build()
        return _cirisStop!!
    }

// ─── CIRISArrowLeft ───────────────────────────────────────────────────────────

private var _cirisArrowLeft: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISArrowLeft: ImageVector
    get() {
        if (_cirisArrowLeft != null) return _cirisArrowLeft!!
        _cirisArrowLeft = ImageVector.Builder(
            name = "Filled.CIRISArrowLeft",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(13.5f, 5f)
                lineTo(7.5f, 11f)
                lineTo(13.5f, 17f)
            }
        }.build()
        return _cirisArrowLeft!!
    }

// ─── CIRISList ────────────────────────────────────────────────────────────────

private var _cirisList: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISList: ImageVector
    get() {
        if (_cirisList != null) return _cirisList!!
        _cirisList = ImageVector.Builder(
            name = "Filled.CIRISList",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Bullets
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(3.5f, 5.5f); lineTo(5.5f, 5.5f); lineTo(5.5f, 7.5f); lineTo(3.5f, 7.5f); close()
            }
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(3.5f, 10f); lineTo(5.5f, 10f); lineTo(5.5f, 12f); lineTo(3.5f, 12f); close()
            }
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(3.5f, 14.5f); lineTo(5.5f, 14.5f); lineTo(5.5f, 16.5f); lineTo(3.5f, 16.5f); close()
            }
            // Lines
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(7.5f, 6.5f); lineTo(18.5f, 6.5f)
            }
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(7.5f, 11f); lineTo(18.5f, 11f)
            }
            path(strokeLineWidth = 1.75f, strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square, strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter) {
                moveTo(7.5f, 15.5f); lineTo(18.5f, 15.5f)
            }
        }.build()
        return _cirisList!!
    }

// ─── CIRISExit ────────────────────────────────────────────────────────────────

private var _cirisExit: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISExit: ImageVector
    get() {
        if (_cirisExit != null) return _cirisExit!!
        _cirisExit = ImageVector.Builder(
            name = "Filled.CIRISExit",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Door frame
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(9f, 3f)
                lineTo(3f, 3f)
                lineTo(3f, 19f)
                lineTo(9f, 19f)
            }
            // Arrow
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(8f, 11f)
                lineTo(19f, 11f)
            }
            path(
                strokeLineWidth = 1.75f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Square,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Miter
            ) {
                moveTo(15f, 7f)
                lineTo(19f, 11f)
                lineTo(15f, 15f)
            }
        }.build()
        return _cirisExit!!
    }

// ─── CIRISMoreVert ────────────────────────────────────────────────────────────

private var _cirisMoreVert: ImageVector? = null
val CIRISMaterialIcons.Filled.CIRISMoreVert: ImageVector
    get() {
        if (_cirisMoreVert != null) return _cirisMoreVert!!
        _cirisMoreVert = ImageVector.Builder(
            name = "Filled.CIRISMoreVert",
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 22f,
            viewportHeight = 22f
        ).apply {
            // Three vertical dots
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(9.5f, 4f); lineTo(12.5f, 4f); lineTo(12.5f, 7f); lineTo(9.5f, 7f); close()
            }
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(9.5f, 9.5f); lineTo(12.5f, 9.5f); lineTo(12.5f, 12.5f); lineTo(9.5f, 12.5f); close()
            }
            path(fill = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black)) {
                moveTo(9.5f, 15f); lineTo(12.5f, 15f); lineTo(12.5f, 18f); lineTo(9.5f, 18f); close()
            }
        }.build()
        return _cirisMoreVert!!
    }
