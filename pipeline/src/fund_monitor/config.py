from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PARQUET_DIR = DATA_DIR / "parquet"
SITE_DIR = DATA_DIR / "site"

MANAGER_CNPJ = "68622174000120"
WINDOW_START = date(2024, 9, 1)

CVM_REGISTRY_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
CVM_DAILY_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{yyyymm}.zip"

REGISTRY_RAW_DIR = RAW_DIR / "cvm" / "registry"
DAILY_RAW_DIR = RAW_DIR / "cvm" / "daily"
REGISTRY_PARQUET = PARQUET_DIR / "registry.parquet"
DAILY_PARQUET_DIR = PARQUET_DIR / "daily"
