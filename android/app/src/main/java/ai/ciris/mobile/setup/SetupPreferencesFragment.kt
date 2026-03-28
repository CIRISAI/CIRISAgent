package ai.ciris.mobile.setup

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.Spinner
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.ViewModelProvider
import ai.ciris.mobile.R

/**
 * Preferences Fragment for Setup Wizard (Step 2).
 *
 * Collects language and location preferences at user-selected granularity.
 * Users choose how much location detail to share:
 * - Country only
 * - Country + Region/State
 * - Country + Region + City
 * - Prefer not to say
 */
class SetupPreferencesFragment : Fragment() {

    companion object {
        private const val TAG = "SetupPrefsFragment"

        // Language codes and display names
        val LANGUAGES = listOf(
            Pair("en", "English"),
            Pair("am", "\u12A0\u121B\u122D\u129B (Amharic)"),
            Pair("ar", "\u0627\u0644\u0639\u0631\u0628\u064A\u0629 (Arabic)"),
            Pair("de", "Deutsch (German)"),
            Pair("es", "Espa\u00F1ol (Spanish)"),
            Pair("fr", "Fran\u00E7ais (French)"),
            Pair("hi", "\u0939\u093F\u0928\u094D\u0926\u0940 (Hindi)"),
            Pair("it", "Italiano (Italian)"),
            Pair("ja", "\u65E5\u672C\u8A9E (Japanese)"),
            Pair("ko", "\uD55C\uAD6D\uC5B4 (Korean)"),
            Pair("pt", "Portugu\u00EAs (Portuguese)"),
            Pair("ru", "\u0420\u0443\u0441\u0441\u043A\u0438\u0439 (Russian)"),
            Pair("sw", "Kiswahili (Swahili)"),
            Pair("tr", "T\u00FCrk\u00E7e (Turkish)"),
            Pair("zh", "\u4E2D\u6587 (Chinese)")
        )
    }

    private lateinit var viewModel: SetupViewModel
    private lateinit var spinnerLanguage: Spinner
    private lateinit var radioGroupLocation: RadioGroup
    private lateinit var sectionCountry: LinearLayout
    private lateinit var sectionRegion: LinearLayout
    private lateinit var sectionCity: LinearLayout
    private lateinit var editCountry: EditText
    private lateinit var editRegion: EditText
    private lateinit var editCity: EditText

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        Log.i(TAG, "onCreateView: Inflating fragment_setup_preferences")
        return inflater.inflate(R.layout.fragment_setup_preferences, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        Log.i(TAG, "onViewCreated: Setting up preferences views")

        viewModel = ViewModelProvider(requireActivity()).get(SetupViewModel::class.java)

        spinnerLanguage = view.findViewById(R.id.spinner_language)
        radioGroupLocation = view.findViewById(R.id.radio_group_location)
        sectionCountry = view.findViewById(R.id.section_country)
        sectionRegion = view.findViewById(R.id.section_region)
        sectionCity = view.findViewById(R.id.section_city)
        editCountry = view.findViewById(R.id.edit_country)
        editRegion = view.findViewById(R.id.edit_region)
        editCity = view.findViewById(R.id.edit_city)

        setupLanguageSpinner()
        setupLocationRadioGroup()
        setupTextWatchers()

        // Auto-detect timezone
        val tz = java.util.TimeZone.getDefault().id
        viewModel.setUserTimezone(tz)
        Log.i(TAG, "Auto-detected timezone: $tz")
    }

    private fun setupLanguageSpinner() {
        val displayNames = LANGUAGES.map { it.second }
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_item, displayNames)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerLanguage.adapter = adapter

        // Default to English (index 0)
        spinnerLanguage.setSelection(0)

        spinnerLanguage.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val langCode = LANGUAGES[position].first
                Log.i(TAG, "Language selected: ${LANGUAGES[position].second} ($langCode)")
                viewModel.setPreferredLanguage(langCode)
            }

            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
    }

    private fun setupLocationRadioGroup() {
        radioGroupLocation.setOnCheckedChangeListener { _, checkedId ->
            when (checkedId) {
                R.id.radio_location_none -> {
                    Log.i(TAG, "Location: prefer not to say")
                    viewModel.setLocationGranularity("none")
                    sectionCountry.visibility = View.GONE
                    sectionRegion.visibility = View.GONE
                    sectionCity.visibility = View.GONE
                }
                R.id.radio_location_country -> {
                    Log.i(TAG, "Location: country only")
                    viewModel.setLocationGranularity("country")
                    sectionCountry.visibility = View.VISIBLE
                    sectionRegion.visibility = View.GONE
                    sectionCity.visibility = View.GONE
                }
                R.id.radio_location_region -> {
                    Log.i(TAG, "Location: country + region")
                    viewModel.setLocationGranularity("region")
                    sectionCountry.visibility = View.VISIBLE
                    sectionRegion.visibility = View.VISIBLE
                    sectionCity.visibility = View.GONE
                }
                R.id.radio_location_city -> {
                    Log.i(TAG, "Location: country + region + city")
                    viewModel.setLocationGranularity("city")
                    sectionCountry.visibility = View.VISIBLE
                    sectionRegion.visibility = View.VISIBLE
                    sectionCity.visibility = View.VISIBLE
                }
            }
        }

        // Default to "prefer not to say"
        view?.findViewById<RadioButton>(R.id.radio_location_none)?.isChecked = true
    }

    private fun setupTextWatchers() {
        editCountry.addTextChangedListener(object : android.text.TextWatcher {
            override fun afterTextChanged(s: android.text.Editable?) {
                viewModel.setLocationCountry(s?.toString()?.takeIf { it.isNotEmpty() })
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })

        editRegion.addTextChangedListener(object : android.text.TextWatcher {
            override fun afterTextChanged(s: android.text.Editable?) {
                viewModel.setLocationRegion(s?.toString()?.takeIf { it.isNotEmpty() })
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })

        editCity.addTextChangedListener(object : android.text.TextWatcher {
            override fun afterTextChanged(s: android.text.Editable?) {
                viewModel.setLocationCity(s?.toString()?.takeIf { it.isNotEmpty() })
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })
    }
}
