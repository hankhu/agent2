__path__ = __import__("pkgutil").extend_path(__path__, __name__)

from agent2.agent import Agent, BaseAgent, PlannerAgent, ReActAgent
from agent2.llm import Message, create_llm
from agent2.tools import tool
from agent2.utils.config import Settings

try:
    from importlib.metadata import PackageNotFoundError, version
    try:
        __version__ = version("agent2")
    except PackageNotFoundError:
        __version__ = version("agent2-core")
except PackageNotFoundError:
    __version__ = "0.1.3.25"

__all__ = [
    "__version__",
    "Settings",
    "Agent",
    "BaseAgent",
    "ReActAgent",
    "PlannerAgent",
    "create_llm",
    "Message",
    "tool",
]

