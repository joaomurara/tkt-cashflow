"""
Página Relatório PDF — One-pager executivo com indicadores e FUP Vendas.
Usa canvas com posicionamento absoluto para layout 100% previsível.
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
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.pdfgen import canvas as rl_canvas
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

W_PG, H_PG = A4
MARG   = 12 * mm
LARG   = W_PG - 2 * MARG          # largura útil total
COL_L  = LARG * 0.52              # coluna esquerda
COL_R  = LARG * 0.48              # coluna direita
SEP    = 4 * mm                   # espaço entre colunas


# ─────────────────────────────────────────────────────────────────────────────
# ESTILOS DE PARÁGRAFO
# ─────────────────────────────────────────────────────────────────────────────
def _ps(name, size, color, bold=False, align=TA_LEFT, leading=None):
    return ParagraphStyle(
        name,
        fontSize=size,
        textColor=color,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        alignment=align,
        leading=leading or size * 1.3,
    )

S_SEC  = _ps("sec",  7.5, BRANCO,    bold=True)
S_LBL  = _ps("lbl",  6.5, CINZA_TXT)
S_VAL  = _ps("val",  9.0, AZUL_ESC,  bold=True)
S_VALP = _ps("valp", 9.0, VERDE,     bold=True)
S_VALN = _ps("valn", 9.0, VERMELHO,  bold=True)
S_CEL  = _ps("cel",  6.5, AZUL_ESC)
S_ROD  = _ps("rod",  6.0, CINZA_TXT, align=TA_CENTER)


# ─────────────────────────────────────────────────────────────────────────────
# FORMATAÇÃO DE VALORES
# ─────────────────────────────────────────────────────────────────────────────
def _brl(v: float) -> str:
    return f"R$ {v:,.2f}"

def _brlk(v: float) -> str:
    """Compacto para KPIs — evita quebra de linha."""
    av = abs(v)
    s  = "-" if v < 0 else ""
    if av >= 1_000_000:
        return f"{s}R$ {av/1_000_000:,.2f}M"
    if av >= 1_000:
        return f"{s}R$ {av/1_000:,.1f}K"
    return f"{s}R$ {av:,.2f}"


# ─────────────────────────────────────────────────────────────────────────────
# PRIMITIVOS DE DESENHO
# ─────────────────────────────────────────────────────────────────────────────
def _draw_table(c, tbl: Table, x: float, y: float, w: float):
    """Envolve e desenha uma Table Platypus em coordenadas absolutas."""
    tbl.wrapOn(c, w, 9999)
    tbl.drawOn(c, x, y - tbl._height)
    return tbl._height


def _sec_header(c, x: float, y: float, w: float, texto: str) -> float:
    """Faixa azul de título de seção. Retorna a altura consumida."""
    h = 8 * mm
    c.setFillColor(AZUL_MED)
    c.roundRect(x, y - h, w, h, 2, fill=1, stroke=0)
    p = Paragraph(texto.upper(), S_SEC)
    pw, ph = p.wrapOn(c, w - 8, h)
    p.drawOn(c, x + 6, y - h + (h - ph) / 2)
    return h + 2


def _kpi_block(c, x: float, y: float, w: float,
               kpis: list) -> float:
    """
    Bloco de KPIs lado a lado sobre fundo cinza.
    kpis = [(label, valor, cor)]  cor: 'p'|'n'|None
    Retorna altura consumida.
    """
    n  = len(kpis)
    cw = w / n
    h  = 14 * mm

    # fundo
    c.setFillColor(CINZA)
    c.roundRect(x, y - h, w, h, 2, fill=1, stroke=0)

    # linhas divisórias
    c.setStrokeColor(colors.HexColor("#C8D8E8"))
    c.setLineWidth(0.4)
    for i in range(1, n):
        lx = x + cw * i
        c.line(lx, y - h + 3, lx, y - 3)

    # textos
    for i, (label, valor, cor) in enumerate(kpis):
        cx = x + cw * i
        # label
        pl = Paragraph(label, S_LBL)
        plw, plh = pl.wrapOn(c, cw - 6, 20)
        pl.drawOn(c, cx + 4, y - 5 - plh)
        # valor
        sv = S_VALP if cor == "p" else S_VALN if cor == "n" else S_VAL
        pv = Paragraph(valor, sv)
        pvw, pvh = pv.wrapOn(c, cw - 6, 20)
        pv.drawOn(c, cx + 4, y - h + 2)

    return h + 3


def _data_table(c, x: float, y: float, w: float,
                cab: list, rows: list, cws: list,
                zebra: bool = True) -> float:
    """Tabela de dados com cabeçalho azul escuro."""
    data = [cab] + rows
    tbl  = Table(data, colWidths=cws, repeatRows=1)
    estilo = [
        ("BACKGROUND",    (0, 0), (-1, 0),  AZUL_ESC),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  BRANCO),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 6.5),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#C5D3E0")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]
    if zebra:
        for i in range(2, len(data), 2):
            estilo.append(("BACKGROUND", (0, i), (-1, i), AZUL_CLR))
    tbl.setStyle(TableStyle(estilo))
    return _draw_table(c, tbl, x, y, w)


# ─────────────────────────────────────────────────────────────────────────────
# COLUNA ESQUERDA
# ─────────────────────────────────────────────────────────────────────────────
def _col_esquerda(c, x, y_start, posicao, saldos, cambios_disp,
                  pos_30, pos_60, pos_90, total_rec, total_obr, total_imp):
    w = COL_L - SEP / 2
    y = y_start

    # Posição consolidada
    y -= _sec_header(c, x, y, w, "Posição Consolidada")
    y -= _kpi_block(c, x, y, w, [
        ("Caixa BRL",           _brlk(posicao["total_bancos"]),      None),
        ("Câmbios a Receber",   _brlk(posicao["total_cambios_brl"]), None),
        ("Posição Consolidada", _brlk(posicao["total"]),
         "p" if posicao["total"] >= 0 else "n"),
    ])

    # Projeção 30/60/90 dias
    y -= _sec_header(c, x, y, w, "Projeção de Caixa — base: posição consolidada")
    y -= _kpi_block(c, x, y, w, [
        ("30 dias", _brlk(pos_30), "p" if pos_30 >= 0 else "n"),
        ("60 dias", _brlk(pos_60), "p" if pos_60 >= 0 else "n"),
        ("90 dias", _brlk(pos_90), "p" if pos_90 >= 0 else "n"),
    ])

    # Recebíveis e obrigações
    saldo_proj = posicao["total"] + total_rec + total_obr
    y -= _sec_header(c, x, y, w, f"Recebíveis e Obrigações — {date.today().year}")
    y -= _kpi_block(c, x, y, w, [
        ("Recebíveis",      _brlk(total_rec),       "p"),
        ("Obrigações",      _brlk(abs(total_obr)),   "n"),
        ("Saldo Projetado", _brlk(saldo_proj),
         "p" if saldo_proj >= 0 else "n"),
        ("Impostos",        _brlk(abs(total_imp)),   "n"),
    ])

    # Saldos bancários
    y -= _sec_header(c, x, y, w, "Saldos Bancários")
    if saldos:
        cws = [w * 0.36, w * 0.22, w * 0.25, w * 0.17]
        rows = [[r["banco"], r.get("tipo") or "C/C",
                 _brl(r["saldo"] or 0), str(r["data"])] for r in saldos]
        y -= _data_table(c, x, y, w,
                         ["Banco / Conta", "Tipo", "Saldo", "Data"],
                         rows, cws) + 3
    else:
        y -= 5 * mm

    # Câmbios disponíveis
    y -= _sec_header(c, x, y, w, "Câmbios Disponíveis")
    if cambios_disp:
        ptax = posicao.get("ptax_map", {})
        cws  = [w * 0.33, w * 0.22, w * 0.27, w * 0.18]
        rows = []
        for cv in cambios_disp[:8]:
            taxa     = ptax.get(cv["moeda"])
            brl_proj = _brl((cv["valor_me"] or 0) * taxa) if taxa else "—"
            nome     = (cv.get("descricao") or cv.get("razao_social") or "—")[:20]
            rows.append([nome,
                         f"{cv['valor_me']:,.0f} {cv['moeda']}",
                         brl_proj,
                         str(cv.get("data_entrada") or "—")])
        y -= _data_table(c, x, y, w,
                         ["Descrição", "Valor ME", "BRL Proj.", "Entrada"],
                         rows, cws) + 2
        if len(cambios_disp) > 8:
            p = Paragraph(f"+ {len(cambios_disp)-8} posição(ões) não exibida(s).", S_LBL)
            pw, ph = p.wrapOn(c, w, 20)
            p.drawOn(c, x, y - ph)
            y -= ph + 2

    return y


# ─────────────────────────────────────────────────────────────────────────────
# COLUNA DIREITA
# ─────────────────────────────────────────────────────────────────────────────
def _col_direita(c, x, y_start, val_alta, val_media, val_baixa,
                 total_fup, n_deals, top_deals, por_mes):
    w = COL_R - SEP / 2
    y = y_start

    # Pipeline FUP
    y -= _sec_header(c, x, y, w, "FUP Vendas — Pipeline")
    y -= _kpi_block(c, x, y, w, [
        ("ALTA",  _brlk(val_alta),  "p" if val_alta > 0 else None),
        ("MEDIA", _brlk(val_media), None),
        ("BAIXA", _brlk(val_baixa), None),
    ])
    y -= _kpi_block(c, x, y, w, [
        ("Total no Pipeline", _brlk(total_fup),
         "p" if total_fup > 0 else None),
        ("Negócios ativos", str(n_deals), None),
    ])

    # Principais negócios
    y -= _sec_header(c, x, y, w, "Principais Negócios (ALTA + MEDIA)")
    if top_deals:
        cws  = [w * 0.45, w * 0.13, w * 0.32, w * 0.10]
        rows = []
        for d in top_deals:
            nome = d["razao"][:26] + "…" if len(d["razao"]) > 26 else d["razao"]
            rows.append([nome, d["prob"], _brl(d["valor"]), str(d["parcelas"])])
        y -= _data_table(c, x, y, w,
                         ["Negócio", "Prob.", "Valor BRL", "Parc."],
                         rows, cws) + 3
    else:
        y -= 5 * mm

    # Recebimentos por mês
    y -= _sec_header(c, x, y, w, "Recebimentos Esperados por Mês (ALTA + MEDIA)")
    if por_mes:
        meses = sorted(por_mes.keys())[:9]
        cws   = [w * 0.35, w * 0.65]
        rows  = [[m, _brl(por_mes[m])] for m in meses]
        y -= _data_table(c, x, y, w,
                         ["Mês", "Valor Esperado"],
                         rows, cws) + 3
    else:
        y -= 5 * mm

    return y


# ─────────────────────────────────────────────────────────────────────────────
# GERAÇÃO DO PDF
# ─────────────────────────────────────────────────────────────────────────────
def _gerar_pdf(usuario: str) -> bytes:
    buf  = io.BytesIO()
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

    def _sv(linhas):
        return sum(r.get("valor_brl") or r.get("valor") or 0 for r in linhas)

    val_alta  = _sv(fup_alta)
    val_media = _sv(fup_media)
    val_baixa = _sv(fup_baixa)
    total_fup = val_alta + val_media + val_baixa

    deal_map = defaultdict(lambda: {"razao": "", "valor": 0.0, "prob": "", "parcelas": 0})
    for ln in fup_alta + fup_media:
        did = ln.get("deal_id", "")
        deal_map[did]["razao"]     = ln.get("razao_social") or ln.get("descricao") or did
        deal_map[did]["valor"]    += ln.get("valor_brl") or ln.get("valor") or 0
        deal_map[did]["prob"]      = ln.get("probabilidade", "")
        deal_map[did]["parcelas"] += 1

    top_deals = sorted(deal_map.values(), key=lambda d: -d["valor"])[:8]
    n_deals   = len({r.get("deal_id") for r in fup_alta + fup_media + fup_baixa})

    por_mes: dict = defaultdict(float)
    for ln in fup_alta + fup_media:
        venc = str(ln.get("vencimento") or "")[:7]
        por_mes[venc] += ln.get("valor_brl") or ln.get("valor") or 0

    # ── Canvas ───────────────────────────────────────────────────────────
    c = rl_canvas.Canvas(buf, pagesize=A4)

    # Borda da página
    c.setStrokeColor(colors.HexColor("#BFD0E0"))
    c.setLineWidth(0.5)
    c.rect(MARG - 3, MARG - 3, W_PG - 2*MARG + 6, H_PG - 2*MARG + 6)

    # ── CABEÇALHO ────────────────────────────────────────────────────────
    y_top = H_PG - MARG

    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logo_tecnotok.png")
    if os.path.exists(logo_path):
        c.drawImage(logo_path, MARG, y_top - 12*mm,
                    width=26*mm, height=12*mm, preserveAspectRatio=True, mask="auto")
        x_titulo = MARG + 28*mm
    else:
        x_titulo = MARG

    c.setFont("Helvetica-Bold", 17)
    c.setFillColor(AZUL_ESC)
    c.drawString(x_titulo, y_top - 10*mm, "TKT Cash Flow")

    c.setFont("Helvetica", 8)
    c.setFillColor(CINZA_TXT)
    data_str = f"Relatório Executivo  ·  {hoje.strftime('%d/%m/%Y')}"
    c.drawRightString(MARG + LARG, y_top - 6*mm, data_str)

    # Linha separadora
    y_top -= 14*mm
    c.setStrokeColor(AZUL_MED)
    c.setLineWidth(1.5)
    c.line(MARG, y_top, MARG + LARG, y_top)
    y_top -= 4*mm

    # ── LINHA SEPARADORA ENTRE COLUNAS ───────────────────────────────────
    # Desenhada depois do conteúdo (altura dinâmica)
    x_L = MARG
    x_R = MARG + COL_L + SEP / 2

    # ── CONTEÚDO ─────────────────────────────────────────────────────────
    y_end_L = _col_esquerda(c, x_L, y_top, posicao, saldos, cambios_disp,
                             pos_30, pos_60, pos_90, total_rec, total_obr, total_imp)
    y_end_R = _col_direita(c, x_R, y_top, val_alta, val_media, val_baixa,
                            total_fup, n_deals, top_deals, por_mes)

    # Linha vertical entre colunas
    y_col_bottom = min(y_end_L, y_end_R) - 2*mm
    c.setStrokeColor(colors.HexColor("#C5D3E0"))
    c.setLineWidth(0.5)
    c.line(MARG + COL_L, y_top, MARG + COL_L, y_col_bottom)

    # ── RODAPÉ ───────────────────────────────────────────────────────────
    y_rod = MARG + 4*mm
    c.setStrokeColor(AZUL_CLR)
    c.setLineWidth(0.4)
    c.line(MARG, y_rod + 3*mm, MARG + LARG, y_rod + 3*mm)

    c.setFont("Helvetica", 6)
    c.setFillColor(CINZA_TXT)
    rodape = (f"Gerado em {hoje.strftime('%d/%m/%Y')} por {usuario}  ·  "
              f"TKT Cash Flow  ·  Tecnotok © {hoje.year}  ·  "
              "Documento confidencial — uso interno")
    c.drawCentredString(MARG + LARG / 2, y_rod, rodape)

    c.save()
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# RENDER (página Streamlit)
# ─────────────────────────────────────────────────────────────────────────────
def render():
    st.title("📄 Relatório Executivo — PDF")
    st.markdown(
        "Gera um **one-pager A4** com os principais indicadores de caixa "
        "e o pipeline de vendas. Pronto para impressão ou envio por e-mail."
    )

    hoje    = date.today()
    usuario = auth.get_display_name() or "Sistema"

    with st.expander("ℹ️ Conteúdo do relatório", expanded=False):
        st.markdown("""
        **Coluna esquerda — Indicadores de Caixa**
        - Posição consolidada: caixa BRL + câmbios a receber (PTAX)
        - Projeção 30, 60 e 90 dias
        - Recebíveis, obrigações e impostos do ano
        - Saldos bancários por conta
        - Câmbios disponíveis com BRL projetado

        **Coluna direita — FUP Vendas**
        - Pipeline por probabilidade (ALTA / MEDIA / BAIXA)
        - Top 8 negócios ALTA + MEDIA
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
