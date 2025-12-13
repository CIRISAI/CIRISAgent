package ai.ciris.mobile

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import ai.ciris.mobile.auth.GoogleSignInHelper
import ai.ciris.mobile.billing.BillingApiClient
import ai.ciris.mobile.billing.BillingManager
import ai.ciris.mobile.billing.GoogleTokenRefreshCallback
import ai.ciris.mobile.billing.PurchaseResult
import ai.ciris.mobile.billing.TokenRefreshResult
import com.android.billingclient.api.ProductDetails
import android.content.Intent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Activity for purchasing CIRIS credits via Google Play.
 *
 * Displays available credit packages and handles the purchase flow.
 * After successful purchase, credits are verified and added to the user's account.
 */
class PurchaseActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "CIRISPurchase"
        private const val RC_INTERACTIVE_SIGN_IN = 9002
    }

    private lateinit var billingManager: BillingManager
    private lateinit var billingApiClient: BillingApiClient
    private lateinit var googleSignInHelper: GoogleSignInHelper

    private lateinit var balanceText: TextView
    private lateinit var productsList: RecyclerView
    private lateinit var loadingProgress: ProgressBar
    private lateinit var statusText: TextView

    // Callback for interactive sign-in result
    private var interactiveSignInCallback: ((String?) -> Unit)? = null

    private val productsAdapter = ProductsAdapter { product ->
        onProductSelected(product)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_purchase)

        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = "Buy Credits"

        // Initialize views
        balanceText = findViewById(R.id.balanceText)
        productsList = findViewById(R.id.productsList)
        loadingProgress = findViewById(R.id.loadingProgress)
        statusText = findViewById(R.id.statusText)

        // Setup RecyclerView
        productsList.layoutManager = LinearLayoutManager(this)
        productsList.adapter = productsAdapter

        // Initialize Google Sign-In helper for token refresh
        googleSignInHelper = GoogleSignInHelper(this)

        // Initialize billing with token refresh callback that supports interactive login fallback
        billingApiClient = BillingApiClient(this)
        billingApiClient.setTokenRefreshCallback(object : GoogleTokenRefreshCallback {
            override fun requestFreshToken(onResult: (String?) -> Unit) {
                Log.i(TAG, "[TokenRefresh] Requesting fresh Google ID token via native sign-in...")
                googleSignInHelper.silentSignIn { result ->
                    when (result) {
                        is GoogleSignInHelper.SignInResult.Success -> {
                            val freshToken = result.account.idToken
                            if (freshToken != null) {
                                Log.i(TAG, "[TokenRefresh] Got fresh token (${freshToken.length} chars)")
                                onResult(freshToken)
                            } else {
                                Log.w(TAG, "[TokenRefresh] Silent sign-in succeeded but no ID token")
                                onResult(null)
                            }
                        }
                        is GoogleSignInHelper.SignInResult.Error -> {
                            Log.e(TAG, "[TokenRefresh] Silent sign-in failed: ${result.message}")
                            onResult(null)
                        }
                    }
                }
            }

            override fun requestFreshTokenWithResult(onResult: (TokenRefreshResult) -> Unit) {
                Log.i(TAG, "[TokenRefresh] Requesting fresh Google ID token with detailed result...")
                googleSignInHelper.silentSignIn { result ->
                    when (result) {
                        is GoogleSignInHelper.SignInResult.Success -> {
                            val freshToken = result.account.idToken
                            if (freshToken != null) {
                                Log.i(TAG, "[TokenRefresh] Got fresh token (${freshToken.length} chars)")
                                onResult(TokenRefreshResult.Success(freshToken))
                            } else {
                                Log.w(TAG, "[TokenRefresh] Silent sign-in succeeded but no ID token")
                                onResult(TokenRefreshResult.Failed("No ID token in response"))
                            }
                        }
                        is GoogleSignInHelper.SignInResult.Error -> {
                            // Error code 4 = SIGN_IN_REQUIRED - user needs to interactively sign in
                            if (result.statusCode == 4) {
                                Log.i(TAG, "[TokenRefresh] Silent sign-in requires interactive login (code 4)")
                                onResult(TokenRefreshResult.NeedsInteractiveLogin)
                            } else {
                                Log.e(TAG, "[TokenRefresh] Silent sign-in failed: ${result.message}")
                                onResult(TokenRefreshResult.Failed("Sign-in failed: ${result.message}"))
                            }
                        }
                    }
                }
            }

            override fun launchInteractiveSignIn(onResult: (String?) -> Unit) {
                Log.i(TAG, "[TokenRefresh] Launching interactive Google sign-in...")
                runOnUiThread {
                    interactiveSignInCallback = onResult
                    val signInIntent = googleSignInHelper.getSignInIntent()
                    startActivityForResult(signInIntent, RC_INTERACTIVE_SIGN_IN)
                }
            }
        })
        billingManager = BillingManager(this, billingApiClient)

        // Handle purchase results
        billingManager.onPurchaseResult = { result ->
            handlePurchaseResult(result)
        }

        // Observe products
        lifecycleScope.launch {
            billingManager.products.collectLatest { products ->
                updateProductsList(products)
            }
        }

        // Observe connection state
        lifecycleScope.launch {
            billingManager.isConnected.collectLatest { connected ->
                if (connected) {
                    statusText.text = "Connected to Google Play"
                    loadCurrentBalance()
                } else {
                    statusText.text = "Connecting to Google Play..."
                }
            }
        }

        // Initialize billing client
        billingManager.initialize()

        // Check for pending purchases
        billingManager.processPendingPurchases()

        // Load initial balance
        loadCurrentBalance()
    }

    private fun loadCurrentBalance() {
        lifecycleScope.launch(Dispatchers.IO) {
            val result = billingApiClient.getBalance()
            withContext(Dispatchers.Main) {
                if (result.success) {
                    balanceText.text = "Current Balance: ${result.balance} credits"
                } else {
                    balanceText.text = "Balance: Sign in to view"
                }
            }
        }
    }

    private fun updateProductsList(products: List<ProductDetails>) {
        loadingProgress.visibility = if (products.isEmpty()) View.VISIBLE else View.GONE

        if (products.isEmpty()) {
            statusText.text = "Loading products..."
        } else {
            statusText.text = "${products.size} products available"
        }

        productsAdapter.submitList(products)
    }

    private fun onProductSelected(product: ProductDetails) {
        // Check if user is signed in
        val googleUserId = billingApiClient.getGoogleUserId()
        if (googleUserId == null) {
            AlertDialog.Builder(this)
                .setTitle("Sign In Required")
                .setMessage("Please sign in with Google in Settings to purchase credits.")
                .setPositiveButton("Go to Settings") { _, _ ->
                    finish()
                    // Could launch SettingsActivity here
                }
                .setNegativeButton("Cancel", null)
                .show()
            return
        }

        // Confirm purchase
        val price = product.oneTimePurchaseOfferDetails?.formattedPrice ?: "N/A"
        val credits = when (product.productId) {
            "credits_100" -> 100
            "credits_250" -> 250
            "credits_600" -> 600
            else -> 0
        }

        AlertDialog.Builder(this)
            .setTitle("Confirm Purchase")
            .setMessage("Purchase $credits credits for $price?")
            .setPositiveButton("Buy") { _, _ ->
                billingManager.launchPurchaseFlow(this, product)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun handlePurchaseResult(result: PurchaseResult) {
        when (result) {
            is PurchaseResult.Success -> {
                val message = if (result.alreadyProcessed) {
                    "Purchase already processed. Balance: ${result.newBalance} credits"
                } else {
                    "Success! Added ${result.creditsAdded} credits. New balance: ${result.newBalance}"
                }

                AlertDialog.Builder(this)
                    .setTitle("Purchase Complete")
                    .setMessage(message)
                    .setPositiveButton("OK") { _, _ ->
                        loadCurrentBalance()
                    }
                    .show()

                Log.i(TAG, "Purchase success: $result")
            }

            is PurchaseResult.Error -> {
                AlertDialog.Builder(this)
                    .setTitle("Purchase Failed")
                    .setMessage(result.message)
                    .setPositiveButton("OK", null)
                    .show()

                Log.e(TAG, "Purchase error: ${result.message}")
            }

            PurchaseResult.Cancelled -> {
                Toast.makeText(this, "Purchase cancelled", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == RC_INTERACTIVE_SIGN_IN) {
            val callback = interactiveSignInCallback
            interactiveSignInCallback = null  // Clear to avoid reuse

            val result = googleSignInHelper.handleSignInResult(data)
            when (result) {
                is GoogleSignInHelper.SignInResult.Success -> {
                    val freshToken = result.account.idToken
                    if (freshToken != null) {
                        Log.i(TAG, "[InteractiveSignIn] Got fresh token (${freshToken.length} chars)")
                        callback?.invoke(freshToken)
                    } else {
                        Log.w(TAG, "[InteractiveSignIn] Sign-in succeeded but no ID token")
                        callback?.invoke(null)
                    }
                }
                is GoogleSignInHelper.SignInResult.Error -> {
                    Log.e(TAG, "[InteractiveSignIn] Sign-in failed: ${result.message}")
                    callback?.invoke(null)
                }
            }
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    override fun onDestroy() {
        super.onDestroy()
        interactiveSignInCallback = null  // Clear any pending callback
        billingManager.endConnection()
    }
}

/**
 * Adapter for displaying available credit products.
 */
class ProductsAdapter(
    private val onProductClick: (ProductDetails) -> Unit
) : RecyclerView.Adapter<ProductsAdapter.ProductViewHolder>() {

    private var products: List<ProductDetails> = emptyList()

    fun submitList(newProducts: List<ProductDetails>) {
        products = newProducts
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ProductViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_product, parent, false)
        return ProductViewHolder(view)
    }

    override fun onBindViewHolder(holder: ProductViewHolder, position: Int) {
        holder.bind(products[position])
    }

    override fun getItemCount() = products.size

    inner class ProductViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val nameText: TextView = itemView.findViewById(R.id.productName)
        private val priceText: TextView = itemView.findViewById(R.id.productPrice)
        private val descText: TextView = itemView.findViewById(R.id.productDescription)
        private val buyButton: Button = itemView.findViewById(R.id.buyButton)

        fun bind(product: ProductDetails) {
            val credits = when (product.productId) {
                "credits_100" -> 100
                "credits_250" -> 250
                "credits_600" -> 600
                else -> 0
            }

            nameText.text = "$credits Credits"
            priceText.text = product.oneTimePurchaseOfferDetails?.formattedPrice ?: "N/A"
            descText.text = product.description

            buyButton.setOnClickListener {
                onProductClick(product)
            }
        }
    }
}
