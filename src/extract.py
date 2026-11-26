import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from src.config import (
    CAMARA_BASE_URL,
    CAMARA_HEADERS,
    DIAS_COLETA_PADRAO,
    QTD_DEPUTADOS_AMOSTRA_DESPESAS,
    RAW_DIR,
)


def buscar_link_proxima_pagina(links: list[dict[str, str]]) -> str | None:
    """Procura na lista 'links' da API se existe um endereço com rel == 'next'."""
    for link in links:
        if link.get("rel") == "next":
            return link.get("href")
    return None


def buscar_todos_os_itens(url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """
    Faz chamadas GET em loop (paginação) até coletar todas as páginas disponíveis.
    Trata erros de rede e timeouts sem quebrar de forma silenciosa.
    """
    todos_os_registros: list[dict[str, Any]] = []
    url_atual: str | None = url
    parametros_atuais = params
    pagina = 1

    while url_atual:
        try:
            resposta = requests.get(
                url_atual,
                headers=CAMARA_HEADERS,
                params=parametros_atuais,
                timeout=20,
            )
            # Se a API retornar erro (ex: 404 ou 500), lança uma exceção para o except capturar
            resposta.raise_for_status()

            conteudo = resposta.json()
            dados_pagina = conteudo.get("dados", [])
            todos_os_registros.extend(dados_pagina)

            # Procura a URL da próxima página
            proxima_url = buscar_link_proxima_pagina(conteudo.get("links", []))

            # Importante: o link 'next' já vem com os filtros na URL,
            # então a partir da página 2 não reenviamos 'parametros_atuais'
            url_atual = proxima_url
            parametros_atuais = None
            pagina += 1

            # Pausa gentil de 0.2s para não sobrecarregar o servidor da Câmara
            if url_atual:
                time.sleep(0.2)

        except requests.exceptions.Timeout:
            print(f"[AVISO] Timeout na página {pagina} ({url_atual}). Interrompendo paginação.")
            break
        except requests.exceptions.RequestException as erro:
            print(f"[ERRO] Falha na requisição ({url_atual}): {erro}")
            break

    return todos_os_registros


def salvar_json_raw(dados: list[dict[str, Any]], nome_arquivo: str) -> Path:
    """Garante que data/raw/ existe e salva os dados brutos em JSON formatado."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    caminho_arquivo = RAW_DIR / nome_arquivo

    with open(caminho_arquivo, mode="w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)

    print(f"  -> Salvo: {caminho_arquivo.name} ({len(dados)} registros)")
    return caminho_arquivo


def extrair_partidos(data_execucao: str) -> list[dict[str, Any]]:
    print("\n1/5 Extraindo partidos...")
    dados = buscar_todos_os_itens(f"{CAMARA_BASE_URL}/partidos", params={"itens": 100})
    salvar_json_raw(dados, f"partidos_{data_execucao}.json")
    return dados


def extrair_deputados(data_execucao: str) -> list[dict[str, Any]]:
    print("\n2/5 Extraindo deputados...")
    dados = buscar_todos_os_itens(f"{CAMARA_BASE_URL}/deputados", params={"itens": 100})
    salvar_json_raw(dados, f"deputados_{data_execucao}.json")
    return dados


def extrair_proposicoes(data_execucao: str, dias: int = DIAS_COLETA_PADRAO) -> list[dict[str, Any]]:
    print(f"\n3/5 Extraindo proposições dos últimos {dias} dias...")
    hoje = date.today()
    inicio = hoje - timedelta(days=dias)

    params = {
        "dataApresentacaoInicio": inicio.isoformat(),
        "dataApresentacaoFim": hoje.isoformat(),
        "itens": 100,
        "ordem": "ASC",
        "ordenarPor": "id",
    }
    dados = buscar_todos_os_itens(f"{CAMARA_BASE_URL}/proposicoes", params=params)
    salvar_json_raw(dados, f"proposicoes_{data_execucao}.json")
    return dados


def extrair_votacoes(data_execucao: str, dias: int = DIAS_COLETA_PADRAO) -> list[dict[str, Any]]:
    print(f"\n4/5 Extraindo votações dos últimos {dias} dias...")
    hoje = date.today()
    inicio = hoje - timedelta(days=dias)

    params = {
        "dataInicio": inicio.isoformat(),
        "dataFim": hoje.isoformat(),
        "itens": 100,
    }
    dados = buscar_todos_os_itens(f"{CAMARA_BASE_URL}/votacoes", params=params)
    salvar_json_raw(dados, f"votacoes_{data_execucao}.json")
    return dados


def extrair_despesas(
    deputados: list[dict[str, Any]],
    data_execucao: str,
    limite_deputados: int | None = QTD_DEPUTADOS_AMOSTRA_DESPESAS,
) -> list[dict[str, Any]]:
    """
    Busca despesas de cada deputado.
    Como a API não retorna o 'deputado_id' dentro de cada item de despesa,
    nós injetamos esse campo manualmente para manter o relacionamento no banco.
    """
    lista_alvo = deputados[:limite_deputados] if limite_deputados else deputados
    print(f"\n5/5 Extraindo despesas de {len(lista_alvo)} deputados (amostra)...")

    ano_atual = date.today().year
    todas_despesas: list[dict[str, Any]] = []

    for dep in lista_alvo:
        dep_id = dep["id"]
        itens_dep = buscar_todos_os_itens(
            f"{CAMARA_BASE_URL}/deputados/{dep_id}/despesas",
            params={"ano": ano_atual, "itens": 100},
        )
        for item in itens_dep:
            item["deputado_id"] = dep_id
        todas_despesas.extend(itens_dep)

    salvar_json_raw(todas_despesas, f"despesas_{data_execucao}.json")
    return todas_despesas


def executar_extracao(dias: int = DIAS_COLETA_PADRAO) -> None:
    data_hoje = date.today().isoformat()
    print(f"=== Iniciando extração RAW ({data_hoje}) ===")

    extrair_partidos(data_hoje)
    deputados = extrair_deputados(data_hoje)
    extrair_proposicoes(data_hoje, dias=dias)
    extrair_votacoes(data_hoje, dias=dias)
    extrair_despesas(deputados, data_hoje)

    print("\n=== Extração RAW finalizada com sucesso! ===")


if __name__ == "__main__":
    executar_extracao()