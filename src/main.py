import argparse
import time

from src.ai_enrich import classificar_proposicoes, gerar_resumos_executivos
from src.config import DIAS_COLETA_PADRAO
from src.extract import executar_extracao
from src.load import executar_carga


def executar_pipeline(dias: int = DIAS_COLETA_PADRAO, com_resumos: bool = True) -> None:
    inicio = time.perf_counter()
    print("============================================================")
    print(f"  INICIANDO PIPELINE RADAR LEGISLATIVO ({dias} dias)")
    print("============================================================\n")

    # 1. Extract: API da Câmara -> data/raw/
    executar_extracao(dias=dias)

    # 2 & 3. Transform (Pandas) + Load (Batch Upsert no Supabase)
    print()
    executar_carga()

    # 4. IA: Classificação temática (Caminho A) e Resumos executivos (Caminho B)
    print()
    classificar_proposicoes(limite=None)
    if com_resumos:
        gerar_resumos_executivos(limite=None)

    duracao = time.perf_counter() - inicio
    print("\n============================================================")
    print(f"  PIPELINE FINALIZADO COM SUCESSO EM {duracao:.1f}s!")
    print("============================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestrador completo do Radar Legislativo.")
    parser.add_argument(
        "--dias",
        type=int,
        default=DIAS_COLETA_PADRAO,
        help="Quantidade de dias para coletar proposições e votações.",
    )
    parser.add_argument(
        "--sem-resumos",
        action="store_true",
        help="Se informado, pula a geração de resumos executivos (Caminho B).",
    )
    args = parser.parse_args()
    executar_pipeline(dias=args.dias, com_resumos=not args.sem_resumos)