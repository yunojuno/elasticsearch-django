import warnings

warnings.warn(
    "Utils module is pending deprecation, please import disable_search_updates "
    "from decorators module instead.",
    PendingDeprecationWarning,
)

from .decorators import disable_search_updates
