class ModelQuotaError(Exception):
    """The model provider's quota or rate limit is exhausted (not the user's fault)."""

QUOTA_MESSAGE = "El servicio ha alcanzado su límite de uso. Inténtalo de nuevo más tarde."

class ExtractionError(Exception):
    """The model did not return a valid profile."""

class ModelUnavailableError(Exception):
    """The model is exhausted (not the user's nor app fault)."""

MODEL_UNAVAILABLE_MESSAGE = "Modelo saturado. Inténtalo de nuevo más tarde."
