import zipfile
from pathlib import Path

SOURCE_ZIP = Path("registro_fundo_classe.zip")
TARGET_ZIP = Path(__file__).parent / "registro_fundo_classe_sample.zip"
FUND_REGISTRY_IDS = {"1789", "1846", "30692", "35332", "42480", "79049", "85562"}
FILES = ("registro_fundo.csv", "registro_classe.csv", "registro_subclasse.csv")


def keep_rows(lines: list[bytes], column: int, values: set[str]) -> list[bytes]:
    header, *rows = lines
    return [header, *(row for row in rows if row.split(b";")[column].decode("latin1") in values)]


def main() -> None:
    with zipfile.ZipFile(SOURCE_ZIP) as source:
        funds = source.read(FILES[0]).splitlines(keepends=True)
        classes = keep_rows(source.read(FILES[1]).splitlines(keepends=True), 0, FUND_REGISTRY_IDS)
        class_ids = {row.split(b";")[1].decode("latin1") for row in classes[1:]}
        subclasses = keep_rows(source.read(FILES[2]).splitlines(keepends=True), 0, class_ids)
        selected = {FILES[0]: keep_rows(funds, 0, FUND_REGISTRY_IDS), FILES[1]: classes, FILES[2]: subclasses}
    with zipfile.ZipFile(TARGET_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, lines in selected.items():
            target.writestr(name, b"".join(lines))


if __name__ == "__main__":
    main()
