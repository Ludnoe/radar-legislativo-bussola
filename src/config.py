from pathlib import Path

# Descobre automaticamente a pasta raiz do projeto (um nível acima de src/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Pasta onde os JSONs brutos serão salvos
RAW_DIR = BASE_DIR / "data" / "raw"

# Configurações da API da Câmara dos Deputados
CAMARA_BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
CAMARA_HEADERS = {"Accept": "application/json"}

# Janela inicial de coleta (começamos com 7 dias; depois expandimos para 30)
DIAS_COLETA_PADRAO = 7
QTD_DEPUTADOS_AMOSTRA_DESPESAS = 5