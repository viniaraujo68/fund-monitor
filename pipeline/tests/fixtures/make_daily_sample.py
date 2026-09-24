import zipfile
from pathlib import Path

SOURCE_ZIP = Path("inf_diario_fi_202608.zip")
TARGET_ZIP = Path(__file__).parent / "inf_diario_fi_202608_sample.zip"
MASKED_CNPJS = {"04.820.026/0001-37", "08.279.304/0001-41", "64.026.956/0001-45", "00.017.024/0001-53"}
LAST_DATE = "2026-08-31"
FIRST_DATE = "2026-08-17"


def is_selected(line: str) -> bool:
    fields = line.split(";")
    return fields[1] in MASKED_CNPJS and FIRST_DATE <= fields[3] <= LAST_DATE


def main() -> None:
    with zipfile.ZipFile(SOURCE_ZIP) as source:
        (member,) = source.namelist()
        header, *rows = source.read(member).decode("latin1").splitlines(keepends=True)
    content = header + "".join(row for row in rows if is_selected(row))
    with zipfile.ZipFile(TARGET_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as target:
        target.writestr(member, content.encode("latin1"))


if __name__ == "__main__":
    main()
