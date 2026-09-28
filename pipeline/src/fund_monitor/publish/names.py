import re

MANAGER_PREFIXES = ("SUBCLASSE ", "ICATU VANGUARDA ", "ICATU VANG ")
LEGAL_MARKERS = (
    " FIF",
    " FUNDO DE INVESTIMENTO",
    " FIC",
    " FIE",
    " SUBCLASSE",
    " CLASSE",
    " - ",
    " RENDA FIXA",
    " MULTIMERCADO",
)
LOWERCASE_WORDS = {"DE", "DA", "DO", "EM", "E", "NO", "NA"}
KEPT_UPPERCASE = {"IPCA", "IBOV", "FIFE"}
CAPITALIZED_WORDS = {"LOW"}
STRUCTURAL_MARKERS = ("VEÍCULO ESPECIAL", "FIFE")
QUALIFIERS = (
    ("FIFE", (" FIFE",)),
    ("FIC", (" EM COTAS", " FIC", " CIC")),
    ("IU", (" IU ",)),
)


def strip_prefixes(name: str) -> str:
    stripped = name.strip()
    changed = True
    while changed:
        changed = False
        for prefix in MANAGER_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):]
                changed = True
    return stripped


def cut_legal_suffix(name: str) -> str:
    positions = [position for marker in LEGAL_MARKERS if (position := name.find(marker)) > 0]
    return name[: min(positions)] if positions else name


def format_word(word: str, first: bool) -> str:
    letters = re.sub(r"[^A-ZÀ-Ý]", "", word)
    if word in CAPITALIZED_WORDS:
        return word.capitalize()
    if word in KEPT_UPPERCASE or len(letters) <= 3 and word not in LOWERCASE_WORDS or any(c.isdigit() for c in word):
        return word
    if word in LOWERCASE_WORDS and not first:
        return word.lower()
    return "-".join(part.capitalize() for part in word.split("-"))


def display_name(class_name: str, subclass_name: str | None) -> str:
    source = subclass_name or class_name
    short = " ".join(cut_legal_suffix(strip_prefixes(source)).split())
    return " ".join(format_word(word, position == 0) for position, word in enumerate(short.split()))


def is_structural_vehicle(class_name: str) -> bool:
    return any(marker in class_name for marker in STRUCTURAL_MARKERS)


def qualifier(full_name: str, base: str) -> str | None:
    for label, markers in QUALIFIERS:
        if label not in base.split() and any(marker in f" {full_name} " for marker in markers):
            return label
    return None


def unique_display_names(names: list[tuple[str, str | None]]) -> list[str]:
    bases = [display_name(class_name, subclass_name) for class_name, subclass_name in names]
    counts = {base: bases.count(base) for base in bases}
    resolved = []
    for (class_name, subclass_name), base in zip(names, bases):
        extra = qualifier(subclass_name or class_name, base) if counts[base] > 1 else None
        resolved.append(f"{base} {extra}" if extra else base)
    return resolved
