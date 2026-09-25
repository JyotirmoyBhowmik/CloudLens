"""Four-State Null Discipline for CloudLens Measures.

Enforces Prompt 05 Item 36:
"Implement the four-state null discipline as a first-class value type used everywhere a measure
can be absent: NO_COST, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED. Ban bare nulls for measures."

Acceptance:
"A measure can be set to NOT_SUPPORTED and renders distinctly from zero in a unit test."
"Do not use a nullable decimal to mean 'no data'."
"""

from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

from domain.models.enums import MeasureNullState
from domain.models.exceptions import MeasureAbsentException, MeasureNullForbiddenException

T = TypeVar("T", Decimal, float, int)


class Measure(Generic[T]):
    """First-class value type for numerical measures enforcing the four-state null discipline.

    Bare Python `None` is banned. A Measure is either:
    1. A present numeric value, or
    2. An explicit MeasureNullState (NO_COST, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED).
    """

    __slots__ = ("_value", "_null_state")

    def __init__(self, value: T | None = None, null_state: MeasureNullState | None = None) -> None:
        if value is None and null_state is None:
            raise MeasureNullForbiddenException()

        if value is not None and null_state is not None:
            raise ValueError(
                "A Measure cannot simultaneously possess a numeric value and an absent null_state."
            )

        self._value: T | None = value
        self._null_state: MeasureNullState | None = null_state

    @property
    def is_present(self) -> bool:
        """Returns True if the measure contains a valid numeric value."""
        return self._value is not None

    @property
    def is_null(self) -> bool:
        """Returns True if the measure is absent under one of the 4 null states."""
        return self._null_state is not None

    @property
    def null_state(self) -> MeasureNullState | None:
        """Returns the specific MeasureNullState, or None if the measure is present."""
        return self._null_state

    @property
    def value(self) -> T:
        """Retrieves the numeric value. Raises MeasureAbsentException if measure is absent."""
        if self._value is None:
            assert self._null_state is not None
            raise MeasureAbsentException(self._null_state.value)
        return self._value

    def value_or(self, default: T) -> T:
        """Returns the numeric value if present, else returns the specified default."""
        return self._value if self._value is not None else default

    def render(self) -> str:
        """Renders measure for display.

        Renders distinctly:
        - Present: e.g. "125.50"
        - NOT_SUPPORTED: "NOT_SUPPORTED" (distinct from zero)
        - NO_DATA: "NO_DATA"
        - NO_COST: "NO_COST"
        - NOT_APPLICABLE: "NOT_APPLICABLE"
        """
        if self._null_state is not None:
            return self._null_state.value
        return str(self._value)

    def to_dict(self) -> dict[str, Any]:
        """Serializes measure to structured dictionary."""
        return {
            "value": str(self._value) if isinstance(self._value, Decimal) else self._value,
            "null_state": self._null_state.value if self._null_state else None,
            "is_present": self.is_present,
            "render": self.render(),
        }

    # Factory constructors
    @classmethod
    def of(cls, val: T | str | int | float) -> "Measure[T]":
        """Creates a present measure."""
        if val is None:
            raise MeasureNullForbiddenException()
        if isinstance(val, int | float | str) and not isinstance(val, Decimal):
            # Default numeric typing
            return cls(value=Decimal(str(val)))  # type: ignore[arg-type]
        return cls(value=val)  # type: ignore[arg-type]

    @classmethod
    def no_cost(cls) -> "Measure[T]":
        """Explicitly represents zero cost / verified free consumption."""
        return cls(null_state=MeasureNullState.NO_COST)

    @classmethod
    def no_data(cls) -> "Measure[T]":
        """Explicitly represents missing or uncollected telemetry/billing."""
        return cls(null_state=MeasureNullState.NO_DATA)

    @classmethod
    def not_applicable(cls) -> "Measure[T]":
        """Explicitly represents an irrelevant or inapplicable metric."""
        return cls(null_state=MeasureNullState.NOT_APPLICABLE)

    @classmethod
    def not_supported(cls) -> "Measure[T]":
        """Explicitly represents a metric unsupported by the underlying cloud provider."""
        return cls(null_state=MeasureNullState.NOT_SUPPORTED)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Measure):
            return False
        return self._value == other._value and self._null_state == other._null_state

    def __str__(self) -> str:
        return self.render()

    def __repr__(self) -> str:
        if self._null_state:
            return f"Measure(null_state={self._null_state.value})"
        return f"Measure(value={self._value})"

    # Pydantic v2 Core Schema integration
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        def validate(v: Any) -> "Measure[Any]":
            if v is None:
                raise MeasureNullForbiddenException()
            if isinstance(v, Measure):
                return v
            if isinstance(v, MeasureNullState):
                return cls(null_state=v)
            if isinstance(v, str):
                v_upper = v.strip().upper()
                if v_upper in MeasureNullState.__members__:
                    return cls(null_state=MeasureNullState[v_upper])
                try:
                    val_dec: Any = Decimal(v)
                    return cls(value=val_dec)
                except Exception:
                    raise ValueError(f"Invalid measure representation: {v}") from None
            if isinstance(v, int | float | Decimal):
                val_num: Any = Decimal(str(v))
                return cls(value=val_num)
            if isinstance(v, dict):
                null_state_str = v.get("null_state")
                val = v.get("value")
                if null_state_str:
                    return cls(null_state=MeasureNullState(null_state_str))
                if val is not None:
                    val_d: Any = Decimal(str(val))
                    return cls(value=val_d)
                raise MeasureNullForbiddenException()
            raise ValueError(f"Cannot parse value of type {type(v)} into Measure")

        return core_schema.chain_schema(
            [
                core_schema.any_schema(),
                core_schema.no_info_plain_validator_function(validate),
            ],
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: instance.to_dict(),
                info_arg=False,
                return_schema=core_schema.dict_schema(),
            ),
        )


# Specialized Measure Aliases
class FinancialMeasure(Measure[Decimal]):
    """Monetary measure (e.g. Billed Cost, List Cost, Effective Cost)."""

    pass


class QuantityMeasure(Measure[Decimal]):
    """Resource usage and consumption quantity measure (e.g. Hours, Bytes, Requests)."""

    pass
