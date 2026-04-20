package ai.ciris.mobile.shared.ui.components

import androidx.compose.foundation.Image
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp

/**
 * CIRIS Signet vector graphic
 * Ported from android/app/src/main/res/drawable/ic_signet.xml
 *
 * The signet is CIRIS's primary brand mark - a geometric pattern
 * representing the interconnected nature of ethical AI.
 */

/**
 * Create the CIRIS signet as an ImageVector
 */
fun createCIRISSignetVector(tintColor: Color = Color(0xFF419CA0)): ImageVector {
    return ImageVector.Builder(
        name = "CIRISSignet",
        defaultWidth = 24.dp,
        defaultHeight = 24.dp,
        viewportWidth = 600f,
        viewportHeight = 600f
    ).apply {
        path(
            fill = SolidColor(tintColor),
            fillAlpha = 1.0f
        ) {
            // CIRIS Signet path data from ic_signet.xml
            moveTo(401.414f, 380.329f)
            curveTo(413.947f, 364.536f, 422.651f, 346.07f, 426.841f, 326.411f)
            lineTo(494.094f, 305.053f)
            curveTo(496.73f, 304.222f, 498.5f, 301.765f, 498.5f, 299.018f)
            curveTo(498.5f, 296.272f, 496.73f, 293.814f, 494.094f, 292.983f)
            lineTo(426.841f, 271.625f)
            curveTo(422.651f, 251.966f, 413.947f, 233.5f, 401.414f, 217.671f)
            lineTo(415.103f, 191.218f)
            curveTo(416.367f, 188.761f, 415.897f, 185.798f, 413.947f, 183.846f)
            curveTo(411.996f, 181.895f, 409.035f, 181.425f, 406.579f, 182.69f)
            lineTo(380.14f, 196.386f)
            curveTo(364.356f, 183.882f, 345.9f, 175.173f, 326.251f, 170.981f)
            lineTo(304.978f, 103.909f)
            curveTo(304.147f, 101.271f, 301.691f, 99.5f, 298.946f, 99.5f)
            curveTo(296.201f, 99.5f, 293.745f, 101.271f, 292.914f, 103.909f)
            lineTo(271.64f, 170.981f)
            curveTo(251.956f, 175.173f, 233.463f, 183.882f, 217.643f, 196.422f)
            lineTo(191.168f, 182.726f)
            curveTo(188.712f, 181.461f, 185.751f, 181.931f, 183.8f, 183.882f)
            curveTo(181.85f, 185.834f, 181.38f, 188.833f, 182.645f, 191.255f)
            lineTo(196.333f, 217.744f)
            curveTo(183.8f, 233.536f, 175.096f, 252.039f, 170.906f, 271.734f)
            lineTo(103.906f, 292.983f)
            curveTo(101.27f, 293.814f, 99.5f, 296.272f, 99.5f, 299.018f)
            curveTo(99.5f, 301.765f, 101.27f, 304.222f, 103.906f, 305.053f)
            lineTo(170.942f, 326.338f)
            curveTo(175.132f, 345.998f, 183.836f, 364.5f, 196.37f, 380.292f)
            lineTo(182.681f, 406.746f)
            curveTo(181.416f, 409.203f, 181.886f, 412.166f, 183.836f, 414.118f)
            curveTo(185.064f, 415.346f, 186.654f, 415.961f, 188.315f, 415.961f)
            curveTo(189.29f, 415.961f, 190.302f, 415.744f, 191.205f, 415.238f)
            lineTo(217.643f, 401.542f)
            curveTo(233.427f, 414.082f, 251.956f, 422.827f, 271.604f, 426.983f)
            lineTo(292.914f, 494.055f)
            curveTo(293.745f, 496.693f, 296.201f, 498.464f, 298.946f, 498.464f)
            curveTo(301.691f, 498.464f, 304.147f, 496.693f, 304.978f, 494.055f)
            lineTo(326.251f, 426.983f)
            curveTo(345.936f, 422.791f, 364.428f, 414.082f, 380.212f, 401.542f)
            lineTo(406.615f, 415.238f)
            curveTo(407.518f, 415.708f, 408.529f, 415.961f, 409.504f, 415.961f)
            curveTo(411.13f, 415.961f, 412.755f, 415.31f, 413.983f, 414.118f)
            curveTo(415.933f, 412.166f, 416.403f, 409.167f, 415.139f, 406.746f)
            lineTo(401.45f, 380.329f)
            horizontalLineTo(401.414f)
            close()

            moveTo(394.985f, 367.897f)
            lineTo(380.465f, 339.89f)
            curveTo(384.294f, 339.348f, 388.122f, 338.553f, 391.915f, 337.505f)
            lineTo(412.719f, 330.892f)
            curveTo(408.999f, 344.154f, 403.003f, 356.694f, 394.985f, 367.897f)
            close()

            moveTo(305.7f, 277.01f)
            curveTo(305.989f, 275.203f, 306.314f, 273.396f, 306.747f, 271.625f)
            curveTo(306.747f, 271.481f, 306.82f, 271.336f, 306.856f, 271.192f)
            curveTo(307.325f, 269.349f, 307.903f, 267.506f, 308.553f, 265.735f)
            curveTo(308.698f, 265.337f, 308.842f, 264.94f, 308.987f, 264.579f)
            curveTo(309.673f, 262.808f, 310.395f, 261.109f, 311.226f, 259.411f)
            curveTo(311.371f, 259.158f, 311.515f, 258.905f, 311.623f, 258.652f)
            curveTo(312.418f, 257.098f, 313.285f, 255.58f, 314.188f, 254.135f)
            curveTo(314.332f, 253.882f, 314.513f, 253.629f, 314.657f, 253.34f)
            curveTo(315.669f, 251.786f, 316.788f, 250.268f, 317.944f, 248.786f)
            curveTo(318.197f, 248.461f, 318.45f, 248.172f, 318.703f, 247.847f)
            curveTo(319.931f, 246.365f, 321.195f, 244.919f, 322.531f, 243.582f)
            curveTo(322.603f, 243.51f, 322.676f, 243.474f, 322.712f, 243.402f)
            curveTo(324.048f, 242.101f, 325.421f, 240.872f, 326.865f, 239.679f)
            curveTo(327.046f, 239.535f, 327.19f, 239.39f, 327.371f, 239.246f)
            curveTo(325.565f, 254.026f, 319.389f, 268.012f, 309.673f, 279.323f)
            curveTo(308.192f, 280.624f, 306.747f, 281.997f, 305.339f, 283.443f)
            curveTo(305.339f, 282.72f, 305.267f, 282.033f, 305.23f, 281.347f)
            curveTo(305.303f, 280.299f, 305.339f, 279.251f, 305.483f, 278.239f)
            curveTo(305.519f, 277.841f, 305.592f, 277.444f, 305.664f, 277.046f)
            lineTo(305.7f, 277.01f)
            close()

            moveTo(314.693f, 292.513f)
            curveTo(316.03f, 291.176f, 317.33f, 289.803f, 318.558f, 288.393f)
            curveTo(329.972f, 278.456f, 343.949f, 272.312f, 358.541f, 270.433f)
            curveTo(348.284f, 283.19f, 333.294f, 291.212f, 316.861f, 292.622f)
            curveTo(316.138f, 292.585f, 315.416f, 292.513f, 314.693f, 292.477f)
            verticalLineTo(292.513f)
            close()

            moveTo(270.918f, 239.752f)
            curveTo(272.399f, 240.98f, 273.88f, 242.245f, 275.216f, 243.618f)
            curveTo(275.216f, 243.618f, 275.252f, 243.655f, 275.288f, 243.691f)
            curveTo(276.625f, 245.028f, 277.889f, 246.473f, 279.081f, 247.955f)
            curveTo(279.334f, 248.28f, 279.586f, 248.569f, 279.839f, 248.895f)
            curveTo(280.995f, 250.376f, 282.079f, 251.858f, 283.09f, 253.448f)
            curveTo(283.27f, 253.737f, 283.451f, 254.026f, 283.596f, 254.279f)
            curveTo(284.498f, 255.761f, 285.365f, 257.243f, 286.16f, 258.796f)
            curveTo(286.268f, 259.049f, 286.413f, 259.266f, 286.521f, 259.519f)
            curveTo(287.352f, 261.218f, 288.074f, 262.916f, 288.76f, 264.687f)
            curveTo(288.905f, 265.084f, 289.049f, 265.446f, 289.194f, 265.843f)
            curveTo(289.844f, 267.65f, 290.422f, 269.457f, 290.891f, 271.3f)
            curveTo(290.891f, 271.445f, 290.928f, 271.553f, 290.964f, 271.698f)
            curveTo(291.397f, 273.468f, 291.758f, 275.275f, 292.011f, 277.118f)
            curveTo(292.083f, 277.48f, 292.119f, 277.877f, 292.192f, 278.239f)
            curveTo(292.336f, 279.287f, 292.372f, 280.335f, 292.444f, 281.383f)
            curveTo(292.408f, 281.997f, 292.372f, 282.648f, 292.336f, 283.262f)
            curveTo(290.819f, 281.744f, 289.23f, 280.262f, 287.605f, 278.853f)
            curveTo(278.142f, 267.65f, 272.11f, 253.918f, 270.304f, 239.354f)
            curveTo(270.485f, 239.499f, 270.665f, 239.643f, 270.81f, 239.788f)
            lineTo(270.918f, 239.752f)
            close()

            moveTo(283.126f, 292.513f)
            curveTo(282.367f, 292.513f, 281.645f, 292.586f, 280.887f, 292.658f)
            curveTo(264.453f, 291.248f, 249.391f, 283.19f, 239.206f, 270.469f)
            curveTo(253.617f, 272.24f, 267.342f, 278.166f, 278.683f, 287.779f)
            curveTo(280.092f, 289.405f, 281.573f, 290.995f, 283.126f, 292.549f)
            verticalLineTo(292.513f)
            close()

            moveTo(283.162f, 305.451f)
            curveTo(281.609f, 307.005f, 280.128f, 308.595f, 278.72f, 310.221f)
            curveTo(267.342f, 319.87f, 253.581f, 325.832f, 239.134f, 327.603f)
            curveTo(249.355f, 314.847f, 264.344f, 306.788f, 280.706f, 305.342f)
            curveTo(281.537f, 305.415f, 282.331f, 305.415f, 283.162f, 305.451f)
            close()

            moveTo(292.408f, 314.81f)
            curveTo(292.408f, 315.533f, 292.481f, 316.256f, 292.553f, 316.979f)
            curveTo(291.18f, 333.458f, 283.09f, 348.527f, 270.376f, 358.718f)
            curveTo(272.146f, 344.335f, 278.069f, 330.639f, 287.605f, 319.328f)
            curveTo(289.266f, 317.882f, 290.855f, 316.4f, 292.408f, 314.81f)
            close()

            moveTo(305.375f, 314.594f)
            curveTo(306.747f, 316.003f, 308.192f, 317.34f, 309.637f, 318.605f)
            curveTo(319.533f, 330.061f, 325.673f, 344.082f, 327.479f, 358.718f)
            curveTo(314.693f, 348.455f, 306.639f, 333.421f, 305.23f, 316.979f)
            curveTo(305.303f, 316.184f, 305.339f, 315.389f, 305.375f, 314.594f)
            close()

            moveTo(314.621f, 305.451f)
            curveTo(315.38f, 305.451f, 316.138f, 305.415f, 316.897f, 305.342f)
            curveTo(333.258f, 306.788f, 348.392f, 314.847f, 358.577f, 327.531f)
            curveTo(343.913f, 325.688f, 329.972f, 319.544f, 318.558f, 309.607f)
            curveTo(317.294f, 308.161f, 315.958f, 306.788f, 314.621f, 305.415f)
            verticalLineTo(305.451f)
            close()

            moveTo(420.34f, 315.208f)
            curveTo(419.798f, 315.316f, 419.256f, 315.461f, 418.751f, 315.714f)
            lineTo(388.339f, 325.399f)
            curveTo(383.643f, 326.7f, 378.876f, 327.531f, 374.144f, 327.892f)
            curveTo(366.451f, 314.991f, 355.11f, 305.017f, 341.891f, 298.982f)
            curveTo(355.074f, 292.983f, 366.379f, 283.045f, 374.144f, 270.108f)
            curveTo(378.84f, 270.505f, 383.499f, 271.3f, 388.122f, 272.565f)
            lineTo(419.076f, 282.395f)
            curveTo(419.292f, 282.467f, 419.509f, 282.539f, 419.726f, 282.611f)
            lineTo(471.303f, 299.018f)
            lineTo(420.34f, 315.208f)
            close()

            moveTo(412.755f, 267.144f)
            lineTo(391.734f, 260.459f)
            curveTo(388.014f, 259.411f, 384.257f, 258.652f, 380.501f, 258.11f)
            lineTo(394.985f, 230.103f)
            curveTo(403.039f, 241.342f, 409.035f, 253.882f, 412.755f, 267.144f)
            close()

            moveTo(388.303f, 215.539f)
            lineTo(366.74f, 257.243f)
            curveTo(355.363f, 257.423f, 344.166f, 259.736f, 333.764f, 264.145f)
            curveTo(338.098f, 253.773f, 340.482f, 242.57f, 340.626f, 231.115f)
            lineTo(394.768f, 203.072f)
            lineTo(388.339f, 215.503f)
            lineTo(388.303f, 215.539f)
            close()

            moveTo(267.162f, 185.075f)
            lineTo(260.48f, 206.107f)
            curveTo(259.685f, 208.637f, 260.516f, 211.383f, 262.611f, 213.01f)
            curveTo(264.706f, 214.636f, 267.559f, 214.816f, 269.798f, 213.407f)
            lineTo(298.693f, 195.699f)
            lineTo(328.129f, 213.443f)
            curveTo(329.141f, 214.058f, 330.26f, 214.347f, 331.38f, 214.347f)
            curveTo(332.753f, 214.347f, 334.161f, 213.877f, 335.281f, 212.973f)
            curveTo(337.34f, 211.347f, 338.17f, 208.601f, 337.376f, 206.107f)
            lineTo(330.694f, 185.075f)
            curveTo(343.949f, 188.797f, 356.482f, 194.76f, 367.679f, 202.819f)
            lineTo(331.308f, 221.647f)
            lineTo(329.249f, 222.731f)
            curveTo(315.596f, 230.464f, 305.122f, 242.173f, 298.837f, 255.942f)
            curveTo(292.553f, 242.173f, 282.042f, 230.392f, 268.245f, 222.622f)
            lineTo(266.403f, 221.683f)
            lineTo(229.996f, 202.819f)
            curveTo(241.229f, 194.76f, 253.798f, 188.761f, 267.089f, 185.039f)
            lineTo(267.162f, 185.075f)
            close()

            moveTo(257.193f, 231.151f)
            curveTo(257.337f, 242.57f, 259.721f, 253.737f, 264.019f, 264.073f)
            curveTo(253.617f, 259.7f, 242.421f, 257.423f, 231.079f, 257.279f)
            lineTo(209.517f, 215.611f)
            verticalLineTo(215.539f)
            lineTo(203.051f, 203.072f)
            lineTo(257.229f, 231.151f)
            horizontalLineTo(257.193f)
            close()

            moveTo(202.799f, 230.139f)
            lineTo(217.318f, 258.182f)
            curveTo(213.562f, 258.724f, 209.806f, 259.483f, 206.049f, 260.531f)
            lineTo(185.028f, 267.217f)
            curveTo(188.749f, 253.954f, 194.744f, 241.378f, 202.799f, 230.139f)
            close()

            moveTo(209.661f, 272.637f)
            curveTo(214.284f, 271.336f, 218.98f, 270.541f, 223.675f, 270.144f)
            curveTo(231.404f, 283.045f, 242.709f, 292.983f, 255.929f, 298.982f)
            curveTo(242.746f, 305.017f, 231.404f, 314.955f, 223.639f, 327.856f)
            curveTo(219.016f, 327.459f, 214.429f, 326.664f, 209.878f, 325.399f)
            lineTo(126.697f, 298.946f)
            lineTo(209.661f, 272.565f)
            verticalLineTo(272.637f)
            close()

            moveTo(185.028f, 330.82f)
            lineTo(206.266f, 337.577f)
            curveTo(209.914f, 338.589f, 213.598f, 339.348f, 217.282f, 339.89f)
            lineTo(202.799f, 367.897f)
            curveTo(194.744f, 356.658f, 188.749f, 344.118f, 185.065f, 330.856f)
            lineTo(185.028f, 330.82f)
            close()

            moveTo(209.444f, 382.497f)
            curveTo(209.444f, 382.497f, 209.481f, 382.425f, 209.481f, 382.389f)
            lineTo(231.007f, 340.794f)
            curveTo(242.348f, 340.649f, 253.545f, 338.336f, 263.947f, 334f)
            curveTo(259.613f, 344.371f, 257.337f, 355.538f, 257.157f, 366.849f)
            lineTo(203.979f, 394.928f)
            lineTo(209.408f, 382.533f)
            lineTo(209.444f, 382.497f)
            close()

            moveTo(230.032f, 395.145f)
            lineTo(258.096f, 380.618f)
            curveTo(258.638f, 384.376f, 259.396f, 388.171f, 260.444f, 391.893f)
            lineTo(267.126f, 412.925f)
            curveTo(253.834f, 409.203f, 241.301f, 403.204f, 230.032f, 395.145f)
            close()

            moveTo(298.91f, 471.288f)
            lineTo(272.543f, 388.279f)
            curveTo(271.243f, 383.653f, 270.448f, 378.955f, 270.051f, 374.257f)
            curveTo(282.945f, 366.56f, 292.878f, 355.213f, 298.874f, 341.986f)
            curveTo(304.869f, 355.177f, 314.802f, 366.488f, 327.732f, 374.257f)
            curveTo(327.335f, 378.883f, 326.54f, 383.509f, 325.276f, 388.062f)
            lineTo(298.837f, 471.288f)
            horizontalLineTo(298.91f)
            close()

            moveTo(330.694f, 412.925f)
            lineTo(337.448f, 391.676f)
            curveTo(338.459f, 388.026f, 339.218f, 384.34f, 339.76f, 380.618f)
            lineTo(367.787f, 395.145f)
            curveTo(356.555f, 403.204f, 343.985f, 409.203f, 330.73f, 412.925f)
            horizontalLineTo(330.694f)
            close()

            moveTo(382.343f, 388.46f)
            curveTo(382.343f, 388.46f, 382.343f, 388.46f, 382.307f, 388.46f)
            lineTo(340.663f, 366.885f)
            curveTo(340.518f, 355.502f, 338.207f, 344.299f, 333.836f, 333.891f)
            curveTo(344.202f, 338.264f, 355.399f, 340.613f, 366.74f, 340.758f)
            lineTo(388.339f, 382.461f)
            lineTo(394.768f, 394.892f)
            lineTo(382.379f, 388.46f)
            horizontalLineTo(382.343f)
            close()
        }
    }.build()
}

/**
 * CIRIS Signet composable
 *
 * @param modifier Modifier for sizing and positioning
 * @param tintColor Color to tint the signet (default: CIRIS teal #419CA0)
 */
@Composable
fun CIRISSignet(
    modifier: Modifier = Modifier,
    tintColor: Color = Color(0xFF419CA0)
) {
    val signetVector = remember(tintColor) {
        createCIRISSignetVector(tintColor)
    }

    Image(
        imageVector = signetVector,
        contentDescription = "CIRIS Signet",
        modifier = modifier
    )
}
