package ai.ciris.mobile.setup

import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentActivity
import androidx.viewpager2.adapter.FragmentStateAdapter

class SetupPagerAdapter(fa: FragmentActivity) : FragmentStateAdapter(fa) {

    override fun getItemCount(): Int = 4

    override fun createFragment(position: Int): Fragment {
        return when (position) {
            0 -> SetupWelcomeFragment()
            1 -> SetupLlmFragment()
            2 -> SetupAdminFragment()
            3 -> SetupAccountFragment()
            else -> SetupWelcomeFragment()
        }
    }
}
