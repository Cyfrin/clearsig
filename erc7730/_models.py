from dataclasses import dataclass, field


@dataclass(frozen=True)
class TranslatedField:
    """A single decoded and formatted field from calldata."""

    label: str
    value: str
    path: str
    format: str


@dataclass(frozen=True)
class TranslatedCalldata:
    """The full human-readable translation of calldata."""

    intent: str
    function_name: str
    function_signature: str
    fields: list[TranslatedField]
    entity: str | None = None


@dataclass(frozen=True)
class FunctionFormat:
    """A function's ABI info paired with its ERC-7730 display format."""

    selector: bytes
    name: str
    signature: str
    input_names: list[str]
    input_types: list[str]
    display: dict
    metadata: dict = field(default_factory=dict)
    entity: str | None = None
