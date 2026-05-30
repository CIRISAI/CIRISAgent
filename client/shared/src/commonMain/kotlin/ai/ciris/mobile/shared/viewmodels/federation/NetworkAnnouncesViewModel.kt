package ai.ciris.mobile.shared.viewmodels.federation

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.FederationEventStream
import ai.ciris.mobile.shared.models.federation.FederationChannel

/**
 * VM for ``NetworkAnnouncesScreen`` — subscribes to
 * ``FederationChannel.ANNOUNCES`` and exposes the standard
 * pause/resume/clear/reconnect surface from [FederationStreamViewModel].
 */
class NetworkAnnouncesViewModel(
    apiClient: CIRISApiClient,
    streamFactory: (CIRISApiClient) -> FederationEventStream = { FederationEventStream(it) },
) : FederationStreamViewModel(apiClient, streamFactory) {

    override val tag: String = "NetworkAnnouncesViewModel"

    override fun channel(): FederationChannel = FederationChannel.ANNOUNCES

    override fun bufferCapacity(): Int = 200
}
