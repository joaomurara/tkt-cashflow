"""
Página Relatório PDF — One-pager executivo com indicadores e FUP Vendas.
"""

import io
import os
import sys
from datetime import date, timedelta
from collections import defaultdict

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import auth

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepInFrame,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Paleta ───────────────────────────────────────────────────────────────────
AZUL_ESC  = colors.HexColor("#1F4E79")
AZUL_MED  = colors.HexColor("#2E75B6")
AZUL_CLR  = colors.HexColor("#D6E4F0")
VERDE     = colors.HexColor("#1a7c3e")
VERMELHO  = colors.HexColor("#c0392b")
CINZA     = colors.HexColor("#F2F4F7")
CINZA_TXT = colors.HexColor("#666666")
BRANCO    = colors.white

W, H = A4
MARGEM  = 12 * mm
LARGURA = W - 2 * MARGEM   # largura útil
COL_L   = LARGURA * 0.52   # coluna esquerda
COL_R   = LARGURA * 0.48   # coluna direita
GAP     = 3 * mm


# ─────────────────────────────────────────────────────────────────────────────
# ESTILOS
# ─────────────────────────────────────────────────────────────────────────────
def _S():
    return {
        "titulo":  ParagraphStyle("tit",  fontSize=17, textColor=AZUL_ESC,
                                  fontName="Helvetica-Bold", leading=20),
        "sub":     ParagraphStyle("sub",  fontSize=8,  textColor=CINZA_TXT,
                                  fontName="Helvetica", alignment=TA_RIGHT),
        "sec":     ParagraphStyle("sec",  fontSize=7.5, textColor=BRANCO,
                                  fontName="Helvetica-Bold", leading=10),
        "lbl":     ParagraphStyle("lbl",  fontSize=6.5, textColor=CINZA_TXT,
                                  fontName="Helvetica", leading=8),
        "val":     ParagraphStyle("val",  fontSize=9,  textColor=AZUL_ESC,
                                  fontName="Helvetica-Bold", leading=11),
        "val_p":   ParagraphStyle("valp", fontSize=9,  textColor=VERDE,
                                  fontName="Helvetica-Bold", leading=11),
        "val_n":   ParagraphStyle("valn", fontSize=9,  textColor=VERMELHO,
                                  fontName="Helvetica-Bold", leading=11),
        "cel":     ParagraphStyle("cel",  fontSize=6.5, textColor=AZUL_ESC,
                                  fontName="Helvetica", leading=8),
        "rod":     ParagraphStyle("rod",  fontSize=6,  textColor=CINZA_TXT,
                                  fontName="Helvetica", alignment=TA_CENTER),
    }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _brl(v: float) -> str:
    return f"R$ {v:,.2f}"


def _brl_k(v: float) -> str:
    """Formato compacto para valores grandes em KPIs (evita quebra de linha)."""
    av = abs(v)
    sinal = "-" if v < 0 else ""
    if av >= 1_000_000:
        return f"{sinal}R$ {av/1_000_000:,.2f}M"
    if av >= 1_000:
        return f"{sinal}R$ {av/1_000:,.1f}K"
    return f"{sinal}R$ {av:,.2f}"


def _bloco_sec(texto: str, S: dict, largura: float) -> Table:
    """Faixa de título de seção — usa a largura da coluna correta."""
    t = Table([[Paragraph(texto.upper(), S["sec"])]], colWidths=[largura])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL_MED),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _kpi(kpis: list, S: dict, largura: float) -> Table:
    """
    kpis = [(label, valor, cor)]  cor: 'p'=verde, 'n'=vermelho, None=azul
    """
    n  = len(kpis)
    cw = largura / n
    row_lbl = []
    row_val = []
    for label, valor, cor in kpis:
        row_lbl.append(Paragraph(label, S["lbl"]))
        st_val = S["val_p"] if cor == "p" else S["val_n"] if cor == "n" else S["val"]
        row_val.append(Paragraph(valor, st_val))

    t = Table([row_lbl, row_val], colWidths=[cw] * n)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CINZA),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.4, colors.HexColor("#C8D8E8")),
    ]))
    return t


def _tabela(cab: list, rows: list, cws: list, S: dict, zebra=True) -> Table:
    data = [cab] + rows
    t = Table(data, colWidths=cws, repeatRows=1)
    estilo = [
        ("BACKGROUND",    (0, 0), (-1, 0),  AZUL_ESC),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  BRANCO),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 6.5),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#C5D3E0")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]
    if zebra:
        for i in range(2, len(data), 2):
            estilo.append(("BACKGROUND", (0, i), (-1, i), AZUL_CLR))
    t.setStyle(TableStyle(estilo))
    return t


def _sp(h=4) -> Spacer:
    return Spacer(1, h)


# ─────────────────────────────────────────────────────────────────────────────
# CONTEÚDO DAS COLUNAS
# ─────────────────────────────────────────────────────────────────────────────
def _col_esquerda(S, posicao, saldos, cambios_disp, pos_30, pos_60, pos_90,
                  total_rec, total_obr, total_imp) -> list:
    W_L = COL_L - GAP / 2
    story = []

    # ── Posição consolidada ───────────────────────────────────────────────
    story.append(_bloco_sec("Posição Consolidada", S, W_L))
    story.append(_sp(3))
    story.append(_kpi([
        ("Caixa BRL",           _brl_k(posicao["total_bancos"]),      None),
        ("Câmbios a Receber",   _brl_k(posicao["total_cambios_brl"]), None),
        ("Posição Consolidada", _brl_k(posicao["total"]),
         "p" if posicao["total"] >= 0 else "n"),
    ], S, W_L))
    story.append(_sp(6))

    # ── Projeção 30 / 60 / 90 dias ───────────────────────────────────────
    story.append(_bloco_sec("Projeção de Caixa — base: posição consolidada", S, W_L))
    story.append(_sp(3))
    story.append(_kpi([
        ("30 dias", _brl_k(pos_30), "p" if pos_30 >= 0 else "n"),
        ("60 dias", _brl_k(pos_60), "p" if pos_60 >= 0 else "n"),
        ("90 dias", _brl_k(pos_90), "p" if pos_90 >= 0 else "n"),
    ], S, W_L))
    story.append(_sp(6))

    # ── Recebíveis e obrigações ───────────────────────────────────────────
    story.append(_bloco_sec(f"Recebíveis e Obrigações — {date.today().year}", S, W_L))
    story.append(_sp(3))
    saldo_proj = posicao["total"] + total_rec + total_obr
    story.append(_kpi([
        ("Recebíveis",      _brl_k(total_rec),       "p"),
        ("Obrigações",      _brl_k(abs(total_obr)),   "n"),
        ("Saldo Projetado", _brl_k(saldo_proj),
         "p" if saldo_proj >= 0 else "n"),
        ("Impostos",        _brl_k(abs(total_imp)),   "n"),
    ], S, W_L))
    story.append(_sp(6))

    # ── Saldos bancários ──────────────────────────────────────────────────
    story.append(_bloco_sec("Saldos Bancários", S, W_L))
    story.append(_sp(3))
    if saldos:
        rows_sb = [[r["banco"],
                    r.get("tipo") or "C/C",
                    _brl(r["saldo"] or 0),
                    str(r["data"])] for r in saldos]
        story.append(_tabela(
            ["Banco / Conta", "Tipo", "Saldo", "Data"],
            rows_sb,
            [W_L * 0.37, W_L * 0.22, W_L * 0.24, W_L * 0.17],
            S,
        ))
    else:
        story.append(Paragraph("Nenhum saldo cadastrado.", S["lbl"]))
    story.append(_sp(6))

    # ── Câmbios disponíveis ───────────────────────────────────────────────
    story.append(_bloco_sec("Câmbios Disponíveis", S, W_L))
    story.append(_sp(3))
    if cambios_disp:
        ptax = posicao.get("ptax_map", {})
        rows_cx = []
        for c in cambios_disp[:7]:
            taxa = ptax.get(c["moeda"])
            brl_proj = _brl((c["valor_me"] or 0) * taxa) if taxa else "—"
            rows_cx.append([
                (c.get("descricao") or c.get("razao_social") or "—")[:22],
                f"{c['valor_me']:,.0f} {c['moeda']}",
                brl_proj,
                str(c.get("data_entrada") or "—"),
            ])
        story.append(_tabela(
            ["Descrição", "Valor ME", "BRL Proj.", "Entrada"],
            rows_cx,
            [W_L * 0.34, W_L * 0.22, W_L * 0.26, W_L * 0.18],
            S,
        ))
        if len(cambios_disp) > 7:
            story.append(Paragraph(
                f"+ {len(cambios_disp) - 7} posição(ões) não exibida(s).", S["lbl"]))
    else:
        story.append(Paragraph("Nenhum câmbio disponível.", S["lbl"]))

    return story


def _col_direita(S, val_alta, val_media, val_baixa, total_fup, n_deals,
                 top_deals, por_mes) -> list:
    W_R = COL_R - GAP / 2
    story = []

    # ── Pipeline FUP ─────────────────────────────────────────────────────
    story.append(_bloco_sec("FUP Vendas — Pipeline", S, W_R))
    story.append(_sp(3))
    story.append(_kpi([
        ("ALTA",  _brl_k(val_alta),  "p"),
        ("MEDIA", _brl_k(val_media), None),
        ("BAIXA", _brl_k(val_baixa), None),
    ], S, W_R))
    story.append(_sp(3))
    story.append(_kpi([
        ("Total no Pipeline", _brl_k(total_fup),
         "p" if total_fup > 0 else None),
        ("Negócios ativos", str(n_deals), None),
    ], S, W_R))
    story.append(_sp(6))

    # ── Top negócios ──────────────────────────────────────────────────────
    story.append(_bloco_sec("Principais Negócios (ALTA + MEDIA)", S, W_R))
    story.append(_sp(3))
    if top_deals:
        rows_deal = []
        for d in top_deals:
            nome = d["razao"]
            if len(nome) > 26:
                nome = nome[:25] + "…"
            rows_deal.append([
                nome,
                d["prob"],
                _brl(d["valor"]),
                str(d["parcelas"]),
            ])
        story.append(_tabela(
            ["Negócio", "Prob.", "Valor BRL", "Parc."],
            rows_deal,
            [W_R * 0.44, W_R * 0.13, W_R * 0.33, W_R * 0.10],
            S,
        ))
    else:
        story.append(Paragraph("Nenhum negócio ALTA ou MEDIA.", S["lbl"]))
    story.append(_sp(6))

    # ── Recebimentos por mês ──────────────────────────────────────────────
    story.append(_bloco_sec("Recebimentos Esperados por Mês (ALTA + MEDIA)", S, W_R))
    story.append(_sp(3))
    if por_mes:
        meses = sorted(por_mes.keys())[:8]
        rows_mes = [[m, _brl(por_mes[m])] for m in meses]
        story.append(_tabela(
            ["Mês", "Valor Esperado"],
            rows_mes,
            [W_R * 0.38, W_R * 0.62],
            S,
        ))
    else:
        story.append(Paragraph("Sem dados de vencimento no FUP.", S["lbl"]))

    return story


# ─────────────────────────────────────────────────────────────────────────────
# GERAÇÃO DO PDF
# ─────────────────────────────────────────────────────────────────────────────
def _gerar_pdf(usuario: str) -> bytes:
    buf = io.BytesIO()
    S   = _S()
    hoje = date.today()

    # ── Dados ────────────────────────────────────────────────────────────
    posicao      = db.get_posicao_consolidada()
    saldos       = db.listar_saldos_recentes()
    cambios_disp = db.listar_cambios(status="DISPONIVEL")
    cfg_corte    = True

    def _fluxo(dias):
        dt_f  = str(hoje + timedelta(days=dias))
        dados = db.fc_diario(str(hoje), dt_f, True, False,
                             erp_corte_status=cfg_corte, inc_fci=True, inc_fcf=True)
        return posicao["total"] + sum(r["valor_final"] or 0 for r in dados)

    pos_30 = _fluxo(30)
    pos_60 = _fluxo(60)
    pos_90 = _fluxo(90)

    dt_fim_ano = str(date(hoje.year, 12, 31))
    dados_all  = db.fc_diario(str(hoje), dt_fim_ano, True, False,
                              erp_corte_status=cfg_corte, inc_fci=True, inc_fcf=True)
    total_rec = sum(r["valor_final"] for r in dados_all if (r["valor_final"] or 0) > 0)
    total_obr = sum(r["valor_final"] for r in dados_all if (r["valor_final"] or 0) < 0)
    total_imp = sum(r["valor_final"] for r in dados_all
                    if r.get("imposto") == "SIM" and (r["valor_final"] or 0) < 0)

    dt_ini_fup = str(hoje)
    fup_alta   = db.listar_fup(dt_ini=dt_ini_fup, dt_fim=dt_fim_ano, prob="ALTA")
    fup_media  = db.listar_fup(dt_ini=dt_ini_fup, dt_fim=dt_fim_ano, prob="MEDIA")
    fup_baixa  = db.listar_fup(dt_ini=dt_ini_fup, dt_fim=dt_fim_ano, prob="BAIXA")

    def _sum_fup(linhas):
        return sum(r.get("valor_brl") or r.get("valor") or 0 for r in linhas)

    val_alta  = _sum_fup(fup_alta)
    val_media = _sum_fup(fup_media)
    val_baixa = _sum_fup(fup_baixa)
    total_fup = val_alta + val_media + val_baixa

    deal_map = defaultdict(lambda: {"razao": "", "valor": 0.0, "prob": "", "parcelas": 0})
    for linha in fup_alta + fup_media:
        did = linha.get("deal_id", "")
        deal_map[did]["razao"]     = linha.get("razao_social") or linha.get("descricao") or did
        deal_map[did]["valor"]    += linha.get("valor_brl") or linha.get("valor") or 0
        deal_map[did]["prob"]      = linha.get("probabilidade", "")
        deal_map[did]["parcelas"] += 1

    top_deals = sorted(deal_map.values(), key=lambda x: -x["valor"])[:8]
    n_deals   = len({r.get("deal_id") for r in fup_alta + fup_media + fup_baixa})

    por_mes: dict = defaultdict(float)
    for linha in fup_alta + fup_media:
        venc = str(linha.get("vencimento") or "")[:7]
        por_mes[venc] += linha.get("valor_brl") or linha.get("valor") or 0

    # ── Monta o documento ────────────────────────────────────────────────
    ALTURA_UTIL = H - 2 * MARGEM

    def _on_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#BFD0E0"))
        canvas.setLineWidth(0.5)
        canvas.rect(MARGEM - 3, MARGEM - 3,
                    W - 2 * MARGEM + 6, H - 2 * MARGEM + 6)
        canvas.restoreState()

    frame = Frame(MARGEM, MARGEM, LARGURA, ALTURA_UTIL,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    tmpl  = PageTemplate(id="main", frames=[frame], onPage=_on_page)
    doc   = BaseDocTemplate(buf, pagesize=A4, pageTemplates=[tmpl],
                            leftMargin=MARGEM, rightMargin=MARGEM,
                            topMargin=MARGEM,  bottomMargin=MARGEM)

    story = []

    # ── CABEÇALHO ────────────────────────────────────────────────────────
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logo_tecnotok.png")
    if os.path.exists(logo_path):
        from reportlab.platypus import Image as RLImage
        logo = RLImage(logo_path, width=26 * mm, height=11 * mm, kind="proportional")
        cab_data = [[logo,
                     Paragraph("TKT Cash Flow", S["titulo"]),
                     Paragraph(
                         f"Relatório Executivo<br/>{hoje.strftime('%d/%m/%Y')}",
                         S["sub"])]]
        cab_cw = [28 * mm, LARGURA - 75 * mm, 47 * mm]
    else:
        cab_data = [[Paragraph("TKT Cash Flow", S["titulo"]),
                     Paragraph(
                         f"Relatório Executivo<br/>{hoje.strftime('%d/%m/%Y')}",
                         S["sub"])]]
        cab_cw = [LARGURA - 50 * mm, 50 * mm]

    cab_t = Table(cab_data, colWidths=cab_cw)
    cab_t.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(cab_t)
    story.append(HRFlowable(width=LARGURA, thickness=1.5,
                             color=AZUL_MED, spaceAfter=5))

    # ── CORPO: duas colunas ───────────────────────────────────────────────
    # Altura disponível = total - cabeçalho (~22pt) - hr (~7pt) - rodapé (~14pt)
    ALTURA_COL = ALTURA_UTIL - 44

    left  = _col_esquerda(S, posicao, saldos, cambios_disp,
                          pos_30, pos_60, pos_90,
                          total_rec, total_obr, total_imp)
    right = _col_direita(S, val_alta, val_media, val_baixa,
                         total_fup, n_deals, top_deals, por_mes)

    corpo = Table(
        [[KeepInFrame(COL_L - GAP / 2, ALTURA_COL, left,  mode="shrink"),
          KeepInFrame(COL_R - GAP / 2, ALTURA_COL, right, mode="shrink")]],
        colWidths=[COL_L, COL_R],
    )
    corpo.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LINEAFTER",     (0, 0), (0, -1),  0.5, colors.HexColor("#C5D3E0")),
        ("RIGHTPADDING",  (0, 0), (0, -1),  int(GAP)),
        ("LEFTPADDING",   (1, 0), (1, -1),  int(GAP)),
    ]))
    story.append(corpo)

    # ── RODAPÉ ───────────────────────────────────────────────────────────
    story.append(HRFlowable(width=LARGURA, thickness=0.4,
                             color=AZUL_CLR, spaceBefore=4, spaceAfter=2))
    story.append(Paragraph(
        f"Gerado em {hoje.strftime('%d/%m/%Y')} por {usuario}  ·  "
        f"TKT Cash Flow  ·  Tecnotok © {hoje.year}  ·  "
        "Documento confidencial — uso interno",
        S["rod"],
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# RENDER (página Streamlit)
# ─────────────────────────────────────────────────────────────────────────────
def render():
    st.title("📄 Relatório Executivo — PDF")
    st.markdown(
        "Gera um **one-pager A4** com os principais indicadores de caixa "
        "e o pipeline de vendas (FUP). Pronto para impressão ou envio por e-mail."
    )

    hoje    = date.today()
    usuario = auth.get_display_name() or "Sistema"

    with st.expander("ℹ️ Conteúdo do relatório", expanded=False):
        st.markdown("""
        **Coluna esquerda — Indicadores de Caixa**
        - Posição consolidada: caixa BRL + câmbios a receber (PTAX)
        - Projeção 30, 60 e 90 dias (cenário ALTA)
        - Recebíveis, obrigações e impostos do ano
        - Saldos bancários por conta
        - Câmbios disponíveis com BRL projetado

        **Coluna direita — FUP Vendas**
        - Pipeline total por probabilidade (ALTA / MEDIA / BAIXA)
        - Top 8 negócios ALTA + MEDIA com valor
        - Recebimentos esperados mês a mês
        """)

    if st.button("📥 Gerar e baixar PDF", type="primary", key="btn_gerar_pdf"):
        with st.spinner("Buscando dados e gerando PDF..."):
            try:
                pdf_bytes    = _gerar_pdf(usuario)
                nome_arquivo = f"TKT_Relatorio_{hoje.strftime('%Y%m%d')}.pdf"
                st.download_button(
                    label="⬇️ Clique aqui para baixar o PDF",
                    data=pdf_bytes,
                    file_name=nome_arquivo,
                    mime="application/pdf",
                    type="primary",
                )
                st.success(f"✅ PDF gerado: **{nome_arquivo}**")
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {e}")
                import traceback
                st.code(traceback.format_exc())
