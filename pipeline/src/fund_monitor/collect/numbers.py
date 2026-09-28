import polars as pl

RATE = pl.Decimal(18, 8)
INDEX_LEVEL = pl.Decimal(20, 6)
MONEY = pl.Decimal(20, 2)


def parse_brazilian_number(column: str) -> pl.Expr:
    return pl.col(column).str.replace_all(".", "", literal=True).str.replace(",", ".", literal=True)
