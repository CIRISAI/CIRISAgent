package ai.ciris.mobile.shared.viewmodels.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.FederationEventStream
import ai.ciris.mobile.shared.models.federation.FederationChannel

/**
 * VM for ``NetworkPathsScreen`` — subscribes to
 * ``FederationChannel.PATH_EVENTS``. Edge 1.0 does not expose a static
 * path table; the screen shows live changes only.
 */
class NetworkPathsViewModel(
    apiClient: CIRISApiClient,
    streamFactory: (CIRISApiClient) -> FederationEventStream = { FederationEventStream(it) },
) : FederationStreamViewModel(apiClient, streamFactory) {

    override val tag: String = "NetworkPathsViewModel"

    override fun channel(): FederationChannel = FederationChannel.PATH_EVENTS

    override fun bufferCapacity(): Int = 100
}
