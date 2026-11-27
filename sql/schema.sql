-- ============================================================
-- Radar Legislativo (Bússola Pública) - Modelo Dimensional
-- ============================================================

-- 1. Dimensão Partidos
CREATE TABLE IF NOT EXISTS dim_partidos (
    id INTEGER PRIMARY KEY,
    sigla VARCHAR(30) NOT NULL,
    nome VARCHAR(150) NOT NULL,
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Dimensão Deputados
CREATE TABLE IF NOT EXISTS dim_deputados (
    id INTEGER PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    sigla_partido VARCHAR(30),
    sigla_uf VARCHAR(2),
    id_legislatura INTEGER,
    email VARCHAR(150),
    url_foto TEXT,
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Fato Proposições (inclui colunas reservadas para a Camada de IA)
CREATE TABLE IF NOT EXISTS fato_proposicoes (
    id BIGINT PRIMARY KEY,
    sigla_tipo VARCHAR(20) NOT NULL,
    numero INTEGER,
    ano INTEGER,
    ementa TEXT NOT NULL,
    data_apresentacao TIMESTAMP,
    url_ficha TEXT,
    tema_ia VARCHAR(100),
    score_tema_ia DOUBLE PRECISION,
    resumo_ia TEXT,
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Fato Votações (id é TEXT pois a API usa formato composto ex: '2655570-60')
CREATE TABLE IF NOT EXISTS fato_votacoes (
    id TEXT PRIMARY KEY,
    data DATE,
    data_hora_registro TIMESTAMP,
    sigla_orgao VARCHAR(30),
    descricao TEXT,
    aprovacao SMALLINT,
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Fato Despesas (ligada à dim_deputados; valores negativos/estornos tratados no Pandas)
CREATE TABLE IF NOT EXISTS fato_despesas (
    id_registro TEXT PRIMARY KEY,
    deputado_id INTEGER NOT NULL REFERENCES dim_deputados(id),
    cod_documento BIGINT,
    ano INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    tipo_despesa VARCHAR(150),
    data_documento DATE,
    valor_documento NUMERIC(12, 2),
    valor_liquido NUMERIC(12, 2) NOT NULL,
    nome_fornecedor VARCHAR(200),
    cnpj_cpf_fornecedor VARCHAR(20),
    url_documento TEXT,
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);