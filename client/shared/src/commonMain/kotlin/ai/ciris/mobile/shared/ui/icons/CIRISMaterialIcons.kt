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
