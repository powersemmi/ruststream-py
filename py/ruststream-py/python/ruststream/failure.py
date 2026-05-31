"""Policy describing what a broker does when a handler raises.

Each broker holds an `on_error` policy: a single `FailureAction` applied to every
exception, or a per-type mapping that lets callers route specific failures differently
(`ValueError` -> ACK, validation errors -> REQUEUE, everything else -> NACK).
"""

import enum
from collections.abc import Mapping
from typing import TypeAlias


class FailureAction(enum.StrEnum):
    """How the broker treats a delivery whose handler raised an exception."""

    NACK = "nack"
    """Negative-acknowledge without requeue. Broker decides what to do next (drop, route
    to dead-letter, etc.). Default."""

    REQUEUE = "requeue"
    """Negative-acknowledge with requeue. Broker re-delivers the message (typically with
    its own redelivery / max-attempts policy)."""

    ACK = "ack"
    """Acknowledge as if the handler succeeded. Use to swallow expected-but-noisy errors
    (e.g. duplicate inserts) without burning a redelivery budget."""

    RAISE = "raise"
    """Propagate the exception out of the dispatch loop. The subscriber task fails; other
    subscriptions on the same broker keep running. Use only for unrecoverable conditions
    where the subscription must stop."""


FailurePolicy: TypeAlias = FailureAction | Mapping[type[BaseException], FailureAction] | None


def resolve_failure_action(
    policy: FailurePolicy,
    exc: BaseException,
    *,
    default: FailureAction = FailureAction.NACK,
) -> FailureAction:
    """Pick the `FailureAction` that applies to `exc` under `policy`.

    A `None` policy returns `default`. A `FailureAction` is applied to every exception.
    A mapping is walked by MRO: the first base class with an entry wins, falling back to
    `default` when no entry matches.
    """
    if policy is None:
        return default
    if isinstance(policy, FailureAction):
        return policy
    for base in type(exc).__mro__:
        if base in policy:
            return policy[base]
    return default


__all__: tuple[str, ...] = ("FailureAction", "FailurePolicy", "resolve_failure_action")
