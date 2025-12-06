class DMAFailure(Exception):
    """Raised when a DMA repeatedly fails or times out."""

    is_dma_failure = True
