import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import RAW_DIR


def encontrar_arquivo_mais_recente(prefixo: str) -> Path:
    """Encontra o JSON mais recente em data/raw/ para um determinado prefixo."""
    arquivos = sorted(RAW_DIR.glob(f"{prefixo}_*.json"))
    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum arquivo '{prefixo}_*.json' encontrado em {RAW_DIR}. "
            "Rode 'python -m src.extract' primeiro."
        )
    return arquivos[-1]


def carregar_json_para_df(prefixo: str) -> pd.DataFrame:
    """Lê o JSON bruto mais recente e converte para DataFrame Pandas."""
    caminho = encontrar_arquivo_mais_recente(prefixo)
    print(f"  Lendo raw: {caminho.name}")
    with open(caminho, mode="r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    return pd.json_normalize(dados)


def transformar_partidos() -> pd.DataFrame:
    df = carregar_json_para_df("partidos")
    if df.empty:
        return df

    df = df[["id", "sigla", "nome"]].copy()
    antes = len(df)
    df = df.dropna(subset=["id", "sigla", "nome"]).copy()
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df = df.dropna(subset=["id"]).copy()
    df["id"] = df["id"].astype(int)
    df = df.drop_duplicates(subset=["id"]).copy()

    print(f"  [partidos] {antes} brutos -> {len(df)} válidos")
    return df


def transformar_deputados() -> pd.DataFrame:
    df = carregar_json_para_df("deputados")
    if df.empty:
        return df

    colunas = ["id", "nome", "siglaPartido", "siglaUf", "idLegislatura", "email", "urlFoto"]
    df = df[colunas].copy()
    df = df.rename(
        columns={
            "siglaPartido": "sigla_partido",
            "siglaUf": "sigla_uf",
            "idLegislatura": "id_legislatura",
            "urlFoto": "url_foto",
        }
    )

    antes = len(df)
    df = df.dropna(subset=["id", "nome"]).copy()
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df["id_legislatura"] = pd.to_numeric(df["id_legislatura"], errors="coerce")
    df = df.dropna(subset=["id"]).copy()
    df["id"] = df["id"].astype(int)
    df = df.drop_duplicates(subset=["id"]).copy()

    print(f"  [deputados] {antes} brutos -> {len(df)} válidos")
    return df


def transformar_proposicoes() -> pd.DataFrame:
    df = carregar_json_para_df("proposicoes")
    if df.empty:
        return df

    colunas = ["id", "siglaTipo", "numero", "ano", "ementa", "dataApresentacao"]
    df = df[colunas].copy()
    df = df.rename(
        columns={
            "siglaTipo": "sigla_tipo",
            "dataApresentacao": "data_apresentacao",
        }
    )

    antes = len(df)
    # Campos obrigatórios
    df = df.dropna(subset=["id", "sigla_tipo", "ementa"]).copy()
    df = df[df["ementa"].astype(str).str.strip() != ""].copy()

    # Tipos numéricos e datas
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df["numero"] = pd.to_numeric(df["numero"], errors="coerce")
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce")
    df["data_apresentacao"] = pd.to_datetime(df["data_apresentacao"], errors="coerce")

    # Documentos acessórios (PAR, EMC-A) às vezes vêm com ano=0; trocamos para None
    df.loc[df["ano"] == 0, "ano"] = None

    df = df.dropna(subset=["id", "data_apresentacao"]).copy()
    df["id"] = df["id"].astype(int)

    # Link oficial para usar nos alertas do n8n
    df["url_ficha"] = (
        "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao="
        + df["id"].astype(str)
    )

    df = df.drop_duplicates(subset=["id"]).copy()
    print(f"  [proposicoes] {antes} brutos -> {len(df)} válidos")
    return df


def transformar_votacoes() -> pd.DataFrame:
    df = carregar_json_para_df("votacoes")
    if df.empty:
        return df

    colunas = ["id", "data", "dataHoraRegistro", "siglaOrgao", "descricao", "aprovacao"]
    df = df[colunas].copy()
    df = df.rename(
        columns={
            "dataHoraRegistro": "data_hora_registro",
            "siglaOrgao": "sigla_orgao",
        }
    )

    antes = len(df)
    df = df.dropna(subset=["id"]).copy()
    df["id"] = df["id"].astype(str).str.strip()

    df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
    df["data_hora_registro"] = pd.to_datetime(df["data_hora_registro"], errors="coerce")
    df["aprovacao"] = pd.to_numeric(df["aprovacao"], errors="coerce")

    df = df.drop_duplicates(subset=["id"]).copy()
    print(f"  [votacoes] {antes} brutos -> {len(df)} válidos")
    return df


def _gerar_id_despesa(row: pd.Series) -> str:
    """Cria uma chave única determinística para evitar colisões ou duplicidades."""
    chave = (
        f"{row.get('deputado_id')}|{row.get('cod_documento')}|"
        f"{row.get('parcela')}|{row.get('numDocumento')}|"
        f"{row.get('data_documento')}|{row.get('valor_liquido')}"
    )
    return hashlib.md5(chave.encode("utf-8")).hexdigest()


def transformar_despesas() -> pd.DataFrame:
    df = carregar_json_para_df("despesas")
    if df.empty:
        return df

    colunas = [
        "deputado_id",
        "codDocumento",
        "ano",
        "mes",
        "tipoDespesa",
        "dataDocumento",
        "numDocumento",
        "parcela",
        "valorDocumento",
        "valorLiquido",
        "nomeFornecedor",
        "cnpjCpfFornecedor",
        "urlDocumento",
    ]
    df = df[colunas].copy()
    df = df.rename(
        columns={
            "codDocumento": "cod_documento",
            "tipoDespesa": "tipo_despesa",
            "dataDocumento": "data_documento",
            "valorDocumento": "valor_documento",
            "valorLiquido": "valor_liquido",
            "nomeFornecedor": "nome_fornecedor",
            "cnpjCpfFornecedor": "cnpj_cpf_fornecedor",
            "urlDocumento": "url_documento",
        }
    )

    antes = len(df)
    df = df.dropna(subset=["deputado_id", "ano", "mes", "valor_liquido"]).copy()

    df["deputado_id"] = pd.to_numeric(df["deputado_id"], errors="coerce")
    df["cod_documento"] = pd.to_numeric(df["cod_documento"], errors="coerce")
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce")
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce")
    df["valor_documento"] = pd.to_numeric(df["valor_documento"], errors="coerce")
    df["valor_liquido"] = pd.to_numeric(df["valor_liquido"], errors="coerce")
    df["data_documento"] = pd.to_datetime(df["data_documento"], errors="coerce").dt.date

    # Validação de valores monetários positivos (remove estornos/ajustes <= 0)
    estornos = df[df["valor_liquido"] <= 0]
    if len(estornos) > 0:
        print(f"  [despesas] Descartados {len(estornos)} registros com valor_liquido <= 0 (estornos/ajustes)")
    df = df[df["valor_liquido"] > 0].copy()

    # Limpa CNPJ/CPF como texto para não perder zeros à esquerda
    df["cnpj_cpf_fornecedor"] = (
        df["cnpj_cpf_fornecedor"]
        .fillna("")
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .replace("", None)
    )

    df["id_registro"] = df.apply(_gerar_id_despesa, axis=1)
    df = df.drop_duplicates(subset=["id_registro"]).copy()

    colunas_finais = [
        "id_registro",
        "deputado_id",
        "cod_documento",
        "ano",
        "mes",
        "tipo_despesa",
        "data_documento",
        "valor_documento",
        "valor_liquido",
        "nome_fornecedor",
        "cnpj_cpf_fornecedor",
        "url_documento",
    ]
    df = df[colunas_finais].copy()
    print(f"  [despesas] {antes} brutos -> {len(df)} válidos")
    return df


def dataframe_para_registros(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Converte DataFrame para lista de dicionários substituindo NaN/NaT por None (NULL no SQL)."""
    registros: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        limpo: dict[str, Any] = {}
        for chave, valor in row.items():
            if pd.isna(valor):
                limpo[chave] = None
            elif hasattr(valor, "to_pydatetime"):
                limpo[chave] = valor.to_pydatetime()
            else:
                limpo[chave] = valor
        registros.append(limpo)
    return registros


def executar_transformacoes() -> dict[str, pd.DataFrame]:
    print("=== Iniciando Transformações e Validações (Pandas) ===")
    resultado = {
        "dim_partidos": transformar_partidos(),
        "dim_deputados": transformar_deputados(),
        "fato_proposicoes": transformar_proposicoes(),
        "fato_votacoes": transformar_votacoes(),
        "fato_despesas": transformar_despesas(),
    }
    print("=== Transformações concluídas! ===\n")
    return resultado


if __name__ == "__main__":
    executar_transformacoes()