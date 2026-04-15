"""
Página DATABASE / ERP — Import CSV com mapeador de colunas flexível.
Suporta lançamentos realizados e a realizar (a pagar / a receber).
"""

import streamlit as st
import pandas as pd
from datetime import date
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db

# Campos internos obrigatórios / opcionais
CAMPOS_INTERNOS = {
    "operacao":      {"label": "OPERAÇÃO (CREDITO/DEBITO)", "obrigatorio": True},
    "razao_social":  {"label": "Razão Social",              "obrigatorio": True},
    "vencimento":    {"label": "Vencimento / Data",         "obrigatorio": True},
    "valor":         {"label": "Valor (positivo)",          "obrigatorio": True},
    "descricao":     {"label": "Descrição",                 "obrigatorio": False},
    "codigo":        {"label": "Código",                    "obrigatorio": False},
    "tipo":          {"label": "Tipo",                      "obrigatorio": False},
    "lote":          {"label": "Lote / Categoria",          "obrigatorio": False},
    "probabilidade": {"label": "Probabilidade",             "obrigatorio": False},
    "imposto":       {"label": "Imposto? (SIM/NAO)",        "obrigatorio": False},
    "status":        {"label": "Status (PAGO/RECEBIDO/PENDENTE)", "obrigatorio": False},
}

OPCAO_IGNORAR = "— Ignorar esta coluna —"


def render():
    st.title("📂 DATABASE / ERP")
    st.markdown("Importe os lançamentos do ERP. Contém tanto registros **já realizados** quanto **a realizar** (a pagar e a receber).")

    tab_import, tab_dados, tab_atraso, tab_estatisticas = st.tabs([
        "📥 Importar CSV", "📋 Dados Atuais", "🔴 Em Atraso", "📊 Estatísticas"
    ])

    # ─── ABA IMPORTAR ──────────────────────────────────────────────────────
    with tab_import:
        st.subheader("1. Faça upload do CSV exportado pelo ERP")

        col_sep, col_enc = st.columns(2)
        with col_sep:
            separador = st.selectbox("Separador", [",", ";", "\\t", "|"], index=1)
            if separador == "\\t":
                separador = "\t"
        with col_enc:
            encoding = st.selectbox("Encoding", ["utf-8", "latin-1", "cp1252"], index=2)

        arquivo = st.file_uploader("Selecione o arquivo CSV", type=["csv", "txt"])

        if arquivo:
            try:
                df_preview = pd.read_csv(arquivo, sep=separador, encoding=encoding, nrows=5)
                st.success(f"✅ Arquivo lido: {len(df_preview.columns)} colunas detectadas")
                st.dataframe(df_preview, use_container_width=True)
                colunas_csv = list(df_preview.columns)
            except Exception as e:
                st.error(f"Erro ao ler CSV: {e}")
                return

            # ── Carregar mapeamento salvo ──────────────────────────────────
            st.subheader("2. Mapeie as colunas do CSV para os campos internos")

            mapeamentos_salvos = db.listar_mapeamentos_csv()
            nome_mapeamento = st.text_input(
                "Nome do mapeamento (para salvar/carregar)",
                value="ERP Padrão"
            )

            mapeamento_atual = {}
            if nome_mapeamento in mapeamentos_salvos:
                if st.button("📂 Carregar mapeamento salvo"):
                    mapeamento_atual = db.carregar_mapeamento_csv(nome_mapeamento)
                    st.success("Mapeamento carregado!")

            # ── Formulário de mapeamento ───────────────────────────────────
            opcoes = [OPCAO_IGNORAR] + colunas_csv
            mapeamento_form = {}

            st.markdown("*Selecione qual coluna do CSV corresponde a cada campo:*")
            cols_a = st.columns(2)

            campos_lista = list(CAMPOS_INTERNOS.items())
            metade = (len(campos_lista) + 1) // 2

            for idx, (campo, info) in enumerate(campos_lista):
                col = cols_a[0] if idx < metade else cols_a[1]
                label = info["label"]
                if info["obrigatorio"]:
                    label += " *"

                # Tenta encontrar default inteligente
                default_idx = 0
                salvo = mapeamento_atual.get(campo)
                if salvo and salvo in colunas_csv:
                    default_idx = opcoes.index(salvo)
                else:
                    # Tenta match por nome similar
                    for i, c in enumerate(colunas_csv):
                        if campo.lower().replace("_", "") in c.lower().replace(" ", "").replace("_", ""):
                            default_idx = i + 1
                            break

                mapeamento_form[campo] = col.selectbox(
                    label, opcoes, index=default_idx, key=f"map_{campo}"
                )

            # ── Configurações adicionais ───────────────────────────────────
            st.subheader("3. Configurações de importação")
            col_a, col_b, col_c = st.columns(3)

            with col_a:
                fmt_data = st.text_input("Formato da data", value="%d/%m/%Y",
                    help="Ex: %d/%m/%Y para 31/12/2025 ou %Y-%m-%d para 2025-12-31")
            with col_b:
                sep_decimal = st.selectbox("Separador decimal", [",", "."], index=0)
            with col_c:
                substituir = st.checkbox("Substituir dados existentes", value=True,
                    help="Se desmarcado, os dados são adicionados aos existentes")

            col_d, col_e = st.columns(2)
            with col_d:
                op_credito_valor = st.text_input(
                    "Valor que representa CRÉDITO na coluna OPERAÇÃO",
                    value="CREDITO",
                    help="Ex: CREDITO, C, ENTRADA, RECEBIMENTO"
                )
            with col_e:
                status_default = st.selectbox(
                    "Status padrão (quando coluna não mapeada)",
                    ["PENDENTE", "PAGO", "RECEBIDO"], index=0
                )

            # ── Botões ─────────────────────────────────────────────────────
            col_btn1, col_btn2, _ = st.columns([1, 1, 2])

            with col_btn1:
                if st.button("💾 Salvar mapeamento"):
                    db.salvar_mapeamento_csv(nome_mapeamento, mapeamento_form)
                    st.success(f"Mapeamento '{nome_mapeamento}' salvo!")

            with col_btn2:
                importar = st.button("📥 Importar dados", type="primary")

            if importar:
                # Valida obrigatórios
                faltando = [
                    CAMPOS_INTERNOS[c]["label"]
                    for c, v in mapeamento_form.items()
                    if CAMPOS_INTERNOS[c]["obrigatorio"] and v == OPCAO_IGNORAR
                ]
                if faltando:
                    st.error(f"Campos obrigatórios não mapeados: {', '.join(faltando)}")
                    return

                # Lê o CSV completo
                arquivo.seek(0)
                try:
                    df_full = pd.read_csv(arquivo, sep=separador, encoding=encoding)
                except Exception as e:
                    st.error(f"Erro ao ler CSV completo: {e}")
                    return

                registros = []
                erros = []

                for idx, row in df_full.iterrows():
                    try:
                        reg = _mapear_linha(
                            row, mapeamento_form, fmt_data,
                            sep_decimal, op_credito_valor, status_default
                        )
                        registros.append(reg)
                    except Exception as e:
                        erros.append(f"Linha {idx+2}: {e}")

                if erros:
                    with st.expander(f"⚠️ {len(erros)} linha(s) com erro"):
                        for e in erros[:50]:
                            st.text(e)

                if registros:
                    total = db.importar_erp(registros, substituir=substituir)
                    st.success(f"✅ {len(registros)} registro(s) importado(s). Total no banco: {total}")
                    st.balloons()
                else:
                    st.warning("Nenhum registro válido encontrado.")

    # ─── ABA DADOS ATUAIS ──────────────────────────────────────────────────
    with tab_dados:
        st.subheader("Dados do DATABASE / ERP")

        # Usa datas mínima e máxima dos próprios dados como default
        # para exibir todos os registros importados, não só o período de projeção
        todos_registros = db.listar_erp()
        if todos_registros:
            # Filtra apenas strings que sejam ISO válidas (YYYY-MM-DD)
            import re as _re
            _iso_pat = _re.compile(r"^\d{4}-\d{2}-\d{2}")
            datas_validas = [
                r["vencimento"][:10]
                for r in todos_registros
                if r.get("vencimento") and _iso_pat.match(str(r["vencimento"]))
            ]
            if datas_validas:
                data_min_banco = min(datas_validas)
                data_max_banco = max(datas_validas)
            else:
                data_min_banco = str(date(date.today().year, 1, 1))
                data_max_banco = str(date(date.today().year, 12, 31))
        else:
            data_min_banco = str(date(date.today().year, 1, 1))
            data_max_banco = str(date(date.today().year, 12, 31))

        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            dt_ini = st.date_input("De", value=date.fromisoformat(data_min_banco), key="erp_ini")
        with col_f2:
            dt_fim = st.date_input("Até", value=date.fromisoformat(data_max_banco), key="erp_fim")
        with col_f3:
            op_filtro = st.selectbox("Operação", ["Todas", "CREDITO", "DEBITO"], key="erp_op")
        with col_f4:
            razao_filtro = st.text_input("Razão Social", key="erp_razao")

        dados = db.listar_erp(
            dt_ini=str(dt_ini), dt_fim=str(dt_fim),
            operacao=None if op_filtro == "Todas" else op_filtro,
            razao=razao_filtro or None
        )

        # total_banco já foi carregado acima para calcular as datas default
        total_banco = todos_registros

        if dados:
            df = pd.DataFrame(dados)
            df["vencimento"] = pd.to_datetime(df["vencimento"]).dt.strftime("%d/%m/%Y")
            df["valor"]       = df["valor"].apply(lambda x: f"R$ {x:,.2f}" if x else "")
            df["valor_final"] = df["valor_final"].apply(lambda x: f"R$ {x:,.2f}" if x else "")

            cols_show = ["operacao", "razao_social", "descricao", "vencimento",
                         "valor", "valor_final", "status", "probabilidade", "origem"]
            cols_show = [c for c in cols_show if c in df.columns]
            st.caption(f"Exibindo {len(dados)} de {len(total_banco)} registros no banco · período: {dt_ini} → {dt_fim}")
            st.dataframe(df[cols_show], use_container_width=True, height=500)

            total_cred = sum(r["valor_final"] for r in dados if (r["valor_final"] or 0) > 0)
            total_deb  = sum(r["valor_final"] for r in dados if (r["valor_final"] or 0) < 0)
            st.markdown(
                f"**Entradas:** `R$ {total_cred:,.2f}` &nbsp;|&nbsp; "
                f"**Saídas:** `R$ {total_deb:,.2f}` &nbsp;|&nbsp; "
                f"**Saldo:** `R$ {total_cred + total_deb:,.2f}`"
            )

            if st.button("🗑️ Limpar todos os dados do DATABASE", type="secondary"):
                db.importar_erp([], substituir=True)
                st.success("Dados removidos.")
                st.rerun()

        elif total_banco:
            # Há dados mas nenhum no período selecionado
            st.warning(
                f"⚠️ Existem **{len(total_banco)} registros** no banco, mas nenhum está dentro do período "
                f"**{dt_ini} → {dt_fim}**. Ajuste as datas acima ou altere o Período de Análise no menu lateral."
            )
            # Mostra amostra de datas disponíveis no banco
            datas = sorted({r["vencimento"][:7] for r in total_banco if r.get("vencimento")})
            st.caption(f"Meses disponíveis no banco: {', '.join(datas[:24])}" + (" ..." if len(datas) > 24 else ""))

            if st.button("🗑️ Limpar todos os dados do DATABASE", type="secondary"):
                db.importar_erp([], substituir=True)
                st.success("Dados removidos.")
                st.rerun()
        else:
            st.info("Nenhum dado importado ainda. Use a aba **Importar CSV** para começar.")

    # ─── ABA EM ATRASO ────────────────────────────────────────────────────
    with tab_atraso:
        st.subheader("🔴 Lançamentos em Atraso")
        st.markdown(
            "Lançamentos ERP com vencimento **antes do período de análise** e status **PENDENTE**. "
            "Marque os que são atrasos reais — eles entrarão no fluxo de caixa mesmo com o corte de data ativo."
        )

        dt_corte = st.session_state.get("cfg_dt_ini") or str(date(date.today().year, 1, 1))
        st.caption(f"Data de corte atual: **{dt_corte}** (início do período de análise)")

        pendentes = db.listar_erp_pendentes_atraso(dt_corte)

        if not pendentes:
            st.success("Nenhum lançamento PENDENTE anterior ao período de análise.")
        else:
            st.info(f"{len(pendentes)} lançamento(s) encontrado(s). Marque os que são **atrasos reais**.")

            df_at = pd.DataFrame(pendentes)
            df_at["incluir_atraso"] = df_at["incluir_atraso"].fillna(False).astype(bool)

            df_edit = df_at[[
                "id", "incluir_atraso", "operacao", "razao_social",
                "descricao", "vencimento", "valor_final", "status"
            ]].copy()
            df_edit = df_edit.rename(columns={
                "incluir_atraso": "Em Atraso?",
                "operacao":       "Op.",
                "razao_social":   "Razão Social",
                "descricao":      "Descrição",
                "vencimento":     "Vencimento",
                "valor_final":    "Valor",
                "status":         "Status",
            })

            edited = st.data_editor(
                df_edit,
                use_container_width=True,
                hide_index=True,
                disabled=["id", "Op.", "Razão Social", "Descrição", "Vencimento", "Valor", "Status"],
                column_config={
                    "id":          st.column_config.NumberColumn("ID", width="small"),
                    "Em Atraso?":  st.column_config.CheckboxColumn("Em Atraso?", width="small",
                                       help="Marque para incluir no fluxo mesmo sendo anterior ao período"),
                    "Valor":       st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                },
                key="erp_atraso_editor",
            )

            if st.button("💾 Salvar marcações", type="primary", key="erp_atraso_salvar"):
                ids_true  = edited.loc[edited["Em Atraso?"] == True,  "id"].tolist()
                ids_false = edited.loc[edited["Em Atraso?"] == False, "id"].tolist()
                db.atualizar_erp_atraso(
                    [int(i) for i in ids_true],
                    [int(i) for i in ids_false],
                )
                marcados = len(ids_true)
                st.success(f"✅ {marcados} lançamento(s) marcado(s) como Em Atraso.")
                st.rerun()

    # ─── ABA ESTATÍSTICAS ─────────────────────────────────────────────────
    with tab_estatisticas:
        st.subheader("Distribuição dos lançamentos")

        dados_all = db.listar_erp()
        if not dados_all:
            st.info("Nenhum dado disponível.")
            return

        df_all = pd.DataFrame(dados_all)
        df_all["vencimento_dt"] = pd.to_datetime(df_all["vencimento"], errors="coerce")
        df_all["mes"] = df_all["vencimento_dt"].dt.to_period("M").astype(str)

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.markdown("**Por Status**")
            st.dataframe(
                df_all.groupby("status")["valor_final"].sum().reset_index()
                      .rename(columns={"status": "Status", "valor_final": "Valor Total"}),
                use_container_width=True
            )
        with col_s2:
            st.markdown("**Por Operação**")
            st.dataframe(
                df_all.groupby("operacao")["valor_final"].agg(["sum", "count"])
                      .reset_index()
                      .rename(columns={"operacao": "Operação", "sum": "Total", "count": "Qtd"}),
                use_container_width=True
            )

        st.markdown("**Saldo por Mês**")
        mensal = df_all.groupby("mes")["valor_final"].sum().reset_index()
        mensal.columns = ["Mês", "Saldo"]
        st.bar_chart(mensal.set_index("Mês"))


# ─── HELPER: MAPEAR LINHA ────────────────────────────────────────────────────

def _mapear_linha(row, mapeamento, fmt_data, sep_decimal, op_credito_valor, status_default):
    def get(campo):
        col = mapeamento.get(campo, OPCAO_IGNORAR)
        if col == OPCAO_IGNORAR:
            return None
        return row.get(col)

    # Operação
    op_raw = str(get("operacao") or "").strip().upper()
    operacao = "CREDITO" if op_credito_valor.upper() in op_raw or op_raw == "CREDITO" else "DEBITO"

    # Valor
    val_raw = str(get("valor") or "0").strip()
    if sep_decimal == ",":
        val_raw = val_raw.replace(".", "").replace(",", ".")
    val_raw = val_raw.replace("R$", "").replace(" ", "")
    valor = abs(float(val_raw))

    # Vencimento
    from datetime import datetime as _dt, timedelta as _td
    ven_raw = str(get("vencimento") or "").strip()
    vencimento = None

    # Verifica se é número serial do Excel (ex: 45292)
    try:
        serial = int(float(ven_raw))
        if 1000 < serial < 100000:  # faixa razoável de datas Excel (1902–2173)
            # Excel: base = 1899-12-30, com correção do bug do ano 1900
            excel_base = _dt(1899, 12, 30)
            vencimento = (excel_base + _td(days=serial)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass

    # Se não era serial, tenta formatos de texto comuns
    if vencimento is None:
        for fmt in [fmt_data, "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"]:
            try:
                vencimento = _dt.strptime(ven_raw, fmt).strftime("%Y-%m-%d")
                break
            except Exception:
                continue

    if vencimento is None:
        raise ValueError(f"Data '{ven_raw}' não reconhecida (formato esperado: {fmt_data})")

    # Status
    status_raw = str(get("status") or "").strip().upper()
    if status_raw in ("PAGO", "RECEBIDO", "PENDENTE"):
        status = status_raw
    else:
        status = status_default

    # Probabilidade
    prob_raw = str(get("probabilidade") or "").strip().upper()
    probabilidade = prob_raw if prob_raw in ("CONFIRMADO", "ALTA", "MEDIA") else "CONFIRMADO"

    # Valor final (positivo para crédito, negativo para débito)
    valor_final = valor if operacao == "CREDITO" else -valor

    # Semana
    try:
        dt = _dt.strptime(vencimento, "%Y-%m-%d")
        semana = dt.isocalendar()[1]
    except Exception:
        semana = None

    return {
        "operacao":      operacao,
        "codigo":        str(get("codigo") or ""),
        "tipo":          str(get("tipo") or "ERP"),
        "lote":          str(get("lote") or ""),
        "razao_social":  str(get("razao_social") or ""),
        "descricao":     str(get("descricao") or ""),
        "vencimento":    vencimento,
        "valor":         valor,
        "valor_final":   valor_final,
        "semana":        semana,
        "probabilidade": probabilidade,
        "imposto":       str(get("imposto") or "NAO").upper(),
        "status":        status,
        "origem":        "ERP",
    }
