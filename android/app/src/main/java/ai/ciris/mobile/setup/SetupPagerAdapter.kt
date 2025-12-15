package ai.ciris.mobile.setup

import android.util.Log
import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentActivity
import androidx.viewpager2.adapter.FragmentStateAdapter

/**
 * Pager Adapter for Setup Wizard.
 *
 * 3-step wizard:
 * 1. Welcome - Introduction and overview
 * 2. LLM - AI configuration (CIRIS proxy or BYOK)
 * 3. Confirm - Setup summary (Google) or account creation (non-Google)
 *
 * Admin password is auto-generated and never shown to users.
 */
class SetupPagerAdapter(fa: FragmentActivity) : FragmentStateAdapter(fa) {

    companion object {
        private const val TAG = "SetupPagerAdapter"
        const val STEP_COUNT = 3
    }

    override fun getItemCount(): Int = STEP_COUNT

    override fun createFragment(position: Int): Fragment {
        Log.i(TAG, "createFragment: Creating fragment for position $position")

        return when (position) {
            0 -> {
                Log.d(TAG, "Creating SetupWelcomeFragment")
                SetupWelcomeFragment()
            }
            1 -> {
                Log.d(TAG, "Creating SetupLlmFragment")
                SetupLlmFragment()
            }
            2 -> {
                Log.d(TAG, "Creating SetupConfirmFragment")
                SetupConfirmFragment()
            }
            else -> {
                Log.w(TAG, "Unknown position $position, defaulting to WelcomeFragment")
                SetupWelcomeFragment()
            }
        }
    }
}
