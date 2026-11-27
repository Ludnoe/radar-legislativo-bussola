import argparse
import json
import os
from typing import Any

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from psycopg2.extras import execute_values

from src.config import BASE_DIR
from src.load import obter_engine

# Caminho A (Embeddings): US$ 0,02 por 1 milhão de tokens
MODELO_EMBEDDING = "text-embedding-3-small"
PRECO_EMBEDDING_POR_1M_USD = 0.02
TAMANHO_LOTE = 100

# Caminho B (Resumo Executivo): gpt-4o-mini (US$ 0,15 / 1M input e US$ 0,60 / 1M output)
MODELO_RESUMO = "gpt-4o-mini"
PRECO_RESUMO_INPUT_1M_USD = 0.15
PRECO_RESUMO_OUTPUT_1M_USD = 0.60
TIPOS_PARA_RESUMO = ("PL", "PLP", "PEC", "MPV")

# Cache local para não pagar pelos embeddings dos 10 temas toda vez que rodar
CAMINHO_CACHE_TEMAS = BASE_DIR / "data" / "temas_embeddings_cache.json"

TEMAS_ESTRATEGICOS: dict[str, str] = {
    "Tributário e Fiscal": (
        "Impostos, tributos, alíquotas, isenção fiscal, ICMS, ISS, IPI, IRPF, "
        "reforma tributária, orçamento público, dívida pública e renúncia de receita."
    ),
    "Tecnologia, IA e Dados": (
        "Inteligência artificial, tecnologia, internet, redes sociais, proteção de dados, "
        "LGPD, cibersegurança, telecomunicações, aplicativos e inovação digital."
    ),
    "Trabalho e Previdência": (
        "Direito trabalhista, CLT, salário mínimo, jornada de trabalho, férias, sindicatos, "
        "INSS, aposentadoria, pensão, FGTS e segurança no trabalho."
    ),
    "Saúde": (
        "Saúde pública, SUS, hospitais, medicamentos, planos de saúde, vacinação, "
        "doenças, médicos, enfermagem e vigilância sanitária."
    ),
    "Educação": (
        "Escolas, universidades, professores, ensino básico e superior, bolsas de estudo, "
        "ENEM, alfabetização, creches e financiamento da educação."
    ),
    "Meio Ambiente e Saneamento": (
        "Meio ambiente, desmatamento, mudanças climáticas, emissões de carbono, "
        "licenciamento ambiental, recursos hídricos, saneamento básico e reciclagem."
    ),
    "Agronegócio e Energia": (
        "Agricultura, pecuária, crédito rural, reforma agrária, biocombustíveis, "
        "energia elétrica, petróleo, gás, mineração e transição energética."
    ),
    "Segurança Pública e Justiça": (
        "Código Penal, crimes, penas, polícia, presídios, combate ao crime organizado, "
        "violência, armas, processo judicial e direitos do consumidor."
    ),
    "Economia, Mercado e Infraestrutura": (
        "Empresas, crédito, bancos, mercado financeiro, microempresas, transportes, "
        "rodovias, ferrovias, portos, aeroportos, habitação e desenvolvimento econômico."
    ),
    "Administração Pública e Homenagens": (
        "Requerimento de sessão solene, voto de pesar, moção de aplauso, homenagem, "
        "datas comemorativas, denominação de rodovia, servidores públicos e trâmite interno."
    ),
}

PROMPT_SISTEMA_RESUMO = (
    "Você é analista sênior de relações governamentais da consultoria Bússola Pública. "
    "Escreva em português claro e direto para executivos (CEOs e diretores), sem jargão jurídico excessivo."
)


def obter_cliente_openai() -> OpenAI:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or "sua-chave" in api_key:
        raise ValueError("OPENAI_API_KEY válida não encontrada no arquivo .env.")
    return OpenAI(api_key=api_key)


def similaridade_cosseno(vetor_a: np.ndarray, vetor_b: np.ndarray) -> float:
    norma_a = np.linalg.norm(vetor_a)
    norma_b = np.linalg.norm(vetor_b)
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return float(np.dot(vetor_a, vetor_b) / (norma_a * norma_b))


def carregar_ou_gerar_embeddings_temas(client: OpenAI) -> tuple[dict[str, np.ndarray], int]:
    """Carrega embeddings dos 10 temas do cache local ou gera via OpenAI se necessário."""
    if CAMINHO_CACHE_TEMAS.exists():
        with open(CAMINHO_CACHE_TEMAS, mode="r", encoding="utf-8") as arq:
            cache = json.load(arq)
        if list(cache.keys()) == list(TEMAS_ESTRATEGICOS.keys()):
            print("Embeddings dos 10 temas carregados do cache local (0 tokens gastos).")
            return {k: np.array(v, dtype=np.float32) for k, v in cache.items()}, 0

    print("Gerando embeddings dos 10 temas estratégicos pela primeira vez...")
    nomes_temas = list(TEMAS_ESTRATEGICOS.keys())
    descricoes = [f"{nome}: {desc}" for nome, desc in TEMAS_ESTRATEGICOS.items()]

    resposta = client.embeddings.create(model=MODELO_EMBEDDING, input=descricoes)
    tokens_gastos = resposta.usage.total_tokens if resposta.usage else 0

    cache_para_salvar = {
        nome: item.embedding for nome, item in zip(nomes_temas, resposta.data)
    }
    CAMINHO_CACHE_TEMAS.parent.mkdir(parents=True, exist_ok=True)
    with open(CAMINHO_CACHE_TEMAS, mode="w", encoding="utf-8") as arq:
        json.dump(cache_para_salvar, arq)

    vetores = {k: np.array(v, dtype=np.float32) for k, v in cache_para_salvar.items()}
    return vetores, tokens_gastos


def buscar_proposicoes_pendentes(limite: int | None) -> list[tuple[int, str, str]]:
    """Busca no Supabase proposições que ainda não possuem tema_ia."""
    engine = obter_engine()
    sql = """
        SELECT id, sigla_tipo, ementa
        FROM fato_proposicoes
        WHERE tema_ia IS NULL
          AND ementa IS NOT NULL
          AND TRIM(ementa) <> ''
        ORDER BY data_apresentacao DESC NULLS LAST, id DESC
    """
    if limite and limite > 0:
        sql += f" LIMIT {int(limite)}"

    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        raw_conn.close()


def atualizar_temas_no_banco(resultados: list[tuple[int, str, float]]) -> None:
    """Atualiza tema_ia e score_tema_ia em lote no Supabase."""
    if not resultados:
        return
    engine = obter_engine()
    sql_update = """
        UPDATE fato_proposicoes AS f
        SET
            tema_ia = v.tema_ia::VARCHAR(100),
            score_tema_ia = v.score_tema_ia::DOUBLE PRECISION,
            atualizado_em = NOW()
        FROM (VALUES %s) AS v(id, tema_ia, score_tema_ia)
        WHERE f.id = v.id::BIGINT;
    """
    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            execute_values(cur, sql_update, resultados, template="(%s, %s, %s)", page_size=500)
        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()


def classificar_proposicoes(limite: int | None = 10) -> None:
    print("=== Caminho A: Classificação Temática (Embeddings + Cosseno) ===")
    client = obter_cliente_openai()
    vetores_temas, tokens_temas = carregar_ou_gerar_embeddings_temas(client)

    pendentes = buscar_proposicoes_pendentes(limite=limite)
    if not pendentes:
        print("Nenhuma proposição pendente de tema_ia no Supabase.")
        return

    print(f"Proposições pendentes selecionadas para classificar: {len(pendentes)}")
    tokens_ementas = 0
    resultados_banco: list[tuple[int, str, float]] = []
    previews: list[dict[str, Any]] = []

    for inicio in range(0, len(pendentes), TAMANHO_LOTE):
        lote = pendentes[inicio : inicio + TAMANHO_LOTE]
        textos_limpos = [" ".join(str(row[2]).split())[:8000] for row in lote]

        resposta = client.embeddings.create(model=MODELO_EMBEDDING, input=textos_limpos)
        if resposta.usage:
            tokens_ementas += resposta.usage.total_tokens

        for (prop_id, sigla_tipo, ementa), item_emb in zip(lote, resposta.data):
            vetor_prop = np.array(item_emb.embedding, dtype=np.float32)

            melhor_tema = ""
            melhor_score = -1.0
            for nome_tema, vetor_tema in vetores_temas.items():
                score = similaridade_cosseno(vetor_prop, vetor_tema)
                if score > melhor_score:
                    melhor_score = score
                    melhor_tema = nome_tema

            score_arredondado = round(melhor_score, 4)
            resultados_banco.append((int(prop_id), melhor_tema, score_arredondado))
            if len(previews) < 10:
                previews.append(
                    {
                        "id": prop_id,
                        "tipo": sigla_tipo,
                        "tema": melhor_tema,
                        "score": score_arredondado,
                        "ementa": " ".join(str(ementa).split())[:85],
                    }
                )

        print(f"  -> Lote processado e classificado: {len(resultados_banco)}/{len(pendentes)}")

    atualizar_temas_no_banco(resultados_banco)

    total_tokens = tokens_temas + tokens_ementas
    custo_total_usd = (total_tokens / 1_000_000) * PRECO_EMBEDDING_POR_1M_USD
    media_tokens_prop = tokens_ementas / len(pendentes)
    custo_1000_usd = ((media_tokens_prop * 1000) / 1_000_000) * PRECO_EMBEDDING_POR_1M_USD

    print("\n--- Amostra das classificações salvas ---")
    for p in previews:
        print(f"  [{p['id']} | {p['tipo']}] -> {p['tema']} (score={p['score']}) | {p['ementa']}...")

    print("\n--- Relatório de Tokens e Custo (Caminho A) ---")
    print(f"  Proposições classificadas: {len(pendentes)}")
    print(f"  Tokens gastos (temas + ementas): {tokens_temas} + {tokens_ementas} = {total_tokens}")
    print(f"  Média por proposição: {media_tokens_prop:.1f} tokens")
    print(f"  Custo real desta execução: US$ {custo_total_usd:.6f}")
    print(f"  Projeção para 1.000 proposições: US$ {custo_1000_usd:.6f}")


def buscar_proposicoes_para_resumo(limite: int | None) -> list[tuple[Any, ...]]:
    """Busca apenas proposições substantivas (PL/PLP/PEC/MPV) de temas estratégicos sem resumo_ia."""
    engine = obter_engine()
    sql = """
        SELECT id, sigla_tipo, numero, ano, tema_ia, ementa
        FROM fato_proposicoes
        WHERE resumo_ia IS NULL
          AND tema_ia IS NOT NULL
          AND tema_ia <> 'Administração Pública e Homenagens'
          AND sigla_tipo IN ('PL', 'PLP', 'PEC', 'MPV')
          AND ementa IS NOT NULL
          AND TRIM(ementa) <> ''
        ORDER BY data_apresentacao DESC NULLS LAST, id DESC
    """
    if limite and limite > 0:
        sql += f" LIMIT {int(limite)}"

    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        raw_conn.close()


def atualizar_resumos_no_banco(resultados: list[tuple[int, str]]) -> None:
    """Salva resumo_ia em lote no Supabase."""
    if not resultados:
        return
    engine = obter_engine()
    sql_update = """
        UPDATE fato_proposicoes AS f
        SET
            resumo_ia = v.resumo_ia::TEXT,
            atualizado_em = NOW()
        FROM (VALUES %s) AS v(id, resumo_ia)
        WHERE f.id = v.id::BIGINT;
    """
    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            execute_values(cur, sql_update, resultados, template="(%s, %s)", page_size=200)
        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()


def gerar_resumos_executivos(limite: int | None = 10) -> None:
    print("\n=== Caminho B: Resumo Executivo em 3 Linhas (gpt-4o-mini) ===")
    client = obter_cliente_openai()
    pendentes = buscar_proposicoes_para_resumo(limite=limite)
    if not pendentes:
        print("Nenhuma proposição elegível pendente de resumo_ia no Supabase.")
        return

    print(f"Proposições elegíveis selecionadas (PL/PLP/PEC/MPV): {len(pendentes)}")
    tokens_in = 0
    tokens_out = 0
    resultados_banco: list[tuple[int, str]] = []
    previews: list[dict[str, Any]] = []

    for idx, (prop_id, sigla_tipo, numero, ano, tema_ia, ementa) in enumerate(pendentes, start=1):
        ano_fmt = str(int(ano)) if ano else "s/ano"
        num_fmt = str(int(numero)) if numero else "s/n"
        prompt_usuario = (
            f"Tema classificado: {tema_ia}\n"
            f"Proposição: {sigla_tipo} {num_fmt}/{ano_fmt}\n"
            f"Ementa: {' '.join(str(ementa).split())}\n\n"
            "Resuma essa proposição em exatamente 3 linhas curtas e objetivas para um executivo:\n"
            "1) O que muda na prática;\n"
            "2) Quem ou qual setor é impactado;\n"
            "3) Ponto de atenção."
        )

        resposta = client.chat.completions.create(
            model=MODELO_RESUMO,
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA_RESUMO},
                {"role": "user", "content": prompt_usuario},
            ],
            temperature=0.3,
            max_tokens=220,
        )
        resumo = (resposta.choices[0].message.content or "").strip()
        if resposta.usage:
            tokens_in += resposta.usage.prompt_tokens
            tokens_out += resposta.usage.completion_tokens

        resultados_banco.append((int(prop_id), resumo))
        if len(previews) < 3:
            previews.append({"id": prop_id, "label": f"{sigla_tipo} {num_fmt}/{ano_fmt}", "tema": tema_ia, "resumo": resumo})

        if idx % 10 == 0 or idx == len(pendentes):
            print(f"  -> Resumos gerados: {idx}/{len(pendentes)}")

    atualizar_resumos_no_banco(resultados_banco)

    custo_usd = (
        (tokens_in / 1_000_000) * PRECO_RESUMO_INPUT_1M_USD
        + (tokens_out / 1_000_000) * PRECO_RESUMO_OUTPUT_1M_USD
    )
    custo_1000_usd = (custo_usd / len(pendentes)) * 1000

    print("\n--- Amostra dos resumos executivos salvos ---")
    for p in previews:
        print(f"\n  [{p['id']} | {p['label']} | {p['tema']}]")
        for linha in p["resumo"].splitlines():
            print(f"    {linha}")

    print("\n--- Relatório de Tokens e Custo (Caminho B) ---")
    print(f"  Resumos gerados: {len(pendentes)}")
    print(f"  Tokens: input={tokens_in} | output={tokens_out}")
    print(f"  Custo real desta execução: US$ {custo_usd:.6f}")
    print(f"  Projeção para 1.000 resumos: US$ {custo_1000_usd:.6f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enriquecimento com IA (Embeddings e Resumos).")
    parser.add_argument(
        "--todos",
        action="store_true",
        help="Se informado, processa TODAS as proposições pendentes (sem limite de 10).",
    )
    parser.add_argument(
        "--resumos",
        action="store_true",
        help="Se informado, executa também o Caminho B (resumo executivo com gpt-4o-mini).",
    )
    args = parser.parse_args()
    limite = None if args.todos else 10

    classificar_proposicoes(limite=limite)
    if args.resumos:
        gerar_resumos_executivos(limite=limite)