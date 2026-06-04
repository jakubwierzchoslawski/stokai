"""TTLValidator — write-time TTL enforcement for the Redis hot-cache layer.

Raises MissingTTLError when a non-immutable, non-event-driven data type
is written to Redis without an explicit TTL. This prevents stale data from
persisting indefinitely in the hot cache.

Exemptions:
    - invalidation == 'immutable'     (PRICE_BAR_HISTORICAL, EVENT_EMBEDDING)
    - invalidation == 'event_driven'  (COMPANY_SCORE)

Unknown data types are treated conservatively: they require a TTL.
"""

from __future__ import annotations

from ingestion.ttl_policy import DEFAULT_TTL_REGISTRY, DataType, TTLPolicy


class MissingTTLError(ValueError):
    """Raised when a time-based data type is written to Redis without a TTL.

    Attributes:
        data_type: The DataType that triggered the error.
        policy: The TTLPolicy associated with that data type.
    """

    def __init__(self, data_type: DataType, policy: TTLPolicy) -> None:
        self.data_type = data_type
        self.policy = policy
        super().__init__(
            f"Redis write for data_type={data_type!r} requires an explicit TTL "
            f"(policy.invalidation={policy.invalidation!r}) but ttl_seconds=None was supplied."
        )


class TTLValidator:
    """Validates that Redis writes include an appropriate TTL.

    Args:
        registry: Optional TTL registry mapping DataType to TTLPolicy.
            Defaults to DEFAULT_TTL_REGISTRY.
    """

    def __init__(self, registry: dict[DataType, TTLPolicy] | None = None) -> None:
        self._registry = registry if registry is not None else DEFAULT_TTL_REGISTRY

    def validate(self, data_type: DataType, ttl_seconds: int | None) -> None:
        """Raise MissingTTLError if data_type requires a TTL but none was provided.

        Args:
            data_type: The data type being written.
            ttl_seconds: The TTL value that will be applied (or None for no expiry).

        Raises:
            MissingTTLError: When data_type has invalidation='time_based' and
                ttl_seconds is None.
        """
        policy = self._registry.get(data_type)

        if policy is None:
            # Unknown data type — conservative: require a TTL.
            if ttl_seconds is None:
                # Construct a synthetic policy for the error message.
                synthetic_policy = TTLPolicy(
                    data_type=data_type,
                    redis_ttl_seconds=None,
                    pg_ttl_seconds=None,
                    invalidation="time_based",
                )
                raise MissingTTLError(data_type=data_type, policy=synthetic_policy)
            return

        # Immutable and event_driven types are exempt — no TTL required.
        if policy.invalidation in ("immutable", "event_driven"):
            return

        # time_based (or any other invalidation strategy) requires a TTL.
        if ttl_seconds is None:
            raise MissingTTLError(data_type=data_type, policy=policy)
