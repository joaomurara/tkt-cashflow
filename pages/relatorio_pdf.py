"""
Página Relatório PDF — One-pager executivo com indicadores e FUP Vendas.
Gera um PDF A4 retrato pronto para impressão ou envio.
"""

import io
import os
import sys
from datetime import date, timedelta

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db
import auth

# ── reportlab ────────────────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.platypus.flowables import KeepTogether
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Paleta de cores Tecnotok ──────────────────────────────────────────────────
AZUL_ESCURO  = colors.HexColor("#1F4E79")
AZUL_MEDIO   = colors.HexColor("#2E75B6")
AZUL_CLARO   = colors.HexColor("#D6E4F0")
VERDE        = colors.HexColor("#1a7c3e")
VERDE_CLARO  = colors.HexColor("#D5F5E3")
VERMELHO     = colors.HexColor("#c0392b")
CINZA_CLARO  = colors.HexColor("#F2F4F7")
CINZA_TEXTO  = colors.HexColor("#555555")
BRANCO       = colors.white

W, H = A4  # 595.27 x 841.89 pts


# ─────────────────────────────────────────────────────────────────────────────
# ESTILOS
# ─────────────────────────────────────────────────────────────────────────────
def _estilos():
    return {
        "titulo":    ParagraphStyle("titulo",    fontSize=18, textColor=AZUL_ESCURO,
                                    fontName="Helvetica-Bold", spaceAfter=2),
        "subtitulo": ParagraphStyle("subtitulo", fontSize=9,  textColor=CINZA_TEXTO,
                                    fontName="Helvetica",      spaceAfter=6),
        "secao":     ParagraphStyle("secao",     fontSize=9,  textColor=BRANCO,
                                    fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=2,
                                    leftIndent=4),
        "label":     ParagraphStyle("label",     fontSize=7.5, textColor=CINZA_TEXTO,
                                    fontName="Helvetica"),
        "valor":     ParagraphStyle("valor",     fontSize=11,  textColor=AZUL_ESCURO,
                                    fontName="Helvetica-Bold"),
        "valor_pos": ParagraphStyle("valor_pos", fontSize=11,  textColor=VERDE,
                                    fontName="Helvetica-Bold"),
        "valor_neg": ParagraphStyle("valor_neg", fontSize=11,  textColor=VERMELHO,
                                    fontName="Helvetica-Bold"),
        "celula":    ParagraphStyle("celula",    fontSize=7.5, textColor=AZUL_ESCURO,
                                    fontName="Helvetica", leading=10),
        "rodape":    ParagraphStyle("rodape",    fontSize=6.5, textColor=CINZA_TEXTO,
                                    fontName="Helvetica", alignment=TA_CENTER),
    }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _brl(v: float) -> str:
    return f"R$ {v:,.2f}"


def _bloco_secao(texto: str, estilos: dict):
    """Faixa colorida de cabeçalho de seção."""
    t = Table([[Paragraph(f"▌ {texto}", estilos["secao"])]],
              colWidths=[W - 36*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AZUL_MEDIO),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("ROUNDEDCORNERS", [3]),
    ]))
    return t


def _kpi_row(kpis: list, col_width: float, estilos: dict):
    """
    kpis: lista de (label, valor_str, positivo|negativo|None)
    Retorna uma Table de KPIs lado a lado.
    """
    n = len(kpis)
    cw = col_width / n

    header_row = []
    value_row  = []
    for label, valor, sentido in kpis:
        header_row.append(Paragraph(label, estilos["label"]))
        estilo = estilos["valor_pos"] if sentido == "pos" \
            else estilos["valor_neg"] if sentido == "neg" \
            else estilos["valor"]
        value_row.append(Paragraph(valor, estilo))

    t = Table([header_row, value_row], colWidths=[cw] * n)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CINZA_CLARO),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.5, colors.HexColor("#DDE3EC")),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t


def _tabela_dados(cabecalho: list, linhas: list, col_widths: list, estilos: dict,
                  zebra: bool = True):
    """Tabela de dados com cabeçalho azul e zebra opcional."""
    data = [cabecalho] + linhas
    t = Table(data, colWidths=col_widths, repeatRows=1)

    estilo = [
        ("BACKGROUND",   (0, 0), (-1, 0), AZUL_ESCURO),
        ("TEXTCOLOR",    (0, 0), (-1, 0), BRANCO),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 7),
        ("FONTSIZE",     (0, 1), (-1, -1), 7),
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.HexColor("#C5D3E0")),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]
    if zebra:
        for i in range(2, len(data), 2):
            estilo.append(("BACKGROUND", (0, i), (-1, i), AZUL_CLARO))

    t.setStyle(TableStyle(estilo))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# GERAÇÃO DO PDF
# ─────────────────────────────────────────────────────────────────────────────
def _gerar_pdf(usuario: str) -> bytes:
    buf = io.BytesIO()
    S = _estilos()
    hoje = date.today()

    # ── Dados ────────────────────────────────────────────────────────────────
    posicao       = db.get_posicao_consolidada()
    saldos        = db.listar_saldos_recentes()
    cambios_disp  = db.listar_cambios(status="DISPONIVEL")
    cfg_corte     = True  # padrão conservador

    # Fluxo 30 / 60 / 90 dias (sempre com ALTA, sem MEDIA — visão conservadora)
    def _fluxo(dias):
        dt_f = str(hoje + timedelta(days=dias))
        dados = db.fc_diario(str(hoje), dt_f, True, False,
                             erp_corte_status=cfg_corte, inc_fci=True, inc_fcf=True)
        fluxo = sum(r["valor_final"] or 0 for r in dados)
        return posicao["total"] + fluxo

    pos_30  = _fluxo(30)
    pos_60  = _fluxo(60)
    pos_90  = _fluxo(90)

    # Recebíveis e obrigações (ano corrente)
    dt_fim_ano = str(date(hoje.year, 12, 31))
    dados_all  = db.fc_diario(str(hoje), dt_fim_ano, True, False,
                              erp_corte_status=cfg_corte, inc_fci=True, inc_fcf=True)
    total_rec  = sum(r["valor_final"] for r in dados_all if (r["valor_final"] or 0) > 0)
    total_obr  = sum(r["valor_final"] for r in dados_all if (r["valor_final"] or 0) < 0)
    total_imp  = sum(r["valor_final"] for r in dados_all
                     if r.get("imposto") == "SIM" and (r["valor_final"] or 0) < 0)

    # FUP Vendas — pipeline
    dt_ini_fup  = str(hoje)
    dt_fim_fup  = str(date(hoje.year, 12, 31))
    fup_alta    = db.listar_fup(dt_ini=dt_ini_fup, dt_fim=dt_fim_fup, prob="ALTA")
    fup_media   = db.listar_fup(dt_ini=dt_ini_fup, dt_fim=dt_fim_fup, prob="MEDIA")
    fup_baixa   = db.listar_fup(dt_ini=dt_ini_fup, dt_fim=dt_fim_fup, prob="BAIXA")

    def _sum_fup(linhas):
        return sum(r.get("valor_brl") or r.get("valor") or 0 for r in linhas)

    val_alta   = _sum_fup(fup_alta)
    val_media  = _sum_fup(fup_media)
    val_baixa  = _sum_fup(fup_baixa)

    # Top negócios ALTA (agrupa por deal_id / razao_social)
    from collections import defaultdict
    deal_totais = defaultdict(lambda: {"razao": "", "valor": 0.0, "prob": "", "parcelas": 0})
    for linha in fup_alta + fup_media:
        did = linha.get("deal_id", "")
        deal_totais[did]["razao"]    = linha.get("razao_social") or linha.get("descricao") or did
        deal_totais[did]["valor"]   += linha.get("valor_brl") or linha.get("valor") or 0
        deal_totais[did]["prob"]     = linha.get("probabilidade", "")
        deal_totais[did]["parcelas"] += 1

    top_deals = sorted(deal_totais.values(), key=lambda x: -x["valor"])[:8]

    # Câmbios disponíveis — top 6
    top_cambios = cambios_disp[:6]

    # ── Layout ───────────────────────────────────────────────────────────────
    MARGEM   = 14 * mm
    LARGURA  = W - 2 * MARGEM
    ALTURA   = H - 2 * MARGEM

    story = []

    # ── CABEÇALHO ─────────────────────────────────────────────────────────
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logo_tecnotok.png")
    if os.path.exists(logo_path):
        from reportlab.platypus import Image as RLImage
        logo = RLImage(logo_path, width=28 * mm, height=12 * mm, kind="proportional")
        cab_data = [[logo,
                     Paragraph("TKT Cash Flow", S["titulo"]),
                     Paragraph(f"Relatório Executivo<br/>{hoje.strftime('%d/%m/%Y')}",
                               ParagraphStyle("d", fontSize=8, textColor=CINZA_TEXTO,
                                              fontName="Helvetica", alignment=TA_RIGHT))]]
        cab_cw = [30 * mm, LARGURA - 70 * mm, 40 * mm]
    else:
        cab_data = [[Paragraph("TKT Cash Flow", S["titulo"]),
                     Paragraph(f"Relatório Executivo<br/>{hoje.strftime('%d/%m/%Y')}",
                               ParagraphStyle("d", fontSize=8, textColor=CINZA_TEXTO,
                                              fontName="Helvetica", alignment=TA_RIGHT))]]
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
    story.append(HRFlowable(width=LARGURA, thickness=1.5, color=AZUL_MEDIO, spaceAfter=6))

    # ══════════════════════════════════════════════════════════════════════════
    # COLUNA ESQUERDA (Indicadores) | COLUNA DIREITA (FUP Vendas)
    # ══════════════════════════════════════════════════════════════════════════
    COL_L = LARGURA * 0.52
    COL_R = LARGURA * 0.48 - 4 * mm
    GAP   = 4 * mm

    # ── COLUNA ESQUERDA ───────────────────────────────────────────────────
    left_story = []

    # Seção: Posição Consolidada
    left_story.append(_bloco_secao("POSIÇÃO CONSOLIDADA", S))
    left_story.append(Spacer(1, 4))
    left_story.append(_kpi_row([
        ("Caixa BRL",              _brl(posicao["total_bancos"]),      None),
        ("Câmbios a Receber",      _brl(posicao["total_cambios_brl"]), None),
        ("Posição Consolidada",    _brl(posicao["total"]),             "pos" if posicao["total"] >= 0 else "neg"),
    ], COL_L, S))

    left_story.append(Spacer(1, 8))

    # Seção: Projeção de Caixa
    left_story.append(_bloco_secao("PROJEÇÃO DE CAIXA (base: posição consolidada)", S))
    left_story.append(Spacer(1, 4))
    left_story.append(_kpi_row([
        ("30 dias",  _brl(pos_30), "pos" if pos_30 >= 0 else "neg"),
        ("60 dias",  _brl(pos_60), "pos" if pos_60 >= 0 else "neg"),
        ("90 dias",  _brl(pos_90), "pos" if pos_90 >= 0 else "neg"),
    ], COL_L, S))

    left_story.append(Spacer(1, 8))

    # Seção: Recebíveis e Obrigações
    left_story.append(_bloco_secao(f"RECEBÍVEIS E OBRIGAÇÕES — {hoje.year}", S))
    left_story.append(Spacer(1, 4))
    left_story.append(_kpi_row([
        ("Recebíveis",    _brl(total_rec),         "pos"),
        ("Obrigações",    _brl(abs(total_obr)),     "neg"),
        ("Saldo Projetado", _brl(posicao["total"] + total_rec + total_obr),
         "pos" if (posicao["total"] + total_rec + total_obr) >= 0 else "neg"),
        ("Impostos",      _brl(abs(total_imp)),     "neg"),
    ], COL_L, S))

    left_story.append(Spacer(1, 8))

    # Seção: Saldos Bancários
    left_story.append(_bloco_secao("SALDOS BANCÁRIOS", S))
    left_story.append(Spacer(1, 4))
    if saldos:
        linhas_sb = [[r["banco"], r.get("tipo") or "Conta Corrente",
                      _brl(r["saldo"] or 0), r["data"]] for r in saldos]
        left_story.append(_tabela_dados(
            ["Banco / Conta", "Tipo", "Saldo", "Data"],
            linhas_sb,
            [COL_L * 0.36, COL_L * 0.26, COL_L * 0.24, COL_L * 0.14],
            S,
        ))
    else:
        left_story.append(Paragraph("Nenhum saldo cadastrado.", S["label"]))

    left_story.append(Spacer(1, 8))

    # Seção: Câmbios Disponíveis
    left_story.append(_bloco_secao("CÂMBIOS DISPONÍVEIS", S))
    left_story.append(Spacer(1, 4))
    if cambios_disp:
        ptax = posicao.get("ptax_map", {})
        linhas_cx = []
        for c in top_cambios:
            taxa = ptax.get(c["moeda"])
            brl  = f"{c['valor_me']:,.0f} {c['moeda']}"
            brl_proj = _brl((c["valor_me"] or 0) * taxa) if taxa else "—"
            linhas_cx.append([
                c.get("descricao") or c.get("razao_social") or "—",
                brl,
                brl_proj,
                c.get("data_entrada") or "—",
            ])
        left_story.append(_tabela_dados(
            ["Descrição", "Valor ME", "BRL Proj.", "Entrada"],
            linhas_cx,
            [COL_L * 0.35, COL_L * 0.22, COL_L * 0.25, COL_L * 0.18],
            S,
        ))
        if len(cambios_disp) > 6:
            left_story.append(Paragraph(
                f"+ {len(cambios_disp) - 6} posição(ões) não exibida(s).", S["label"]))
    else:
        left_story.append(Paragraph("Nenhum câmbio disponível.", S["label"]))

    # ── COLUNA DIREITA ────────────────────────────────────────────────────
    right_story = []

    # Seção: Pipeline FUP
    right_story.append(_bloco_secao("FUP VENDAS — PIPELINE", S))
    right_story.append(Spacer(1, 4))
    right_story.append(_kpi_row([
        ("ALTA",  _brl(val_alta),  "pos"),
        ("MEDIA", _brl(val_media), None),
        ("BAIXA", _brl(val_baixa), None),
    ], COL_R, S))
    right_story.append(Spacer(1, 4))

    total_fup = val_alta + val_media + val_baixa
    n_deals   = len({r.get("deal_id") for r in fup_alta + fup_media + fup_baixa})
    right_story.append(_kpi_row([
        ("Total no Pipeline", _brl(total_fup), "pos" if total_fup > 0 else None),
        ("Negócios ativos",   str(n_deals),    None),
    ], COL_R, S))

    right_story.append(Spacer(1, 8))

    # Seção: Top negócios
    right_story.append(_bloco_secao("PRINCIPAIS NEGÓCIOS (ALTA + MEDIA)", S))
    right_story.append(Spacer(1, 4))
    if top_deals:
        linhas_deal = []
        for d in top_deals:
            prob_badge = "●" if d["prob"] == "ALTA" else "○"
            linhas_deal.append([
                prob_badge + " " + (d["razao"][:28] + "…" if len(d["razao"]) > 29 else d["razao"]),
                d["prob"],
                _brl(d["valor"]),
                str(d["parcelas"]),
            ])
        right_story.append(_tabela_dados(
            ["Negócio", "Prob.", "Valor BRL", "Parc."],
            linhas_deal,
            [COL_R * 0.48, COL_R * 0.14, COL_R * 0.28, COL_R * 0.10],
            S,
        ))
    else:
        right_story.append(Paragraph("Nenhum negócio ALTA ou MEDIA no período.", S["label"]))

    right_story.append(Spacer(1, 8))

    # Seção: FUP por mês
    right_story.append(_bloco_secao("RECEBIMENTOS ESPERADOS POR MÊS", S))
    right_story.append(Spacer(1, 4))

    from collections import defaultdict as _dd
    por_mes: dict = _dd(float)
    for linha in fup_alta + fup_media:
        venc = str(linha.get("vencimento") or "")[:7]  # YYYY-MM
        por_mes[venc] += linha.get("valor_brl") or linha.get("valor") or 0

    if por_mes:
        meses_ord = sorted(por_mes.keys())[:6]
        linhas_mes = [[m, _brl(por_mes[m])] for m in meses_ord]
        right_story.append(_tabela_dados(
            ["Mês", "Valor Esperado (ALTA+MEDIA)"],
            linhas_mes,
            [COL_R * 0.38, COL_R * 0.62],
            S,
        ))
    else:
        right_story.append(Paragraph("Sem dados de vencimento no FUP.", S["label"]))

    # ── Monta a tabela de duas colunas ────────────────────────────────────
    from reportlab.platypus import KeepInFrame

    def _frame_content(content, width, height):
        """Empacota uma lista de flowables em KeepInFrame."""
        return KeepInFrame(width, height, content, mode="shrink")

    col_height = ALTURA - 60  # reserva espaço para cabeçalho e rodapé

    two_col = Table(
        [[_frame_content(left_story, COL_L, col_height),
          _frame_content(right_story, COL_R, col_height)]],
        colWidths=[COL_L + GAP, COL_R],
    )
    two_col.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LINEAFTER",     (0, 0), (0, -1), 0.5, colors.HexColor("#C5D3E0")),
    ]))
    story.append(two_col)

    # ── RODAPÉ ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width=LARGURA, thickness=0.5, color=AZUL_CLARO))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        f"Gerado em {hoje.strftime('%d/%m/%Y')} por {usuario} · "
        f"TKT Cash Flow · Tecnotok © {hoje.year} · "
        "Documento confidencial — uso interno",
        S["rodape"]
    ))

    # ── Build ─────────────────────────────────────────────────────────────
    def _on_page(canvas, doc):
        canvas.saveState()
        # borda sutil
        canvas.setStrokeColor(colors.HexColor("#C5D3E0"))
        canvas.setLineWidth(0.5)
        canvas.rect(MARGEM - 4, MARGEM - 4, W - 2 * MARGEM + 8, H - 2 * MARGEM + 8)
        canvas.restoreState()

    frame  = Frame(MARGEM, MARGEM, LARGURA, ALTURA, leftPadding=0, rightPadding=0,
                   topPadding=0, bottomPadding=0)
    tmpl   = PageTemplate(id="main", frames=[frame], onPage=_on_page)
    doc    = BaseDocTemplate(buf, pagesize=A4, pageTemplates=[tmpl],
                             leftMargin=MARGEM, rightMargin=MARGEM,
                             topMargin=MARGEM, bottomMargin=MARGEM)
    doc.build(story)

    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────────────────────────────────────
def render():
    st.title("📄 Relatório Executivo — PDF")
    st.markdown(
        "Gera um **one-pager A4** com os principais indicadores de caixa "
        "e o pipeline de vendas (FUP). Pronto para impressão ou envio por e-mail."
    )

    hoje = date.today()
    usuario = auth.get_display_name() or "Sistema"

    with st.expander("ℹ️ O que é incluído no relatório", expanded=False):
        st.markdown("""
        **Lado esquerdo — Indicadores de Caixa:**
        - Posição consolidada: caixa BRL + câmbios a receber (PTAX)
        - Projeção 30, 60 e 90 dias (cenário ALTA)
        - Recebíveis, obrigações e impostos do ano
        - Saldos bancários por conta
        - Câmbios disponíveis com BRL projetado

        **Lado direito — FUP Vendas:**
        - Pipeline total por probabilidade (ALTA / MEDIA / BAIXA)
        - Principais negócios ALTA + MEDIA com valor e parcelas
        - Recebimentos esperados mês a mês (ALTA + MEDIA)
        """)

    col1, col2 = st.columns([2, 3])
    with col1:
        if st.button("🔄 Pré-visualizar dados", key="btn_preview"):
            st.session_state["rel_preview"] = True

    if st.session_state.get("rel_preview"):
        posicao = db.get_posicao_consolidada()
        fup_alta  = db.listar_fup(dt_ini=str(hoje), dt_fim=str(date(hoje.year, 12, 31)), prob="ALTA")
        fup_media = db.listar_fup(dt_ini=str(hoje), dt_fim=str(date(hoje.year, 12, 31)), prob="MEDIA")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Posição Consolidada", f"R$ {posicao['total']:,.2f}")
        col_b.metric("FUP ALTA",  f"R$ {sum(r.get('valor_brl') or r.get('valor') or 0 for r in fup_alta):,.2f}")
        col_c.metric("FUP MEDIA", f"R$ {sum(r.get('valor_brl') or r.get('valor') or 0 for r in fup_media):,.2f}")

    st.markdown("---")

    if st.button("📥 Gerar e baixar PDF", type="primary", key="btn_gerar_pdf"):
        with st.spinner("Gerando PDF..."):
            try:
                pdf_bytes = _gerar_pdf(usuario)
                nome_arquivo = f"TKT_Relatorio_{hoje.strftime('%Y%m%d')}.pdf"
                st.download_button(
                    label="⬇️ Clique aqui para baixar o PDF",
                    data=pdf_bytes,
                    file_name=nome_arquivo,
                    mime="application/pdf",
                    type="primary",
                )
                st.success(f"PDF gerado: **{nome_arquivo}**")
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {e}")
                import traceback
                st.code(traceback.format_exc())
