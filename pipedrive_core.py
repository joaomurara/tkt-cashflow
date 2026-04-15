"""
pipedrive_core.py — Lógica Pipedrive e geração de fluxo de caixa
Extraído de exportar_pipedrive.py e adaptado para usar db.py (SQLite)
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from db import (
    salvar_config_deal, listar_config_pipedrive, obter_config_deal,
    remover_deals_inativos, salvar_fup
)

# ─── CONFIGURAÇÃO PIPEDRIVE ──────────────────────────────────────────────────
def _get_api_token() -> str:
    try:
        import streamlit as st
        return st.secrets["pipedrive"]["api_key"]
    except Exception:
        return os.environ.get("PIPEDRIVE_API_KEY", "")

API_TOKEN = _get_api_token()
BASE_URL  = "https://api.pipedrive.com/v1"

FILTROS = {
    "Nacional":   ["Em fechamento", "Assinatura de Pedido e Pagamento"],
    "Exportação": ["Em fechamento", "Aguardando Pagamento"],
}

ETIQUETA_OBRIGATORIA    = "TAG FINANCAS"
ETIQUETA_OBRIGATORIA_ID = None  # resolvido dinamicamente pelo nome

# ─── CÂMBIO ─────────────────────────────────────────────────────────────────
CAMBIO_API        = "https://economia.awesomeapi.com.br/json/last/{pairs}"
MOEDAS_DIRETAS    = ["USD", "EUR", "ARS", "COP", "PEN", "CRC"]
MOEDAS_CRUZADAS   = ["HNL", "GTQ"]
MOEDAS_PAREADAS_USD = ["PAB"]

# ─── CUSTOS E IMPOSTOS PADRÃO ────────────────────────────────────────────────
CUSTOS_PADRAO = [
    (42,  0.25, "CUSTOS 42 dias"),
    (49,  0.02, "CUSTOS 49 dias"),
    (67,  0.07, "CUSTOS 67 dias"),
    (97,  0.01, "CUSTOS 97 dias"),
    (127, 0.01, "CUSTOS 127 dias"),
]
IMPOSTOS_PADRAO = [
    (10,  0.088, "ICMS"),
    (25,  0.059, "PIS/COFINS"),
]
PRAZO_BASE_CUSTOS = 60


# ─── CÂMBIO ─────────────────────────────────────────────────────────────────

def buscar_cambio(log_fn=None):
    """Retorna dict {moeda: taxa_BRL}. log_fn é chamado com mensagens de log."""
    cambio = {"BRL": 1.0}
    _log = log_fn or print
    try:
        pares_diretos  = ",".join(f"{m}-BRL" for m in MOEDAS_DIRETAS)
        pares_cruzados = ",".join(f"USD-{m}" for m in MOEDAS_CRUZADAS)
        todos = f"{pares_diretos},{pares_cruzados}"

        resp = requests.get(CAMBIO_API.format(pairs=todos), timeout=10)
        resp.raise_for_status()
        data = resp.json()

        usd_brl = None
        usd_cruzados = {}

        for key, val in data.items():
            code   = val.get("code")
            codein = val.get("codein")
            taxa   = float(val.get("bid", 0))
            if not taxa:
                continue
            if codein == "BRL":
                cambio[code] = taxa
                if code == "USD":
                    usd_brl = taxa
                _log(f"💱 {code}/BRL = {taxa:.4f}  ({val.get('create_date', '')})")
            elif code == "USD" and codein in MOEDAS_CRUZADAS:
                usd_cruzados[codein] = taxa

        if usd_brl:
            for moeda, usd_x in usd_cruzados.items():
                if usd_x > 0:
                    taxa_cruzada = round(usd_brl / usd_x, 4)
                    cambio[moeda] = taxa_cruzada
                    _log(f"💱 {moeda}/BRL = {taxa_cruzada:.4f}  (via USD)")
            for moeda in MOEDAS_PAREADAS_USD:
                cambio[moeda] = usd_brl
                _log(f"💱 {moeda}/BRL = {usd_brl:.4f}  (pareada USD)")
    except Exception as e:
        _log(f"⚠️ Não foi possível buscar câmbio: {e}")
    return cambio


# ─── API PIPEDRIVE ───────────────────────────────────────────────────────────

def get_all(endpoint, params=None):
    params = params or {}
    params.update({"api_token": API_TOKEN, "limit": 100, "start": 0})
    all_data = []
    while True:
        r = requests.get(f"{BASE_URL}/{endpoint}", params=params)
        r.raise_for_status()
        resp = r.json()
        data = resp.get("data") or []
        all_data.extend(data)
        pag = resp.get("additional_data", {}).get("pagination", {})
        if pag.get("more_items_in_collection"):
            params["start"] += params["limit"]
        else:
            break
    return all_data


def _resolver_id_etiqueta():
    """
    Busca o ID da etiqueta pelo nome (case-insensitive) via dealFields.
    Retorna o ID ou None se não encontrado.
    """
    try:
        fields = get_all("dealFields")
        for f in fields:
            if f.get("key") == "label":
                for opt in f.get("options", []):
                    if str(opt.get("label", "")).strip().upper() == ETIQUETA_OBRIGATORIA.strip().upper():
                        return str(opt["id"])
    except Exception:
        pass
    # Fallback ao ID hardcoded se existir
    return str(ETIQUETA_OBRIGATORIA_ID) if ETIQUETA_OBRIGATORIA_ID else None


def _extrair_labels(deal):
    """
    Extrai todos os IDs de label de um deal, normalizando para lista de strings.
    Trata os formatos possíveis da API Pipedrive:
      - None / []
      - inteiro:  87
      - string:   "87"
      - csv:      "87,92"
      - lista:    [87, 92]
    """
    raw = deal.get("label")
    if raw is None or raw == "" or raw == []:
        return []
    if isinstance(raw, list):
        ids = []
        for item in raw:
            ids += [s.strip() for s in str(item).split(",") if s.strip()]
        return ids
    # int ou string (possivelmente "87,92")
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def _tem_etiqueta(deal, etiqueta_id):
    """Verifica se o deal tem a etiqueta, independente do formato retornado pela API."""
    return str(etiqueta_id) in _extrair_labels(deal)


def buscar_deals_ativos():
    """Retorna deals filtrados por funil, estágio e etiqueta."""
    pipelines = get_all("pipelines")
    pipeline_map = {p["name"]: p["id"] for p in pipelines}
    stages_raw   = get_all("stages")
    stage_map    = {(s["pipeline_id"], s["name"]): s["id"] for s in stages_raw}

    etiqueta_id = _resolver_id_etiqueta()

    deals_validos = []
    for funil, estagios in FILTROS.items():
        pid = pipeline_map.get(funil)
        if not pid:
            continue
        for estagio in estagios:
            sid = stage_map.get((pid, estagio))
            if not sid:
                continue
            deals = get_all("deals", {"status": "open", "pipeline_id": pid, "stage_id": sid})
            for d in deals:
                # Se não há etiqueta configurada, aceita todos os deals do estágio
                if etiqueta_id is None or _tem_etiqueta(d, etiqueta_id):
                    d["_funil"] = funil
                    deals_validos.append(d)
    return deals_validos


def diagnosticar_pipedrive(log_fn=None):
    """
    Faz um diagnóstico completo da conexão Pipedrive.
    Retorna dict com todas as informações encontradas para identificar
    por que deals não estão sendo capturados.
    """
    _log = log_fn or print
    resultado = {
        "pipelines": [],
        "stages": [],
        "etiquetas": [],
        "deals_abertos": [],
        "filtros_configurados": FILTROS,
        "etiqueta_configurada_id": ETIQUETA_OBRIGATORIA_ID,
        "etiqueta_configurada_nome": ETIQUETA_OBRIGATORIA,
        "erros": [],
    }

    try:
        _log("📡 Buscando pipelines...")
        pipelines = get_all("pipelines")
        for p in pipelines:
            resultado["pipelines"].append({"id": p["id"], "nome": p["name"]})
            _log(f"  Pipeline: id={p['id']} nome='{p['name']}'")

        _log("📡 Buscando estágios...")
        stages = get_all("stages")
        pipeline_id_nome = {p["id"]: p["name"] for p in pipelines}
        for s in stages:
            resultado["stages"].append({
                "id": s["id"],
                "nome": s["name"],
                "pipeline_id": s["pipeline_id"],
                "pipeline_nome": pipeline_id_nome.get(s["pipeline_id"], "?"),
            })
            _log(f"  Estágio: '{pipeline_id_nome.get(s['pipeline_id'],'?')}' > '{s['name']}' (id={s['id']})")

        _log("📡 Buscando etiquetas (deal fields)...")
        try:
            fields = get_all("dealFields")
            for f in fields:
                if f.get("key") == "label":
                    for opt in f.get("options", []):
                        resultado["etiquetas"].append({"id": opt["id"], "nome": opt["label"]})
                        _log(f"  Etiqueta: id={opt['id']} nome='{opt['label']}'")
        except Exception as e:
            _log(f"  ⚠️ Não foi possível buscar etiquetas: {e}")

        # Resolve ID da etiqueta pelo nome
        etiqueta_id_resolvido = None
        for e in resultado["etiquetas"]:
            if e["nome"].strip().upper() == ETIQUETA_OBRIGATORIA.strip().upper():
                etiqueta_id_resolvido = str(e["id"])
                _log(f"\n✅ Etiqueta '{ETIQUETA_OBRIGATORIA}' resolvida → id={etiqueta_id_resolvido}")
                break
        if not etiqueta_id_resolvido:
            _log(f"\n⚠️  Etiqueta '{ETIQUETA_OBRIGATORIA}' não encontrada via dealFields.")
        resultado["etiqueta_id_resolvido"] = etiqueta_id_resolvido

        # Busca ampla: TODOS os deals abertos para inspecionar campo label
        _log("\n📡 Buscando TODOS os deals abertos para inspecionar campo 'label'...")
        try:
            todos_deals = get_all("deals", {"status": "open"})
            _log(f"  Total de deals abertos: {len(todos_deals)}")
            # Mostra os primeiros 5 para ver formato do campo label
            for d in todos_deals[:5]:
                raw_label = d.get("label")
                _log(f"  Ex. deal #{d['id']} '{d.get('title','')}' — label bruto: {repr(raw_label)} (tipo: {type(raw_label).__name__})")
            resultado["total_deals_abertos"] = len(todos_deals)
            resultado["exemplo_label_bruto"] = [
                {"id": d["id"], "titulo": d.get("title",""), "label_bruto": repr(d.get("label"))}
                for d in todos_deals[:10]
            ]
            # Quantos têm a etiqueta
            if etiqueta_id_resolvido:
                com_etiq = [d for d in todos_deals if etiqueta_id_resolvido in _extrair_labels(d)]
                _log(f"  Deals com etiqueta '{ETIQUETA_OBRIGATORIA}' (id={etiqueta_id_resolvido}): {len(com_etiq)}")
                resultado["deals_com_etiqueta_total"] = len(com_etiq)
                for d in com_etiq[:10]:
                    _log(f"    → #{d['id']} '{d.get('title','')}' label={repr(d.get('label'))}")
        except Exception as e:
            _log(f"  ⚠️ Erro ao buscar todos os deals: {e}")

        _log("\n📡 Buscando deals por funil/estágio configurado...")
        pipeline_map = {p["name"]: p["id"] for p in pipelines}
        stage_map    = {(s["pipeline_id"], s["name"]): s["id"] for s in stages}

        for funil, estagios in FILTROS.items():
            pid = pipeline_map.get(funil)
            _log(f"\n  Funil configurado: '{funil}' → id={pid}")
            if not pid:
                _log(f"    ❌ Funil '{funil}' NÃO encontrado no Pipedrive!")
                _log(f"    Pipelines disponíveis: {[p['name'] for p in pipelines]}")
                continue

            for estagio in estagios:
                sid = stage_map.get((pid, estagio))
                _log(f"  Estágio configurado: '{estagio}' → id={sid}")
                if not sid:
                    stages_do_funil = [s["name"] for s in stages if s["pipeline_id"] == pid]
                    _log(f"    ❌ Estágio '{estagio}' NÃO encontrado!")
                    _log(f"    Estágios disponíveis neste funil: {stages_do_funil}")
                    continue

                deals = get_all("deals", {"status": "open", "pipeline_id": pid, "stage_id": sid})
                _log(f"    Deals neste estágio: {len(deals)}")
                for d in deals:
                    labels_extraidas = _extrair_labels(d)
                    tem_etiqueta = etiqueta_id_resolvido in labels_extraidas if etiqueta_id_resolvido else False
                    resultado["deals_abertos"].append({
                        "id": d["id"],
                        "titulo": d.get("title", ""),
                        "funil": funil,
                        "estagio": estagio,
                        "label_bruto": repr(d.get("label")),
                        "labels_extraidas": labels_extraidas,
                        "tem_etiqueta_financas": tem_etiqueta,
                    })
                    status = "✅" if tem_etiqueta else f"❌ label_bruto={repr(d.get('label'))} extraido={labels_extraidas}"
                    _log(f"    Deal #{d['id']} '{d.get('title','')}' — etiqueta: {status}")

    except Exception as e:
        resultado["erros"].append(str(e))
        _log(f"❌ Erro no diagnóstico: {e}")

    return resultado


# ─── SINCRONIZAÇÃO ───────────────────────────────────────────────────────────

def sincronizar_pipedrive(log_fn=None):
    """
    Sincroniza deals do Pipedrive:
    1. Busca deals ativos com a etiqueta correta
    2. Atualiza config_pipedrive no SQLite (preservando configurações manuais)
    3. Gera linhas de fluxo e salva em fup_vendas
    Retorna dict com estatísticas.
    """
    _log = log_fn or print
    stats = {"novos": 0, "atualizados": 0, "removidos": 0, "linhas": 0, "erros": []}

    _log("🔄 Buscando câmbio...")
    cambio = buscar_cambio(log_fn=_log)

    _log("📡 Buscando deals no Pipedrive...")
    try:
        deals = buscar_deals_ativos()
    except Exception as e:
        stats["erros"].append(f"Erro ao buscar deals: {e}")
        return stats

    _log(f"✅ {len(deals)} deal(s) encontrado(s)")
    ids_ativos = [str(d["id"]) for d in deals]

    # Remover deals que perderam a etiqueta
    remover_deals_inativos(ids_ativos)

    hoje = datetime.now().strftime("%Y-%m-%d")

    for deal in deals:
        did   = str(deal["id"])
        funil = deal.get("_funil", "Nacional")
        moeda = deal.get("currency", "BRL")
        valor_orig = float(deal.get("value") or 0)
        taxa  = cambio.get(moeda, 1.0)
        valor_brl = round(valor_orig * taxa, 2)
        negocio = deal.get("title", "")
        cliente = negocio or deal.get("org_name") or deal.get("person_name") or "—"
        close_date = deal.get("expected_close_date", "") or ""

        # Verifica se já existe config
        cfg_existente = obter_config_deal(did)
        is_novo = cfg_existente is None

        dados_cfg = {
            "deal_id":       did,
            "cliente":       cliente,
            "negocio":       negocio,
            "funil":         funil,
            "moeda":         moeda,
            "valor_original": valor_orig,
            "cambio":        taxa,
            "valor_brl":     valor_brl,
            "data_cambio":   hoje,
            "ativo":         1,
        }

        # Preserva data_fechamento se já configurada manualmente
        if cfg_existente and cfg_existente.get("data_fechamento"):
            dados_cfg["data_fechamento"] = cfg_existente["data_fechamento"]
        elif close_date:
            dados_cfg["data_fechamento"] = close_date[:10]

        salvar_config_deal(dados_cfg)
        if is_novo:
            stats["novos"] += 1
            _log(f"  ➕ Novo: {cliente} — {negocio}")
        else:
            stats["atualizados"] += 1

    # Gerar linhas de fluxo com as configs atuais
    _log("⚙️  Gerando linhas de fluxo de caixa...")
    configs = listar_config_pipedrive()
    todas_linhas = []

    for cfg in configs:
        if not cfg.get("ativo"):
            continue
        did   = cfg["deal_id"]
        prob  = cfg.get("probabilidade", "ALTA") or "ALTA"
        close = cfg.get("data_fechamento")
        vbrl  = cfg.get("valor_brl") or 0
        funil = cfg.get("funil", "Nacional")
        cliente = cfg.get("cliente", "")

        if not close or not vbrl:
            _log(f"  ⚠️  {cliente} ({did}): sem data de fechamento ou valor — pulando")
            continue

        try:
            linhas = linhas_deal(cfg, did, cliente, funil, close, vbrl, prob)
            for l in linhas:
                l["deal_id"] = did
            todas_linhas.extend(linhas)
        except Exception as e:
            msg = f"Erro em deal {did} ({cliente}): {e}"
            stats["erros"].append(msg)
            _log(f"  ❌ {msg}")

    salvar_fup(todas_linhas)
    stats["linhas"] = len(todas_linhas)
    _log(f"✅ {stats['linhas']} linha(s) de fluxo gerada(s)")
    return stats


# ─── GERAÇÃO DE LINHAS DE FLUXO ─────────────────────────────────────────────

def linhas_deal(cfg, deal_id, cliente, funil, close_date, valor_brl, prob="ALTA"):
    rows = []
    close_dt = _parse_date(close_date)
    is_exp   = funil == "Exportação"

    tipo      = _n_int(cfg.get("tipo_fluxo") or cfg.get("Tipo Fluxo (1/2/3)"), 1)
    pct_ent   = _pct(cfg.get("pct_entrada") or cfg.get("% Entrada"), 0.0)
    pct_com   = _pct(cfg.get("pct_comissao") or cfg.get("% Comissão"), 0.0)
    prazo_ent = _n_int(cfg.get("prazo_entrega") or cfg.get("Prazo Entrega (dias)"), 0)

    total_com_export = 0.0
    # fat_dt é sempre fechamento + prazo de entrega — independente do tipo de fluxo.
    # É a âncora para cálculo de impostos e referência "faturamento" na MP.
    fat_dt = _add_days(close_dt, prazo_ent) if prazo_ent else close_dt

    def linha(op, desc, dt, valor, imposto="NAO"):
        if not dt:
            return
        vf = abs(round(valor, 2)) if op == "CREDITO" else -abs(round(valor, 2))
        rows.append({
            "deal_id":       str(deal_id),
            "OPERACAO":      op,
            "operacao":      op,
            "Codigo":        deal_id,
            "codigo":        str(deal_id),
            "TIPO":          "FUP",
            "tipo":          "FUP",
            "Lote":          funil,
            "lote":          funil,
            "Razao Social":  cliente,
            "razao_social":  cliente,
            "Descricao":     desc,
            "descricao":     desc,
            "Vencimento":    _fmt_date(dt),
            "vencimento":    _fmt_date(dt),
            "Valor":         abs(round(valor, 2)),
            "valor":         abs(round(valor, 2)),
            "Valor Final":   vf,
            "valor_final":   vf,
            "Semana":        _semana(dt),
            "semana":        _semana(dt),
            "PROBABILIDADE": prob,
            "probabilidade": prob,
            "Imposto?":      imposto,
            "imposto":       imposto,
        })

    def comissao(dt_receb, val_parcela, label):
        nonlocal total_com_export
        if pct_com <= 0:
            return
        val_com = val_parcela * pct_com
        if is_exp:
            total_com_export += val_com
        else:
            dt_com = _proximo_mes_dia(dt_receb, 10)
            linha("DEBITO", f"COMISSÃO {pct_com*100:.1f}% - {label}", dt_com, val_com)

    # ── TIPO 1 ──────────────────────────────────────────────────────────────
    if tipo == 1:
        n_parc    = _n_int(cfg.get("n_parcelas") or cfg.get("N° Parcelas (Tipo 1)"), 4)
        intervalo = _n_int(cfg.get("intervalo_parcelas") or cfg.get("Intervalo Parcelas (dias) (Tipo 1)"), 30)
        val_ent   = valor_brl * pct_ent
        val_parc  = (valor_brl - val_ent) / n_parc if n_parc > 0 else 0

        if pct_ent > 0:
            linha("CREDITO", "ENTRADA", close_dt, val_ent)
            comissao(close_dt, val_ent, "ENTRADA")

        for i in range(n_parc):
            parc_dt = _add_days(close_dt, (i + 1) * intervalo)
            linha("CREDITO", f"PARCELA {i+1}/{n_parc}", parc_dt, val_parc)
            comissao(parc_dt, val_parc, f"P{i+1}")

    # ── TIPO 2 ──────────────────────────────────────────────────────────────
    elif tipo == 2:
        pct_pos = _pct(cfg.get("pct_pos_x") or cfg.get("% Pós X dias (Tipo 2/3)"), 0.0)
        x_dias  = _n_int(cfg.get("x_dias") or cfg.get("X Dias (Tipo 2/3)"), 30)
        pct_fat = _pct(cfg.get("pct_fat") or cfg.get("% Faturamento (Tipo 2/3)"), 0.0)

        val_ent = valor_brl * pct_ent
        val_pos = valor_brl * pct_pos
        val_fat = valor_brl * pct_fat
        dt_pos  = _add_days(close_dt, x_dias)

        if pct_ent > 0:
            linha("CREDITO", "ENTRADA", close_dt, val_ent)
            comissao(close_dt, val_ent, "ENTRADA")
        if pct_pos > 0:
            linha("CREDITO", f"PARCELA {int(x_dias)}d", dt_pos, val_pos)
            comissao(dt_pos, val_pos, "P2")
        if pct_fat > 0:
            linha("CREDITO", "FATURAMENTO", fat_dt, val_fat)
            comissao(fat_dt, val_fat, "FAT")

    # ── TIPO 4 — Livre ──────────────────────────────────────────────────────
    elif tipo == 4:
        import json as _json
        try:
            parcelas = _json.loads(cfg.get("parcelas_livres_json") or "[]")
        except Exception:
            parcelas = []
        for i, p in enumerate(parcelas):
            desc     = p.get("desc") or f"Parcela {i+1}"
            dias     = int(p.get("dias") or 0)
            ref_key  = p.get("ref", "fechamento")  # "fechamento" ou "faturamento"
            tipo_val = p.get("tipo_val", "pct")
            val_p    = float(p.get("valor") or 0)
            val      = (valor_brl * val_p / 100) if tipo_val == "pct" else val_p
            ref_dt   = fat_dt if ref_key == "faturamento" else close_dt
            dt       = _add_days(ref_dt, dias)
            if val > 0:
                linha("CREDITO", desc, dt, val)
                comissao(dt, val, desc)

    # ── TIPO 3 ──────────────────────────────────────────────────────────────
    elif tipo == 3:
        pct_pos    = _pct(cfg.get("pct_pos_x") or cfg.get("% Pós X dias (Tipo 2/3)"), 0.0)
        x_dias     = _n_int(cfg.get("x_dias") or cfg.get("X Dias (Tipo 2/3)"), 30)
        pct_fat    = _pct(cfg.get("pct_fat") or cfg.get("% Faturamento (Tipo 2/3)"), 0.0)
        pct_pos_f  = _pct(cfg.get("pct_pos_fat") or cfg.get("% Pós Faturamento (Tipo 3)"), 0.0)
        dias_pos_f = _n_int(cfg.get("dias_pos_fat") or cfg.get("Dias Pós Faturamento (Tipo 3)"), 30)

        val_ent   = valor_brl * pct_ent
        val_pos   = valor_brl * pct_pos
        val_fat   = valor_brl * pct_fat
        val_pos_f = valor_brl * pct_pos_f
        dt_pos   = _add_days(close_dt, x_dias)
        dt_pos_f = _add_days(fat_dt, dias_pos_f)

        if pct_ent > 0:
            linha("CREDITO", "ENTRADA", close_dt, val_ent)
            comissao(close_dt, val_ent, "ENTRADA")
        if pct_pos > 0:
            linha("CREDITO", f"PARCELA {int(x_dias)}d", dt_pos, val_pos)
            comissao(dt_pos, val_pos, "P2")
        if pct_fat > 0:
            linha("CREDITO", "FATURAMENTO", fat_dt, val_fat)
            comissao(fat_dt, val_fat, "FAT")
        if pct_pos_f > 0:
            linha("CREDITO", f"PÓS-FAT {int(dias_pos_f)}d", dt_pos_f, val_pos_f)
            comissao(dt_pos_f, val_pos_f, "PÓS-FAT")

    # ── Comissão Exportação ──────────────────────────────────────────────────
    if is_exp and total_com_export > 0 and fat_dt:
        dt_com_exp = _add_days(fat_dt, 30)
        linha("DEBITO", f"COMISSÃO {pct_com*100:.1f}% - TOTAL", dt_com_exp, total_com_export)

    # ── CUSTOS ──────────────────────────────────────────────────────────────
    ajuste_dias_custo = max(0, prazo_ent - PRAZO_BASE_CUSTOS)
    for dias_c, pct_c, desc_c in CUSTOS_PADRAO:
        val_c = valor_brl * pct_c
        if val_c > 0:
            dias_ajustados = dias_c + ajuste_dias_custo
            linha("DEBITO", f"{desc_c} ({int(pct_c*100)}%)",
                  _add_days(close_dt, dias_ajustados), val_c)

    # ── MATÉRIA PRIMA (customizado — opcional) ──────────────────────────────
    # Quando a referência é "fechamento", aplica o mesmo ajuste de prazo dos
    # CUSTOS_PADRAO: se prazo_ent > PRAZO_BASE_CUSTOS, o excedente é somado.
    import json as _json
    try:
        mp_parcelas = _json.loads(cfg.get("mp_json") or "[]")
    except Exception:
        mp_parcelas = []
    for i, p in enumerate(mp_parcelas):
        desc     = p.get("desc") or f"Matéria Prima {i+1}"
        dias     = int(p.get("dias") or 0)
        ref_key  = p.get("ref", "fechamento")   # "fechamento" ou "faturamento"
        tipo_val = p.get("tipo_val", "pct")      # "pct" ou "fixo"
        val_p    = float(p.get("valor") or 0)
        val      = (valor_brl * val_p / 100) if tipo_val == "pct" else val_p
        if ref_key == "faturamento" and fat_dt:
            # Referência = faturamento → sem ajuste de prazo (data já reflete entrega)
            ref_dt = fat_dt
            dt     = _add_days(ref_dt, dias)
        else:
            # Referência = fechamento → mesmo ajuste proporcional dos CUSTOS_PADRAO
            dt = _add_days(close_dt, dias + ajuste_dias_custo)
        if val > 0:
            linha("DEBITO", f"MP: {desc}", dt, val)

    # ── IMPOSTOS (Nacional) ──────────────────────────────────────────────────
    if not is_exp and fat_dt:
        icms_pct = _pct(cfg.get("pct_icms") or cfg.get("% ICMS"), IMPOSTOS_PADRAO[0][1])
        pis_pct  = _pct(cfg.get("pct_pis_cofins") or cfg.get("% PIS/ COFINS"), IMPOSTOS_PADRAO[1][1])
        icms_dia = _n_int(cfg.get("dias_icms") or cfg.get("Dias ICMS após fat."), IMPOSTOS_PADRAO[0][0])
        pis_dia  = _n_int(cfg.get("dias_pis_cofins") or cfg.get("Dias PIS/ COFINS"), IMPOSTOS_PADRAO[1][0])

        if icms_pct > 0:
            linha("DEBITO", "ICMS", _proximo_mes_dia(fat_dt, icms_dia),
                  valor_brl * icms_pct, imposto="SIM")
        if pis_pct > 0:
            linha("DEBITO", "PIS/COFINS", _proximo_mes_dia(fat_dt, pis_dia),
                  valor_brl * pis_pct, imposto="SIM")

    return rows


# ─── HELPERS INTERNOS ────────────────────────────────────────────────────────

def _parse_date(val):
    if not val or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d")
    except:
        return None


def _fmt_date(dt):
    return dt.strftime("%Y-%m-%d") if dt else ""


def _add_days(base, days):
    if not base:
        return None
    return base + timedelta(days=days)


def _proximo_mes_dia(dt, dia):
    if not dt:
        return None
    if dt.month == 12:
        return datetime(dt.year + 1, 1, dia)
    return datetime(dt.year, dt.month + 1, dia)


def _semana(dt):
    if not dt:
        return None
    return dt.isocalendar()[1]


def _pct(val, default=0.0):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    s = str(val).replace("%", "").replace(",", ".").strip()
    try:
        v = float(s)
        return v / 100 if v > 1 else v
    except:
        return default


def _n_int(val, default=0):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return int(float(str(val)))
    except:
        return default
