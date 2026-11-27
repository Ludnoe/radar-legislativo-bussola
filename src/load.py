import math
import os

from dotenv import load_dotenv
from psycopg2.extras import execute_values
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.transform import dataframe_para_registros, executar_transformacoes

TAMANHO_LOTE = 500


def obter_engine() -> Engine:
    """Lê a DATABASE_URL do arquivo .env e cria a conexão com o PostgreSQL (Supabase)."""
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL não encontrada no arquivo .env.")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    return create_engine(database_url)


UPSERT_CONFIG = {
    "dim_partidos": {
        "sql": """
            INSERT INTO dim_partidos (id, sigla, nome, atualizado_em)
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                sigla = EXCLUDED.sigla,
                nome = EXCLUDED.nome,
                atualizado_em = NOW();
        """,
        "template": "(%(id)s, %(sigla)s, %(nome)s, NOW())",
    },
    "dim_deputados": {
        "sql": """
            INSERT INTO dim_deputados (
                id, nome, sigla_partido, sigla_uf, id_legislatura, email, url_foto, atualizado_em
            )
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                nome = EXCLUDED.nome,
                sigla_partido = EXCLUDED.sigla_partido,
                sigla_uf = EXCLUDED.sigla_uf,
                id_legislatura = EXCLUDED.id_legislatura,
                email = EXCLUDED.email,
                url_foto = EXCLUDED.url_foto,
                atualizado_em = NOW();
        """,
        "template": "(%(id)s, %(nome)s, %(sigla_partido)s, %(sigla_uf)s, %(id_legislatura)s, %(email)s, %(url_foto)s, NOW())",
    },
    "fato_proposicoes": {
        "sql": """
            INSERT INTO fato_proposicoes (
                id, sigla_tipo, numero, ano, ementa, data_apresentacao, url_ficha, atualizado_em
            )
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                sigla_tipo = EXCLUDED.sigla_tipo,
                numero = EXCLUDED.numero,
                ano = EXCLUDED.ano,
                ementa = EXCLUDED.ementa,
                data_apresentacao = EXCLUDED.data_apresentacao,
                url_ficha = EXCLUDED.url_ficha,
                atualizado_em = NOW();
        """,
        "template": "(%(id)s, %(sigla_tipo)s, %(numero)s, %(ano)s, %(ementa)s, %(data_apresentacao)s, %(url_ficha)s, NOW())",
    },
    "fato_votacoes": {
        "sql": """
            INSERT INTO fato_votacoes (
                id, data, data_hora_registro, sigla_orgao, descricao, aprovacao, atualizado_em
            )
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                data = EXCLUDED.data,
                data_hora_registro = EXCLUDED.data_hora_registro,
                sigla_orgao = EXCLUDED.sigla_orgao,
                descricao = EXCLUDED.descricao,
                aprovacao = EXCLUDED.aprovacao,
                atualizado_em = NOW();
        """,
        "template": "(%(id)s, %(data)s, %(data_hora_registro)s, %(sigla_orgao)s, %(descricao)s, %(aprovacao)s, NOW())",
    },
    "fato_despesas": {
        "sql": """
            INSERT INTO fato_despesas (
                id_registro, deputado_id, cod_documento, ano, mes, tipo_despesa,
                data_documento, valor_documento, valor_liquido,
                nome_fornecedor, cnpj_cpf_fornecedor, url_documento, atualizado_em
            )
            VALUES %s
            ON CONFLICT (id_registro) DO UPDATE SET
                valor_documento = EXCLUDED.valor_documento,
                valor_liquido = EXCLUDED.valor_liquido,
                atualizado_em = NOW();
        """,
        "template": "(%(id_registro)s, %(deputado_id)s, %(cod_documento)s, %(ano)s, %(mes)s, %(tipo_despesa)s, %(data_documento)s, %(valor_documento)s, %(valor_liquido)s, %(nome_fornecedor)s, %(cnpj_cpf_fornecedor)s, %(url_documento)s, NOW())",
    },
}


def executar_carga() -> None:
    tabelas = executar_transformacoes()
    engine = obter_engine()

    ordem_carga = [
        "dim_partidos",
        "dim_deputados",
        "fato_proposicoes",
        "fato_votacoes",
        "fato_despesas",
    ]

    print("=== Iniciando Carga em Lotes no Supabase (PostgreSQL) ===")
    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            for nome_tabela in ordem_carga:
                df = tabelas[nome_tabela]
                if df.empty:
                    print(f"  [AVISO] {nome_tabela}: sem registros para carregar.")
                    continue

                registros = dataframe_para_registros(df)
                total = len(registros)
                total_lotes = math.ceil(total / TAMANHO_LOTE)
                config = UPSERT_CONFIG[nome_tabela]

                for indice, inicio in enumerate(range(0, total, TAMANHO_LOTE), start=1):
                    lote = registros[inicio : inicio + TAMANHO_LOTE]
                    execute_values(
                        cur,
                        config["sql"],
                        lote,
                        template=config["template"],
                        page_size=TAMANHO_LOTE,
                    )
                    print(
                        f"  -> {nome_tabela}: lote {indice}/{total_lotes} enviado ({len(lote)} registros)"
                    )

        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()

    print("=== Carga finalizada com sucesso! ===")


if __name__ == "__main__":
    executar_carga()