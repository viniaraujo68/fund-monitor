import polars as pl


def ensure_unique(frame: pl.DataFrame, keys: list[str], label: str) -> None:
    duplicated = frame.filter(pl.struct(keys).is_duplicated())
    if duplicated.height:
        sample = duplicated.select(keys).unique().head(5).to_dicts()
        raise ValueError(f"{label}: {duplicated.height} rows share the key {keys}, e.g. {sample}")
