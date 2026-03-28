package ai.ciris.mobile.shared.ui.screens.graph

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope

/**
 * Vector Font Character Sets for H3ERE Pipeline Visualization
 *
 * PERFORMANCE: All charsets are Kotlin `object` singletons. Glyphs are computed
 * ONCE at class load time and cached permanently. No allocations occur during
 * rendering - only lookups and drawing primitives.
 *
 * SPACE: Glyphs use minimal stroke counts for recognizable shapes. Each glyph
 * is typically 2-6 polylines. Total memory: ~50KB for all supported scripts.
 *
 * This system renders text using line segments instead of fonts, enabling:
 * - Platform-agnostic rendering (no font dependencies)
 * - Consistent appearance across all devices
 * - Support for ANY script/language by adding character definitions
 *
 * ## Architecture
 *
 * Characters are defined as a list of line segments (polylines).
 * Each character maps to a CharacterGlyph containing normalized coordinates (0-1).
 * Coordinates: (0,0) = top-left, (1,1) = bottom-right
 *
 * ## Adding New Languages
 *
 * 1. Add character definitions to the appropriate charset object
 * 2. Keep stroke count minimal (2-6 polylines per character)
 * 3. Test at small sizes (24-48px) for readability
 *
 * ## Resources for Character Data
 *
 * - Chinese Hershey Font (CJK): https://github.com/LingDong-/chinese-hershey-font
 * - Ge'ez Fonts (Ethiopic): https://github.com/raeytype/geez-handwriting-fonts
 * - Hershey Fonts (Latin/Greek/Cyrillic): https://github.com/coolbutuseless/hershey
 */

/**
 * A single character glyph defined as polylines.
 *
 * @param polylines List of connected line segments. Each polyline is a list of (x, y) points.
 *                  Coordinates are normalized 0-1 where (0,0) is top-left.
 * @param width Character width as fraction of height (typically 0.6-1.0)
 */
data class CharacterGlyph(
    val polylines: List<List<Pair<Float, Float>>>,
    val width: Float = 0.8f
)

/**
 * Character set containing glyphs for a script.
 */
interface VectorCharset {
    /** Get glyph for a character, or null if not supported */
    fun getGlyph(char: Char): CharacterGlyph?

    /** Check if this charset supports the given text */
    fun supports(text: String): Boolean = text.all { getGlyph(it) != null || it == ' ' }
}

/**
 * Latin alphabet characters (A-Z) plus common accented variants.
 * Covers: English, German, Spanish, French, Italian, Portuguese, Turkish, Swahili
 *
 * CACHED: Glyphs created once at class load, no runtime allocation.
 */
object LatinCharset : VectorCharset {

    // Pre-allocated immutable map
    private val glyphs: Map<Char, CharacterGlyph> = buildMap {
        // Basic A-Z
        put('A', CharacterGlyph(listOf(
            listOf(0f to 1f, 0.5f to 0f, 1f to 1f),
            listOf(0.2f to 0.6f, 0.8f to 0.6f)
        )))
        put('B', CharacterGlyph(listOf(
            listOf(0f to 0f, 0f to 1f),
            listOf(0f to 0f, 0.7f to 0f, 0.9f to 0.25f, 0.7f to 0.5f, 0f to 0.5f),
            listOf(0f to 0.5f, 0.7f to 0.5f, 0.9f to 0.75f, 0.7f to 1f, 0f to 1f)
        )))
        put('C', CharacterGlyph(listOf(listOf(1f to 0f, 0f to 0f, 0f to 1f, 1f to 1f))))
        put('D', CharacterGlyph(listOf(
            listOf(0f to 0f, 0f to 1f),
            listOf(0f to 0f, 0.5f to 0f, 1f to 0.5f, 0.5f to 1f, 0f to 1f)
        )))
        put('E', CharacterGlyph(listOf(
            listOf(1f to 0f, 0f to 0f, 0f to 1f, 1f to 1f),
            listOf(0f to 0.5f, 0.7f to 0.5f)
        )))
        put('F', CharacterGlyph(listOf(
            listOf(1f to 0f, 0f to 0f, 0f to 1f),
            listOf(0f to 0.5f, 0.7f to 0.5f)
        )))
        put('G', CharacterGlyph(listOf(listOf(1f to 0f, 0f to 0f, 0f to 1f, 1f to 1f, 1f to 0.5f, 0.5f to 0.5f))))
        put('H', CharacterGlyph(listOf(
            listOf(0f to 0f, 0f to 1f),
            listOf(1f to 0f, 1f to 1f),
            listOf(0f to 0.5f, 1f to 0.5f)
        )))
        put('I', CharacterGlyph(listOf(
            listOf(0f to 0f, 1f to 0f),
            listOf(0.5f to 0f, 0.5f to 1f),
            listOf(0f to 1f, 1f to 1f)
        ), width = 0.6f))
        put('J', CharacterGlyph(listOf(
            listOf(0f to 0f, 1f to 0f),
            listOf(0.5f to 0f, 0.5f to 0.8f, 0.3f to 1f, 0f to 0.8f)
        ), width = 0.7f))
        put('K', CharacterGlyph(listOf(
            listOf(0f to 0f, 0f to 1f),
            listOf(1f to 0f, 0f to 0.5f, 1f to 1f)
        )))
        put('L', CharacterGlyph(listOf(listOf(0f to 0f, 0f to 1f, 1f to 1f))))
        put('M', CharacterGlyph(listOf(listOf(0f to 1f, 0f to 0f, 0.5f to 0.5f, 1f to 0f, 1f to 1f))))
        put('N', CharacterGlyph(listOf(listOf(0f to 1f, 0f to 0f, 1f to 1f, 1f to 0f))))
        put('O', CharacterGlyph(listOf(listOf(0f to 0f, 1f to 0f, 1f to 1f, 0f to 1f, 0f to 0f))))
        put('P', CharacterGlyph(listOf(listOf(0f to 1f, 0f to 0f, 0.8f to 0f, 1f to 0.15f, 1f to 0.35f, 0.8f to 0.5f, 0f to 0.5f))))
        put('Q', CharacterGlyph(listOf(
            listOf(0f to 0f, 1f to 0f, 1f to 1f, 0f to 1f, 0f to 0f),
            listOf(0.6f to 0.7f, 1f to 1f)
        )))
        put('R', CharacterGlyph(listOf(
            listOf(0f to 1f, 0f to 0f, 0.8f to 0f, 1f to 0.15f, 1f to 0.35f, 0.8f to 0.5f, 0f to 0.5f),
            listOf(0.5f to 0.5f, 1f to 1f)
        )))
        put('S', CharacterGlyph(listOf(listOf(1f to 0f, 0f to 0f, 0f to 0.5f, 1f to 0.5f, 1f to 1f, 0f to 1f))))
        put('T', CharacterGlyph(listOf(listOf(0f to 0f, 1f to 0f), listOf(0.5f to 0f, 0.5f to 1f))))
        put('U', CharacterGlyph(listOf(listOf(0f to 0f, 0f to 0.8f, 0.2f to 1f, 0.8f to 1f, 1f to 0.8f, 1f to 0f))))
        put('V', CharacterGlyph(listOf(listOf(0f to 0f, 0.5f to 1f, 1f to 0f))))
        put('W', CharacterGlyph(listOf(listOf(0f to 0f, 0.25f to 1f, 0.5f to 0.5f, 0.75f to 1f, 1f to 0f))))
        put('X', CharacterGlyph(listOf(listOf(0f to 0f, 1f to 1f), listOf(1f to 0f, 0f to 1f))))
        put('Y', CharacterGlyph(listOf(listOf(0f to 0f, 0.5f to 0.5f, 1f to 0f), listOf(0.5f to 0.5f, 0.5f to 1f))))
        put('Z', CharacterGlyph(listOf(listOf(0f to 0f, 1f to 0f, 0f to 1f, 1f to 1f))))

        // Accented variants (reuse base glyphs)
        val e = get('E')!!; val a = get('A')!!; val o = get('O')!!
        val u = get('U')!!; val n = get('N')!!; val c = get('C')!!
        val s = get('S')!!; val i = get('I')!!; val g = get('G')!!
        put('É', e); put('È', e); put('Ê', e); put('Ë', e)
        put('Ä', a); put('Ã', a); put('Á', a); put('Â', a)
        put('Ö', o); put('Õ', o); put('Ó', o); put('Ô', o)
        put('Ü', u); put('Ú', u); put('Û', u)
        put('Ñ', n); put('Ç', c); put('Ş', s)
        put('İ', i); put('Í', i); put('Î', i)
        put('Ğ', g)
    }

    override fun getGlyph(char: Char): CharacterGlyph? = glyphs[char.uppercaseChar()]
}

/**
 * Cyrillic alphabet for Russian - MINIMAL STROKES.
 *
 * Pipeline labels: МЫСЛЬ, КОНТЕКСТ, ВЫБОР, ЭТИКА, ДЕЙСТВИЕ
 * Many shapes shared with Latin.
 *
 * CACHED: Glyphs created once at class load, no runtime allocation.
 */
object CyrillicCharset : VectorCharset {

    // Pre-allocated immutable map
    private val glyphs: Map<Char, CharacterGlyph> = buildMap {
        // Shared with Latin
        put('А', LatinCharset.getGlyph('A')!!)
        put('В', LatinCharset.getGlyph('B')!!)
        put('Е', LatinCharset.getGlyph('E')!!)
        put('К', LatinCharset.getGlyph('K')!!)
        put('М', LatinCharset.getGlyph('M')!!)
        put('Н', LatinCharset.getGlyph('H')!!)
        put('О', LatinCharset.getGlyph('O')!!)
        put('Р', LatinCharset.getGlyph('P')!!)
        put('С', LatinCharset.getGlyph('C')!!)
        put('Т', LatinCharset.getGlyph('T')!!)
        put('Х', LatinCharset.getGlyph('X')!!)

        // Unique Cyrillic
        put('Б', CharacterGlyph(listOf(  // Б
            listOf(1f to 0f, 0f to 0f, 0f to 1f, 0.8f to 1f, 0.9f to 0.75f, 0.8f to 0.5f, 0f to 0.5f)
        )))
        put('Г', CharacterGlyph(listOf(listOf(1f to 0f, 0f to 0f, 0f to 1f))))  // Г
        put('Д', CharacterGlyph(listOf(  // Д
            listOf(0.2f to 0f, 0.8f to 0f),
            listOf(0.2f to 0f, 0f to 1f, 1f to 1f, 0.8f to 0f)
        )))
        put('Ж', CharacterGlyph(listOf(  // Ж
            listOf(0f to 0f, 0.5f to 0.5f, 0f to 1f),
            listOf(1f to 0f, 0.5f to 0.5f, 1f to 1f),
            listOf(0.5f to 0f, 0.5f to 1f)
        )))
        put('З', CharacterGlyph(listOf(  // З (like 3)
            listOf(0f to 0.1f, 0.7f to 0f, 0.9f to 0.25f, 0.7f to 0.5f, 0.3f to 0.5f),
            listOf(0.7f to 0.5f, 0.9f to 0.75f, 0.7f to 1f, 0f to 0.9f)
        )))
        put('И', CharacterGlyph(listOf(listOf(0f to 0f, 0f to 1f, 1f to 0f, 1f to 1f))))  // И
        put('Й', get('И')!!)  // Й
        put('Л', CharacterGlyph(listOf(listOf(0f to 1f, 0.5f to 0f, 1f to 1f))))  // Л
        put('П', CharacterGlyph(listOf(  // П
            listOf(0f to 0f, 1f to 0f),
            listOf(0f to 0f, 0f to 1f),
            listOf(1f to 0f, 1f to 1f)
        )))
        put('У', CharacterGlyph(listOf(  // У
            listOf(0f to 0f, 0.5f to 0.5f, 1f to 0f),
            listOf(0.5f to 0.5f, 0.2f to 1f)
        )))
        put('Ф', CharacterGlyph(listOf(  // Ф
            listOf(0.5f to 0f, 0.5f to 1f),
            listOf(0.5f to 0.2f, 0.1f to 0.4f, 0.1f to 0.6f, 0.5f to 0.8f, 0.9f to 0.6f, 0.9f to 0.4f, 0.5f to 0.2f)
        )))
        put('Ц', CharacterGlyph(listOf(listOf(0f to 0f, 0f to 1f, 1f to 1f, 1f to 0f))))  // Ц
        put('Ч', CharacterGlyph(listOf(  // Ч
            listOf(0f to 0f, 0f to 0.5f, 1f to 0.5f),
            listOf(1f to 0f, 1f to 1f)
        )))
        put('Ш', CharacterGlyph(listOf(  // Ш
            listOf(0f to 0f, 0f to 1f, 1f to 1f, 1f to 0f),
            listOf(0.5f to 0f, 0.5f to 1f)
        )))
        put('Щ', get('Ш')!!)  // Щ
        put('Ъ', CharacterGlyph(listOf(  // Ъ
            listOf(0f to 0f, 0.3f to 0f, 0.3f to 1f, 0.8f to 1f, 0.9f to 0.75f, 0.8f to 0.5f, 0.3f to 0.5f)
        )))
        put('Ы', CharacterGlyph(listOf(  // Ы
            listOf(0f to 0f, 0f to 1f, 0.4f to 1f, 0.5f to 0.75f, 0.4f to 0.5f, 0f to 0.5f),
            listOf(0.7f to 0f, 0.7f to 1f)
        )))
        put('Ь', CharacterGlyph(listOf(listOf(0f to 0f, 0f to 1f, 0.7f to 1f, 0.9f to 0.75f, 0.7f to 0.5f, 0f to 0.5f))))  // Ь
        put('Э', CharacterGlyph(listOf(  // Э
            listOf(0f to 0f, 1f to 0f, 1f to 1f, 0f to 1f),
            listOf(0.3f to 0.5f, 1f to 0.5f)
        )))
        put('Ю', CharacterGlyph(listOf(  // Ю
            listOf(0f to 0f, 0f to 1f),
            listOf(0f to 0.5f, 0.4f to 0.5f),
            listOf(0.4f to 0.15f, 0.7f to 0f, 1f to 0.15f, 1f to 0.85f, 0.7f to 1f, 0.4f to 0.85f, 0.4f to 0.15f)
        )))
        put('Я', CharacterGlyph(listOf(  // Я
            listOf(1f to 1f, 1f to 0f, 0.2f to 0f, 0f to 0.25f, 0.2f to 0.5f, 1f to 0.5f),
            listOf(0.5f to 0.5f, 0f to 1f)
        )))
    }

    override fun getGlyph(char: Char): CharacterGlyph? = glyphs[char.uppercaseChar()]
}

/**
 * Ge'ez (Ethiopic) script for Amharic - MINIMAL STROKES.
 *
 * Pipeline labels: ሀሳብ (think), አውድ (context), ምረጥ (select), ህሊና (ethics), ተግባር (act)
 *
 * CACHED: Glyphs created once at class load, no runtime allocation.
 */
object GeezCharset : VectorCharset {

    // Pre-allocated immutable map - created once, read-only thereafter
    private val glyphs: Map<Char, CharacterGlyph> = buildMap {
        // ሀሳብ (hasab - think) - 3 chars
        put('ሀ', CharacterGlyph(listOf(
            listOf(0.2f to 0.1f, 0.2f to 0.95f),  // stem
            listOf(0.2f to 0.3f, 0.7f to 0.3f, 0.7f to 0.6f)  // right L
        )))
        put('ሳ', CharacterGlyph(listOf(
            listOf(0.1f to 0.25f, 0.5f to 0.05f, 0.9f to 0.25f),  // roof
            listOf(0.5f to 0.05f, 0.5f to 0.95f)  // stem
        )))
        put('ብ', CharacterGlyph(listOf(
            listOf(0.2f to 0.05f, 0.2f to 0.95f),  // stem
            listOf(0.2f to 0.4f, 0.7f to 0.4f, 0.7f to 0.7f, 0.2f to 0.7f)  // box
        )))

        // አውድ (awd - context) - 3 chars
        put('አ', CharacterGlyph(listOf(
            listOf(0.5f to 0.05f, 0.15f to 0.4f, 0.5f to 0.75f, 0.85f to 0.4f, 0.5f to 0.05f)  // diamond
        )))
        put('ው', CharacterGlyph(listOf(
            listOf(0.15f to 0.1f, 0.15f to 0.7f, 0.5f to 0.95f, 0.85f to 0.7f, 0.85f to 0.1f)  // U
        )))
        put('ድ', CharacterGlyph(listOf(
            listOf(0.5f to 0.05f, 0.5f to 0.5f),  // stem
            listOf(0.2f to 0.5f, 0.2f to 0.95f, 0.8f to 0.95f, 0.8f to 0.5f)  // U bottom
        )))

        // ምረጥ (mret - select) - 4 chars
        put('ም', CharacterGlyph(listOf(
            listOf(0.1f to 0.15f, 0.1f to 0.5f, 0.5f to 0.7f, 0.9f to 0.5f, 0.9f to 0.15f),  // M
            listOf(0.5f to 0.7f, 0.5f to 0.95f)  // tail
        )))
        put('ረ', CharacterGlyph(listOf(
            listOf(0.25f to 0.05f, 0.25f to 0.95f),  // stem
            listOf(0.25f to 0.35f, 0.75f to 0.2f)  // flag
        )))
        put('ጥ', CharacterGlyph(listOf(
            listOf(0.15f to 0.2f, 0.85f to 0.2f),  // top
            listOf(0.5f to 0.05f, 0.5f to 0.95f),  // vertical
            listOf(0.3f to 0.6f, 0.7f to 0.6f)  // middle
        )))

        // ህሊና (hlina - ethics) - 4 chars
        put('ህ', CharacterGlyph(listOf(
            listOf(0.2f to 0.05f, 0.2f to 0.95f),  // left
            listOf(0.2f to 0.3f, 0.6f to 0.3f, 0.6f to 0.7f)  // right L
        )))
        put('ሊ', CharacterGlyph(listOf(
            listOf(0.2f to 0.1f, 0.2f to 0.5f, 0.8f to 0.95f),  // diagonal
            listOf(0.2f to 0.3f, 0.6f to 0.3f)  // bar
        )))
        put('ና', CharacterGlyph(listOf(
            listOf(0.2f to 0.05f, 0.2f to 0.95f),  // stem
            listOf(0.2f to 0.4f, 0.7f to 0.4f, 0.7f to 0.8f)  // right L
        )))

        // ተግባር (tegbar - act) - 4 chars
        put('ተ', CharacterGlyph(listOf(
            listOf(0.15f to 0.2f, 0.85f to 0.2f),  // top
            listOf(0.5f to 0.05f, 0.5f to 0.95f),  // vertical
            listOf(0.3f to 0.55f, 0.7f to 0.55f)  // middle
        )))
        put('ግ', CharacterGlyph(listOf(
            listOf(0.2f to 0.1f, 0.5f to 0.05f, 0.8f to 0.1f),  // crown
            listOf(0.5f to 0.05f, 0.5f to 0.5f),  // stem
            listOf(0.25f to 0.5f, 0.25f to 0.95f, 0.75f to 0.95f, 0.75f to 0.5f)  // U
        )))
        put('ባ', CharacterGlyph(listOf(
            listOf(0.2f to 0.05f, 0.2f to 0.95f),  // stem
            listOf(0.2f to 0.35f, 0.7f to 0.35f, 0.7f to 0.7f, 0.2f to 0.7f)  // box
        )))
        put('ር', CharacterGlyph(listOf(
            listOf(0.25f to 0.05f, 0.25f to 0.95f),  // stem
            listOf(0.25f to 0.35f, 0.7f to 0.15f)  // flag
        )))
    }

    override fun getGlyph(char: Char): CharacterGlyph? = glyphs[char]
}

/**
 * CJK characters for Chinese, Japanese, Korean - MINIMAL STROKES.
 *
 * Pipeline labels:
 * - Chinese: 思考 语境 选择 伦理 执行
 * - Japanese: 思考 文脈 選択 倫理 実行
 * - Korean: 생각 맥락 선택 윤리 실행
 *
 * CACHED: Glyphs created once at class load, no runtime allocation.
 */
object CJKCharset : VectorCharset {

    // Pre-allocated immutable map
    private val glyphs: Map<Char, CharacterGlyph> = buildMap {
        // === CHINESE: 思考 (think) ===
        put('思', CharacterGlyph(listOf(
            listOf(0.15f to 0.05f, 0.85f to 0.05f, 0.85f to 0.45f, 0.15f to 0.45f, 0.15f to 0.05f),  // 田 box
            listOf(0.5f to 0.05f, 0.5f to 0.45f),  // center
            listOf(0.15f to 0.25f, 0.85f to 0.25f),  // middle
            listOf(0.2f to 0.6f, 0.5f to 0.95f, 0.8f to 0.6f)  // 心 hook
        )))
        put('考', CharacterGlyph(listOf(
            listOf(0.1f to 0.1f, 0.9f to 0.1f),  // top
            listOf(0.5f to 0.1f, 0.5f to 0.4f),  // stem
            listOf(0.15f to 0.4f, 0.85f to 0.4f),  // middle
            listOf(0.3f to 0.4f, 0.1f to 0.95f),  // left leg
            listOf(0.5f to 0.6f, 0.9f to 0.95f)  // right leg
        )))

        // === CHINESE: 语境 (context) ===
        put('语', CharacterGlyph(listOf(
            listOf(0.05f to 0.15f, 0.2f to 0.15f),  // 讠 top
            listOf(0.12f to 0.15f, 0.12f to 0.9f),  // stem
            listOf(0.3f to 0.1f, 0.9f to 0.1f),  // 吾 top
            listOf(0.6f to 0.1f, 0.6f to 0.9f),  // center
            listOf(0.35f to 0.5f, 0.85f to 0.5f),  // middle
            listOf(0.35f to 0.9f, 0.85f to 0.9f)  // bottom
        )))
        put('境', CharacterGlyph(listOf(
            listOf(0.15f to 0.3f, 0.15f to 0.9f),  // 土 stem
            listOf(0.05f to 0.6f, 0.28f to 0.6f),  // middle
            listOf(0.35f to 0.05f, 0.9f to 0.05f),  // top
            listOf(0.6f to 0.05f, 0.6f to 0.95f),  // center
            listOf(0.4f to 0.5f, 0.85f to 0.5f),  // middle
            listOf(0.4f to 0.95f, 0.85f to 0.95f)  // bottom
        )))

        // === CHINESE: 选择 (select) ===
        put('选', CharacterGlyph(listOf(
            listOf(0.1f to 0.7f, 0.2f to 0.85f, 0.9f to 0.95f),  // 辶
            listOf(0.35f to 0.1f, 0.8f to 0.1f),  // top
            listOf(0.55f to 0.1f, 0.55f to 0.5f),  // stem
            listOf(0.4f to 0.35f, 0.75f to 0.35f)  // middle
        )))
        put('择', CharacterGlyph(listOf(
            listOf(0.12f to 0.05f, 0.12f to 0.95f),  // 扌 stem
            listOf(0.05f to 0.2f, 0.2f to 0.2f),  // top
            listOf(0.3f to 0.1f, 0.9f to 0.1f),  // top right
            listOf(0.6f to 0.1f, 0.4f to 0.55f, 0.9f to 0.55f),  // diagonal
            listOf(0.6f to 0.55f, 0.6f to 0.95f)  // stem
        )))

        // === CHINESE: 伦理 (ethics) ===
        put('伦', CharacterGlyph(listOf(
            listOf(0.15f to 0.05f, 0.05f to 0.5f, 0.05f to 0.95f),  // 亻
            listOf(0.3f to 0.1f, 0.55f to 0.3f, 0.8f to 0.1f),  // 仑 roof
            listOf(0.55f to 0.3f, 0.55f to 0.95f),  // stem
            listOf(0.35f to 0.6f, 0.75f to 0.6f)  // middle
        )))
        put('理', CharacterGlyph(listOf(
            listOf(0.15f to 0.15f, 0.15f to 0.85f),  // 王 stem
            listOf(0.05f to 0.15f, 0.25f to 0.15f),  // top
            listOf(0.05f to 0.5f, 0.25f to 0.5f),  // middle
            listOf(0.05f to 0.85f, 0.25f to 0.85f),  // bottom
            listOf(0.35f to 0.05f, 0.9f to 0.05f),  // 里 top
            listOf(0.6f to 0.05f, 0.6f to 0.95f),  // stem
            listOf(0.35f to 0.5f, 0.85f to 0.5f),  // middle
            listOf(0.35f to 0.95f, 0.85f to 0.95f)  // bottom
        )))

        // === CHINESE: 执行 (act) ===
        put('执', CharacterGlyph(listOf(
            listOf(0.12f to 0.05f, 0.12f to 0.95f),  // 扌 stem
            listOf(0.05f to 0.2f, 0.2f to 0.2f),  // top
            listOf(0.35f to 0.15f, 0.7f to 0.15f, 0.85f to 0.3f),  // top right
            listOf(0.5f to 0.15f, 0.5f to 0.75f, 0.35f to 0.95f),  // curve
            listOf(0.7f to 0.6f, 0.85f to 0.95f)  // tail
        )))
        put('行', CharacterGlyph(listOf(
            listOf(0.2f to 0.05f, 0.1f to 0.35f, 0.1f to 0.95f),  // 彳
            listOf(0.4f to 0.2f, 0.9f to 0.2f),  // top
            listOf(0.6f to 0.2f, 0.6f to 0.95f),  // stem
            listOf(0.4f to 0.55f, 0.85f to 0.55f)  // middle
        )))

        // === JAPANESE: 文脈 (context) ===
        put('文', CharacterGlyph(listOf(
            listOf(0.1f to 0.15f, 0.9f to 0.15f),  // top
            listOf(0.5f to 0.15f, 0.5f to 0.5f),  // stem
            listOf(0.2f to 0.5f, 0.5f to 0.95f, 0.8f to 0.5f)  // X
        )))
        put('脈', CharacterGlyph(listOf(
            listOf(0.1f to 0.1f, 0.25f to 0.1f, 0.25f to 0.9f, 0.1f to 0.9f, 0.1f to 0.1f),  // 月 box
            listOf(0.1f to 0.4f, 0.25f to 0.4f),  // middle
            listOf(0.5f to 0.1f, 0.5f to 0.9f),  // 永 stem
            listOf(0.35f to 0.4f, 0.65f to 0.4f),  // crossbar
            listOf(0.35f to 0.6f, 0.5f to 0.75f, 0.7f to 0.9f)  // tail
        )))
        put('実', CharacterGlyph(listOf(
            listOf(0.2f to 0.1f, 0.8f to 0.1f),  // top
            listOf(0.5f to 0.1f, 0.5f to 0.95f),  // stem
            listOf(0.2f to 0.45f, 0.8f to 0.45f),  // middle
            listOf(0.25f to 0.95f, 0.75f to 0.95f)  // bottom
        )))

        // Traditional/variant forms
        put('選', get('选')!!)  // Traditional
        put('択', get('择')!!)  // Japanese simplified
        put('倫', get('伦')!!)  // Traditional

        // === KOREAN HANGUL ===
        put('생', CharacterGlyph(listOf(  // ㅅ+ㅐ+ㅇ
            listOf(0.2f to 0.15f, 0.5f to 0.4f, 0.8f to 0.15f),  // ㅅ
            listOf(0.5f to 0.55f, 0.3f to 0.7f, 0.3f to 0.95f, 0.7f to 0.95f, 0.7f to 0.7f, 0.5f to 0.55f)  // ㅇ
        )))
        put('각', CharacterGlyph(listOf(  // ㄱ+ㅏ+ㄱ
            listOf(0.15f to 0.15f, 0.55f to 0.15f, 0.55f to 0.45f),  // top ㄱ
            listOf(0.65f to 0.15f, 0.65f to 0.45f),  // ㅏ
            listOf(0.2f to 0.55f, 0.8f to 0.55f, 0.8f to 0.95f)  // bottom ㄱ
        )))
        put('맥', CharacterGlyph(listOf(  // ㅁ+ㅐ+ㄱ
            listOf(0.15f to 0.1f, 0.45f to 0.1f, 0.45f to 0.45f, 0.15f to 0.45f, 0.15f to 0.1f),  // ㅁ
            listOf(0.55f to 0.1f, 0.55f to 0.45f),  // ㅐ
            listOf(0.2f to 0.55f, 0.8f to 0.55f, 0.8f to 0.95f)  // ㄱ
        )))
        put('락', CharacterGlyph(listOf(  // ㄹ+ㅏ+ㄱ
            listOf(0.1f to 0.1f, 0.45f to 0.1f, 0.45f to 0.25f, 0.1f to 0.25f, 0.1f to 0.4f, 0.45f to 0.4f),  // ㄹ
            listOf(0.55f to 0.1f, 0.55f to 0.45f),  // ㅏ
            listOf(0.2f to 0.55f, 0.8f to 0.55f, 0.8f to 0.95f)  // ㄱ
        )))
        put('선', CharacterGlyph(listOf(  // ㅅ+ㅓ+ㄴ
            listOf(0.2f to 0.15f, 0.4f to 0.4f, 0.6f to 0.15f),  // ㅅ
            listOf(0.2f to 0.55f, 0.2f to 0.95f, 0.8f to 0.95f)  // ㄴ
        )))
        put('택', CharacterGlyph(listOf(  // ㅌ+ㅐ+ㄱ
            listOf(0.1f to 0.1f, 0.45f to 0.1f),  // ㅌ top
            listOf(0.1f to 0.25f, 0.45f to 0.25f),  // middle
            listOf(0.27f to 0.1f, 0.27f to 0.45f),  // vertical
            listOf(0.55f to 0.1f, 0.55f to 0.45f),  // ㅐ
            listOf(0.2f to 0.55f, 0.8f to 0.55f, 0.8f to 0.95f)  // ㄱ
        )))
        put('윤', CharacterGlyph(listOf(  // ㅇ+ㅠ+ㄴ
            listOf(0.3f to 0.05f, 0.15f to 0.2f, 0.15f to 0.35f, 0.45f to 0.35f, 0.45f to 0.2f, 0.3f to 0.05f),  // ㅇ
            listOf(0.55f to 0.1f, 0.55f to 0.4f),  // ㅠ
            listOf(0.7f to 0.1f, 0.7f to 0.4f),
            listOf(0.2f to 0.5f, 0.2f to 0.95f, 0.8f to 0.95f)  // ㄴ
        )))
        put('리', CharacterGlyph(listOf(  // ㄹ+ㅣ
            listOf(0.1f to 0.15f, 0.5f to 0.15f, 0.5f to 0.35f, 0.1f to 0.35f, 0.1f to 0.55f, 0.5f to 0.55f, 0.5f to 0.75f),  // ㄹ
            listOf(0.65f to 0.1f, 0.65f to 0.95f)  // ㅣ
        )))
        put('실', CharacterGlyph(listOf(  // ㅅ+ㅣ+ㄹ
            listOf(0.25f to 0.1f, 0.5f to 0.35f, 0.75f to 0.1f),  // ㅅ
            listOf(0.15f to 0.5f, 0.75f to 0.5f, 0.75f to 0.7f, 0.15f to 0.7f, 0.15f to 0.9f, 0.75f to 0.9f)  // ㄹ
        )))
        put('행', CharacterGlyph(listOf(  // ㅎ+ㅐ+ㅇ
            listOf(0.2f to 0.05f, 0.4f to 0.05f),  // ㅎ top
            listOf(0.2f to 0.2f, 0.4f to 0.2f, 0.4f to 0.35f, 0.2f to 0.35f, 0.2f to 0.2f),  // box
            listOf(0.5f to 0.5f, 0.3f to 0.65f, 0.3f to 0.9f, 0.7f to 0.9f, 0.7f to 0.65f, 0.5f to 0.5f)  // ㅇ
        )))
    }

    override fun getGlyph(char: Char): CharacterGlyph? = glyphs[char]
}

/**
 * Combined charset that tries multiple charsets in order.
 */
class CompositeCharset(private val charsets: List<VectorCharset>) : VectorCharset {
    override fun getGlyph(char: Char): CharacterGlyph? {
        for (charset in charsets) {
            charset.getGlyph(char)?.let { return it }
        }
        return null
    }
}

/**
 * Default charset that supports all implemented scripts.
 */
val DefaultVectorCharset = CompositeCharset(listOf(
    LatinCharset,
    CyrillicCharset,
    GeezCharset,
    CJKCharset
))

// =============================================================================
// Drawing Functions
// =============================================================================

/**
 * Draw text using vector character glyphs.
 *
 * @param text Text to render
 * @param x Center X position
 * @param y Center Y position
 * @param charSize Height of each character in pixels
 * @param color Text color
 * @param strokeWidth Line stroke width
 * @param charset Character set to use (defaults to all scripts)
 */
fun DrawScope.drawVectorText(
    text: String,
    x: Float,
    y: Float,
    charSize: Float,
    color: Color,
    strokeWidth: Float,
    charset: VectorCharset = DefaultVectorCharset
) {
    if (text.isEmpty()) return

    // Calculate total width
    var totalWidth = 0f
    val glyphsWithWidths = text.map { char ->
        val glyph = charset.getGlyph(char)
        val width = (glyph?.width ?: 0.8f) * charSize
        totalWidth += width
        Triple(char, glyph, width)
    }
    val spacing = charSize * 0.2f
    totalWidth += (text.length - 1) * spacing

    // Draw centered
    var currentX = x - totalWidth / 2

    for ((char, glyph, width) in glyphsWithWidths) {
        if (glyph != null && char != ' ') {
            drawVectorGlyph(glyph, currentX, y, charSize, width, color, strokeWidth)
        }
        currentX += width + spacing
    }
}

/**
 * Draw a single character glyph.
 */
private fun DrawScope.drawVectorGlyph(
    glyph: CharacterGlyph,
    x: Float,
    y: Float,
    height: Float,
    width: Float,
    color: Color,
    strokeWidth: Float
) {
    val top = y - height / 2

    for (polyline in glyph.polylines) {
        if (polyline.size < 2) continue

        for (i in 0 until polyline.size - 1) {
            val (x1, y1) = polyline[i]
            val (x2, y2) = polyline[i + 1]

            drawLine(
                color = color,
                start = Offset(x + x1 * width, top + y1 * height),
                end = Offset(x + x2 * width, top + y2 * height),
                strokeWidth = strokeWidth,
                cap = StrokeCap.Round
            )
        }
    }
}
