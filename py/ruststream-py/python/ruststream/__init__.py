"""Python bindings for the RustStream messaging framework."""

from ruststream._broker import Broker, Router
from ruststream._interfaces import IncomingMessage, Subscriber
from ruststream._message import Message
from ruststream._native import __version__
from ruststream.app import RustStream
from ruststream.context import ContextRepo
from ruststream.di import DI, DIError, NoOpDI
from ruststream.failure import FailureAction, FailurePolicy
from ruststream.memory import MemoryBroker, MemoryRouter

__all__: tuple[str, ...] = (
    "DI",
    "Broker",
    "ContextRepo",
    "DIError",
    "FailureAction",
    "FailurePolicy",
    "IncomingMessage",
    "MemoryBroker",
    "MemoryRouter",
    "Message",
    "NoOpDI",
    "Router",
    "RustStream",
    "Subscriber",
    "__version__",
)
