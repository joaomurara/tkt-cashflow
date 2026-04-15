"""
db.py — Camada de acesso ao banco de dados PostgreSQL (Supabase) para o TKT Cash Flow App
"""

import json
import os
from contextlib import contextmanager
from datetime import datetime

import psycopg2
import psycopg2.extras
import streamlit as st


# ─── CONEXÃO ─────────────────────────────────────────────────────────────────

def _get_dsn() -> str:
    """Retorna a string de conexão do Supabase (via secrets ou variável de ambiente)."""
    try:
        return st.secrets["supabase"]["url"]
    except Exception:
        dsn = os.environ.get("SUPABASE_URL", "")
        if not dsn:
            raise RuntimeError(
                "Configure a URL do Supabase em .streamlit/secrets.toml:\n"
                "[supabase]\nurl = 'postgresql://postgres.xxxx:senha@aws-0-region.pooler.supabase.com:6543/postgres'"
            )
        return dsn


@contextmanager
def get_conn():
    """Abre conexão, commita no sucesso e rollback em erro, depois fecha."""
    conn = psycopg2.connect(_get_dsn(), cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── INICIALIZAÇÃO ────────────────────────────────────────────────────────────

def init_db():
    """Cria todas as tabelas se não existirem e roda migrações."""
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS database_erp (
                id            BIGSERIAL PRIMARY KEY,
                operacao      TEXT,
                codigo        TEXT,
                tipo          TEXT,
                lote          TEXT,
                razao_social  TEXT,
                descricao     TEXT,
                vencimento    TEXT,
                valor         DOUBLE PRECISION,
                valor_final   DOUBLE PRECISION,
                semana        INTEGER,
                probabilidade TEXT DEFAULT 'CONFIRMADO',
                imposto       TEXT DEFAULT 'NAO',
                status        TEXT DEFAULT 'PENDENTE',
                origem        TEXT DEFAULT 'ERP',
                importado_em  TEXT DEFAULT NOW()::TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS provisoes (
                id            BIGSERIAL PRIMARY KEY,
                operacao      TEXT,
                codigo        TEXT,
                tipo          TEXT,
                lote          TEXT,
                razao_social  TEXT,
                descricao     TEXT,
                vencimento    TEXT,
                valor         DOUBLE PRECISION,
                valor_final   DOUBLE PRECISION,
                semana        INTEGER,
                probabilidade TEXT DEFAULT 'CONFIRMADO',
                imposto       TEXT DEFAULT 'NAO',
                criado_em     TEXT DEFAULT NOW()::TEXT,
                atualizado_em TEXT DEFAULT NOW()::TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS fup_vendas (
                id              BIGSERIAL PRIMARY KEY,
                deal_id         TEXT,
                operacao        TEXT,
                codigo          TEXT,
                tipo            TEXT,
                lote            TEXT,
                razao_social    TEXT,
                descricao       TEXT,
                vencimento      TEXT,
                valor           DOUBLE PRECISION,
                valor_final     DOUBLE PRECISION,
                semana          INTEGER,
                probabilidade   TEXT,
                imposto         TEXT DEFAULT 'NAO',
                sincronizado_em TEXT DEFAULT NOW()::TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS config_pipedrive (
                deal_id              TEXT PRIMARY KEY,
                cliente              TEXT,
                negocio              TEXT,
                funil                TEXT,
                moeda                TEXT DEFAULT 'BRL',
                valor_original       DOUBLE PRECISION,
                cambio               DOUBLE PRECISION DEFAULT 1.0,
                valor_brl            DOUBLE PRECISION,
                data_cambio          TEXT,
                data_fechamento      TEXT,
                prazo_entrega        INTEGER DEFAULT 0,
                pct_comissao         DOUBLE PRECISION DEFAULT 0,
                tipo_fluxo           INTEGER DEFAULT 1,
                pct_entrada          DOUBLE PRECISION DEFAULT 0,
                n_parcelas           INTEGER DEFAULT 4,
                intervalo_parcelas   INTEGER DEFAULT 30,
                pct_pos_x            DOUBLE PRECISION DEFAULT 0,
                x_dias               INTEGER DEFAULT 30,
                pct_fat              DOUBLE PRECISION DEFAULT 0,
                pct_pos_fat          DOUBLE PRECISION DEFAULT 0,
                dias_pos_fat         INTEGER DEFAULT 30,
                pct_icms             DOUBLE PRECISION DEFAULT 0.088,
                dias_icms            INTEGER DEFAULT 10,
                pct_pis_cofins       DOUBLE PRECISION DEFAULT 0.059,
                dias_pis_cofins      INTEGER DEFAULT 25,
                pct_ir               DOUBLE PRECISION DEFAULT 0,
                dias_ir              INTEGER DEFAULT 0,
                probabilidade        TEXT DEFAULT 'ALTA',
                parcelas_livres_json TEXT DEFAULT '[]',
                mp_json              TEXT DEFAULT '[]',
                obs                  TEXT,
                ativo                INTEGER DEFAULT 1,
                atualizado_em        TEXT DEFAULT NOW()::TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS csv_mapeamento (
                id         BIGSERIAL PRIMARY KEY,
                nome       TEXT UNIQUE,
                mapeamento TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS saldos_bancarios (
                id            BIGSERIAL PRIMARY KEY,
                banco         TEXT,
                saldo         DOUBLE PRECISION,
                data          TEXT,
                atualizado_em TEXT DEFAULT NOW()::TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor TEXT
            )
        """)

        _migrar_db(cur)


# ─── MIGRAÇÕES ───────────────────────────────────────────────────────────────

def _migrar_db(cur):
    """Adiciona colunas novas sem perder dados (ADD COLUMN IF NOT EXISTS)."""
    novas_cfg = [
        ("probabilidade",        "TEXT DEFAULT 'ALTA'"),
        ("pct_ir",               "DOUBLE PRECISION DEFAULT 0"),
        ("dias_ir",              "INTEGER DEFAULT 0"),
        ("parcelas_livres_json", "TEXT DEFAULT '[]'"),
        ("mp_json",              "TEXT DEFAULT '[]'"),
    ]
    for col, defn in novas_cfg:
        cur.execute(
            f"ALTER TABLE config_pipedrive ADD COLUMN IF NOT EXISTS {col} {defn}"
        )
    cur.execute(
        "ALTER TABLE fup_vendas ADD COLUMN IF NOT EXISTS deal_id TEXT"
    )



_CFG_DEFAULTS = {
    "dt_ini":           "",
    "dt_fim":           "",
    "erp_corte_status": "1",
    "incluir_alta":     "1",
    "incluir_media":    "0",
}


def get_cfg(chave: str) -> str:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT valor FROM configuracoes WHERE chave = %s", (chave,))
        row = cur.fetchone()
        return row["valor"] if row else _CFG_DEFAULTS.get(chave, "")


def set_cfg(chave: str, valor: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO configuracoes (chave, valor) VALUES (%s, %s)
            ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor
        """, (chave, str(valor)))


def get_cfg_datas():
    """Retorna (dt_ini, dt_fim) como strings 'YYYY-MM-DD'."""
    from datetime import date
    ini = get_cfg("dt_ini") or ""
    fim = get_cfg("dt_fim") or ""
    hoje = date.today()
    if not ini:
        ini = f"{hoje.year}-01-01"
    if not fim:
        fim = f"{hoje.year}-12-31"
    return ini, fim


# ─── DATABASE ERP ────────────────────────────────────────────────────────────

def importar_erp(registros: list[dict], substituir=True):
    """Insere registros do ERP. Se substituir=True, limpa antes."""
    with get_conn() as conn:
        cur = conn.cursor()
        if substituir:
            cur.execute("DELETE FROM database_erp")
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO database_erp
              (operacao, codigo, tipo, lote, razao_social, descricao,
               vencimento, valor, valor_final, semana, probabilidade, imposto, status, origem)
            VALUES
              (%(operacao)s, %(codigo)s, %(tipo)s, %(lote)s, %(razao_social)s, %(descricao)s,
               %(vencimento)s, %(valor)s, %(valor_final)s, %(semana)s, %(probabilidade)s,
               %(imposto)s, %(status)s, %(origem)s)
        """, registros)
        cur.execute("SELECT COUNT(*) AS n FROM database_erp")
        return cur.fetchone()["n"]


def listar_erp(dt_ini=None, dt_fim=None, operacao=None, razao=None):
    sql = "SELECT * FROM database_erp WHERE 1=1"
    params = []
    if dt_ini:
        sql += " AND vencimento >= %s"; params.append(str(dt_ini))
    if dt_fim:
        sql += " AND vencimento <= %s"; params.append(str(dt_fim))
    if operacao:
        sql += " AND operacao = %s"; params.append(operacao)
    if razao:
        sql += " AND razao_social ILIKE %s"; params.append(f"%{razao}%")
    sql += " ORDER BY vencimento"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def salvar_mapeamento_csv(nome: str, mapeamento: dict):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO csv_mapeamento (nome, mapeamento) VALUES (%s, %s)
            ON CONFLICT (nome) DO UPDATE SET mapeamento = EXCLUDED.mapeamento
        """, (nome, json.dumps(mapeamento, ensure_ascii=False)))


def carregar_mapeamento_csv(nome: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT mapeamento FROM csv_mapeamento WHERE nome = %s", (nome,))
        row = cur.fetchone()
        return json.loads(row["mapeamento"]) if row else {}


def listar_mapeamentos_csv():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT nome FROM csv_mapeamento ORDER BY nome")
        return [r["nome"] for r in cur.fetchall()]


# ─── PROVISÕES ───────────────────────────────────────────────────────────────

def inserir_provisao(dados: dict) -> int:
    dados["semana"] = _semana(dados.get("vencimento"))
    dados["valor_final"] = (
        abs(dados["valor"]) if dados["operacao"] == "CREDITO"
        else -abs(dados["valor"])
    )
    with get_conn() as conn:
        cur = conn.cursor()
        # Sincroniza sequence antes de inserir (evita conflito de PK pós-migração)
        cur.execute("SELECT setval('provisoes_id_seq', (SELECT COALESCE(MAX(id), 0) FROM provisoes))")
        cur.execute("""
            INSERT INTO provisoes
              (operacao, codigo, tipo, lote, razao_social, descricao,
               vencimento, valor, valor_final, semana, probabilidade, imposto)
            VALUES
              (%(operacao)s, %(codigo)s, %(tipo)s, %(lote)s, %(razao_social)s, %(descricao)s,
               %(vencimento)s, %(valor)s, %(valor_final)s, %(semana)s, %(probabilidade)s, %(imposto)s)
            RETURNING id
        """, dados)
        return cur.fetchone()["id"]


def atualizar_provisao(pid: int, dados: dict):
    dados["semana"] = _semana(dados.get("vencimento"))
    dados["valor_final"] = (
        abs(dados["valor"]) if dados["operacao"] == "CREDITO"
        else -abs(dados["valor"])
    )
    dados["atualizado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dados["id"] = pid
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE provisoes SET
              operacao=%(operacao)s, codigo=%(codigo)s, tipo=%(tipo)s, lote=%(lote)s,
              razao_social=%(razao_social)s, descricao=%(descricao)s,
              vencimento=%(vencimento)s, valor=%(valor)s, valor_final=%(valor_final)s,
              semana=%(semana)s, probabilidade=%(probabilidade)s, imposto=%(imposto)s,
              atualizado_em=%(atualizado_em)s
            WHERE id = %(id)s
        """, dados)


def excluir_provisao(pid: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM provisoes WHERE id = %s", (pid,))


def listar_origens_provisoes():
    """Lista origens únicas de FUP e Simulação presentes em Provisões."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT tipo, codigo, razao_social,
                   COUNT(*)  AS qtd,
                   MIN(vencimento) AS dt_ini,
                   MAX(vencimento) AS dt_fim,
                   SUM(CASE WHEN operacao='CREDITO' THEN valor ELSE 0 END) AS total_cred,
                   SUM(CASE WHEN operacao='DEBITO'  THEN valor ELSE 0 END) AS total_deb
            FROM provisoes
            WHERE tipo IN ('FUP', 'FUP→PROVISAO', 'SIMULACAO')
            GROUP BY tipo, codigo, razao_social
            ORDER BY tipo, razao_social
        """)
        return [dict(r) for r in cur.fetchall()]


def excluir_provisoes_por_origem(tipo: str, codigo: str, razao_social: str) -> int:
    """Exclui em lote todas as provisões de uma origem (FUP ou Simulação)."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM provisoes WHERE tipo = %s AND codigo = %s AND razao_social = %s",
            (tipo, codigo, razao_social)
        )
        return cur.rowcount


def listar_provisoes(dt_ini=None, dt_fim=None, operacao=None, razao=None):
    sql = "SELECT * FROM provisoes WHERE 1=1"
    params = []
    if dt_ini:
        sql += " AND vencimento >= %s"; params.append(str(dt_ini))
    if dt_fim:
        sql += " AND vencimento <= %s"; params.append(str(dt_fim))
    if operacao:
        sql += " AND operacao = %s"; params.append(operacao)
    if razao:
        sql += " AND razao_social ILIKE %s"; params.append(f"%{razao}%")
    sql += " ORDER BY vencimento"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


# ─── FUP VENDAS ──────────────────────────────────────────────────────────────

def salvar_fup(linhas: list[dict]):
    """Substitui todos os registros FUP pelo novo conjunto."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM fup_vendas")
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO fup_vendas
              (deal_id, operacao, codigo, tipo, lote, razao_social, descricao,
               vencimento, valor, valor_final, semana, probabilidade, imposto)
            VALUES
              (%(deal_id)s, %(operacao)s, %(codigo)s, %(tipo)s, %(lote)s, %(razao_social)s,
               %(descricao)s, %(vencimento)s, %(valor)s, %(valor_final)s, %(semana)s,
               %(probabilidade)s, %(imposto)s)
        """, linhas)


def listar_fup(dt_ini=None, dt_fim=None, prob=None, deal_id=None):
    sql = "SELECT * FROM fup_vendas WHERE 1=1"
    params = []
    if dt_ini:
        sql += " AND vencimento >= %s"; params.append(str(dt_ini))
    if dt_fim:
        sql += " AND vencimento <= %s"; params.append(str(dt_fim))
    if prob:
        sql += " AND probabilidade = %s"; params.append(prob)
    if deal_id:
        sql += " AND deal_id = %s"; params.append(str(deal_id))
    sql += " ORDER BY vencimento"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def mover_fup_para_provisoes(deal_id: str, remover_do_fup: bool = True):
    """
    Move linhas do FUP para provisões.
    Retorna (n_movidas, msg_erro) — msg_erro é None em caso de sucesso.
    """
    linhas = listar_fup(deal_id=str(deal_id))
    if not linhas:
        return (0, None)

    # Identifica o deal pelo código e razao_social da primeira linha
    codigo_deal     = str(linhas[0].get("codigo", "") or "")
    razao_deal      = str(linhas[0].get("razao_social", "") or "")

    conn = None
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(_get_dsn(), cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = False
        cur = conn.cursor()

        # 1. Sincroniza a sequence com o max(id) atual (evita conflito de PK
        #    causado por migração com ids explícitos que não atualizaram a sequence)
        cur.execute("""
            SELECT setval('provisoes_id_seq',
                          (SELECT COALESCE(MAX(id), 0) FROM provisoes))
        """)

        # 2. Remove entradas anteriores deste deal em Provisões
        cur.execute("""
            DELETE FROM provisoes
            WHERE codigo = %s AND razao_social = %s
        """, (codigo_deal, razao_deal))

        # 3. Insere todas as linhas frescas
        for l in linhas:
            prov = {
                "operacao":      l.get("operacao", ""),
                "codigo":        l.get("codigo", ""),
                "tipo":          l.get("tipo", "FUP→PROVISAO"),
                "lote":          l.get("lote", ""),
                "razao_social":  l.get("razao_social", ""),
                "descricao":     l.get("descricao", ""),
                "vencimento":    l.get("vencimento", ""),
                "valor":         l.get("valor", 0),
                "valor_final":   l.get("valor_final", 0),
                "semana":        l.get("semana"),
                "probabilidade": l.get("probabilidade", "CONFIRMADO"),
                "imposto":       l.get("imposto", "NAO"),
            }
            cur.execute("""
                INSERT INTO provisoes
                  (operacao, codigo, tipo, lote, razao_social, descricao,
                   vencimento, valor, valor_final, semana, probabilidade, imposto)
                VALUES
                  (%(operacao)s, %(codigo)s, %(tipo)s, %(lote)s, %(razao_social)s,
                   %(descricao)s, %(vencimento)s, %(valor)s, %(valor_final)s,
                   %(semana)s, %(probabilidade)s, %(imposto)s)
            """, prov)

        # 3. Remove do FUP se solicitado
        if remover_do_fup:
            cur.execute("DELETE FROM fup_vendas WHERE deal_id = %s", (str(deal_id),))

        conn.commit()
        conn.close()
        return (len(linhas), None)

    except Exception as _oe:
        if conn:
            try: conn.rollback()
            except Exception: pass
            try: conn.close()
            except Exception: pass
        pgcode = getattr(_oe, "pgcode", None) or "?"
        return (0, f"[{pgcode}] {_oe}")


# ─── CONFIG PIPEDRIVE ─────────────────────────────────────────────────────────

def listar_config_pipedrive():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM config_pipedrive ORDER BY cliente")
        return [dict(r) for r in cur.fetchall()]


def salvar_config_deal(dados: dict):
    dados["atualizado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cols = list(dados.keys())
    placeholders = ", ".join(f"%({c})s" for c in cols)
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "deal_id")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO config_pipedrive ({', '.join(cols)})
            VALUES ({placeholders})
            ON CONFLICT (deal_id) DO UPDATE SET {updates}
        """, dados)


def remover_deals_inativos(ids_ativos: list[str]):
    """Marca como inativo qualquer deal que não está mais na lista."""
    if not ids_ativos:
        return
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE config_pipedrive SET ativo = 0
            WHERE deal_id != ALL(%s) AND ativo = 1
        """, (ids_ativos,))


def obter_config_deal(deal_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM config_pipedrive WHERE deal_id = %s", (str(deal_id),)
        )
        row = cur.fetchone()
        return dict(row) if row else None


# ─── SALDOS BANCÁRIOS ────────────────────────────────────────────────────────

def salvar_saldo(banco: str, saldo: float, data: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO saldos_bancarios (banco, saldo, data) VALUES (%s, %s, %s)
        """, (banco, saldo, data))


def listar_saldos_recentes():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.* FROM saldos_bancarios s
            INNER JOIN (
                SELECT banco, MAX(data) AS max_data
                FROM saldos_bancarios GROUP BY banco
            ) m ON s.banco = m.banco AND s.data = m.max_data
            ORDER BY s.banco
        """)
        return [dict(r) for r in cur.fetchall()]


def get_saldo_total() -> float:
    """Retorna a soma de todos os saldos bancários mais recentes cadastrados."""
    saldos = listar_saldos_recentes()
    return sum(r["saldo"] or 0 for r in saldos)


# ─── FC DIÁRIO (VIEW CONSOLIDADA) ────────────────────────────────────────────

def fc_diario(dt_ini=None, dt_fim=None, incluir_alta=True, incluir_media=True,
              erp_corte_status=True, saldo_inicial: float = None,
              inc_fci=True, inc_fcf=True):
    """
    Consolida DATABASE + Provisões + FUP Vendas em um único fluxo diário.

    erp_corte_status (bool):
        Quando True, lançamentos ERP com vencimento ANTES de dt_ini só entram
        no fluxo se o status for PAGO ou RECEBIDO — evita duplicidade com saldo inicial.

    saldo_inicial (float | None):
        Valor de partida para o saldo acumulado. Se None, usa get_saldo_total().

    inc_fci / inc_fcf (bool):
        Controla se provisões do tipo FCI / FCF entram no cálculo.
        Quando False, exclui as provisões daquele tipo.
    """
    filtros_prob = ["CONFIRMADO"]
    if incluir_alta:
        filtros_prob.append("ALTA")
    if incluir_media:
        filtros_prob.append("MEDIA")

    cond_dt = ""
    params_dt = []
    if dt_ini:
        cond_dt += " AND vencimento >= %s"; params_dt.append(str(dt_ini))
    if dt_fim:
        cond_dt += " AND vencimento <= %s"; params_dt.append(str(dt_fim))

    # Filtro de tipo para provisões (FCI / FCF)
    tipos_excluidos = []
    if not inc_fci:
        tipos_excluidos.append("FCI")
    if not inc_fcf:
        tipos_excluidos.append("FCF")
    if tipos_excluidos:
        cond_tipo_prov = " AND (tipo IS NULL OR tipo != ALL(%s))"
        params_tipo_prov = [tipos_excluidos]
    else:
        cond_tipo_prov = ""
        params_tipo_prov = []

    if erp_corte_status and dt_ini:
        sql_erp = f"""
            SELECT 'ERP' AS origem, operacao, codigo, tipo, lote,
                   razao_social, descricao, vencimento, valor, valor_final,
                   semana, probabilidade, imposto, status
            FROM database_erp
            WHERE probabilidade = ANY(%s)
              {cond_dt}
              AND NOT (vencimento < %s AND status NOT IN ('PAGO','RECEBIDO'))
        """
        params_erp = [filtros_prob] + params_dt + [str(dt_ini)]
    else:
        sql_erp = f"""
            SELECT 'ERP' AS origem, operacao, codigo, tipo, lote,
                   razao_social, descricao, vencimento, valor, valor_final,
                   semana, probabilidade, imposto, status
            FROM database_erp
            WHERE probabilidade = ANY(%s) {cond_dt}
        """
        params_erp = [filtros_prob] + params_dt

    sql_prov = f"""
        SELECT 'PROVISAO' AS origem, operacao, codigo, tipo, lote,
               razao_social, descricao, vencimento, valor, valor_final,
               semana, probabilidade, imposto, '' AS status
        FROM provisoes
        WHERE probabilidade = ANY(%s) {cond_dt} {cond_tipo_prov}
    """

    sql_fup = f"""
        SELECT 'FUP' AS origem, operacao, codigo, tipo, lote,
               razao_social, descricao, vencimento, valor, valor_final,
               semana, probabilidade, imposto, '' AS status
        FROM fup_vendas
        WHERE probabilidade = ANY(%s) {cond_dt}
    """

    union = f"""
        SELECT * FROM (
            {sql_erp}
            UNION ALL
            {sql_prov}
            UNION ALL
            {sql_fup}
        ) AS consolidated ORDER BY vencimento
    """
    all_params = (params_erp
                  + [filtros_prob] + params_dt + params_tipo_prov
                  + [filtros_prob] + params_dt)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(union, all_params)
        rows = [dict(r) for r in cur.fetchall()]

    if saldo_inicial is None:
        saldo_inicial = get_saldo_total()
    saldo = float(saldo_inicial)
    for r in rows:
        saldo += r.get("valor_final") or 0
        r["saldo_acumulado"] = round(saldo, 2)

    return rows


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _semana(vencimento):
    if not vencimento:
        return None
    try:
        dt = datetime.strptime(str(vencimento)[:10], "%Y-%m-%d")
        return dt.isocalendar()[1]
    except Exception:
        return None
