"""Multi-Agent Security Policy Q&A: exploring Microsoft Agent Framework for grounded RAG."""

from typing import TYPE_CHECKING, Any

from .config import Settings
from .tracing import QueryTrace

if TYPE_CHECKING:
    from .orchestrator import Orchestrator

__version__ = "1.0.0"

__all__ = ["Orchestrator", "QueryTrace", "Settings", "__version__"]


def __getattr__(name: str) -> Any:
    # Lazy: importing the orchestrator pulls in the Azure SDKs and the agent
    # framework, which the CLI deliberately defers until a command needs them.
    if name == "Orchestrator":
        from .orchestrator import Orchestrator

        return Orchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
