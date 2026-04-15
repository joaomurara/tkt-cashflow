"""
Página Provisões — Lançamentos manuais de fluxo de caixa.
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db


def render():
    st.title("📝 Provisões")
    st.markdown("Lançamentos manuais que ainda não constam no ERP — despesas previstas, recebimentos estimados, etc.")

    # ── DIAGNÓSTICO TEMPORÁRIO: constraints únicas da tabela provisoes ─────────
    with st.expander("🔍 Diagnóstico: constraints da tabela provisoes", expanded=False):
        try:
            constraints = db.get_provisoes_constraints()
            if constraints:
                st.write("Constraints UNIQUE encontradas:")
                for c in constraints:
                    st.code(f"{c['constraint_name']}: {c['columns']}")
            else:
                st.info("Nenhuma constraint UNIQUE encontrada além do PRIMARY KEY.")
        except Exception as e:
            st.error(f"Erro ao buscar constraints: {e}")
    # ── FIM DIAGNÓSTICO ────────────────────────────────────────────────────────

    tab_novo, tab_lista, tab_origem = st.tabs([
        "➕ Novo Lançamento", "📋 Gerenciar", "🗑 Excluir por Origem"
    ])

    # ─── ABA NOVO ──────────────────────────────────────────────────────────
    with tab_novo:
        st.subheader("Novo lançamento")

        with st.form("form_provisao", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                operacao = st.selectbox("Operação *", ["CREDITO", "DEBITO"])
                razao_social = st.text_input("Razão Social *")
                descricao = st.text_input("Descrição *")
                valor = st.number_input("Valor (R$) *", min_value=0.01, step=0.01, format="%.2f")

            with col2:
                vencimento = st.date_input("Vencimento *", value=date.today())
                probabilidade = st.selectbox("Probabilidade", ["CONFIRMADO", "ALTA", "MEDIA"])
                codigo = st.text_input("Código (opcional)")
                lote = st.text_input("Lote / Categoria (opcional)")

            col3, col4 = st.columns(2)
            with col3:
                tipo = st.text_input("Tipo (opcional)", value="PROVISAO")
            with col4:
                imposto = st.selectbox("É imposto?", ["NAO", "SIM"])

            submitted = st.form_submit_button("💾 Salvar lançamento", type="primary")

        if submitted:
            if not razao_social or not descricao or valor <= 0:
                st.error("Preencha todos os campos obrigatórios (*).")
            else:
                dados = {
                    "operacao":      operacao,
                    "codigo":        codigo,
                    "tipo":          tipo,
                    "lote":          lote,
                    "razao_social":  razao_social,
                    "descricao":     descricao,
                    "vencimento":    str(vencimento),
                    "valor":         float(valor),
                    "probabilidade": probabilidade,
                    "imposto":       imposto,
                }
                pid = db.inserir_provisao(dados)
                st.success(f"✅ Lançamento #{pid} salvo com sucesso!")

    # ─── ABA LISTA ─────────────────────────────────────────────────────────
    with tab_lista:
        st.subheader("Provisões cadastradas")

        cfg_ini = st.session_state.get("cfg_dt_ini", str(date(date.today().year, 1, 1)))
        cfg_fim = st.session_state.get("cfg_dt_fim", str(date(date.today().year, 12, 31)))

        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            dt_ini = st.date_input("De", value=date.fromisoformat(cfg_ini), key="prov_ini")
        with col_f2:
            dt_fim = st.date_input("Até", value=date.fromisoformat(cfg_fim), key="prov_fim")
        with col_f3:
            op_filtro = st.selectbox("Operação", ["Todas", "CREDITO", "DEBITO"], key="prov_op")
        with col_f4:
            razao_filtro = st.text_input("Razão Social", key="prov_razao")

        dados = db.listar_provisoes(
            dt_ini=str(dt_ini), dt_fim=str(dt_fim),
            operacao=None if op_filtro == "Todas" else op_filtro,
            razao=razao_filtro or None,
        )

        if not dados:
            st.info("Nenhuma provisão cadastrada para o período selecionado.")
        else:
            # Totais
            total_cred = sum(r["valor_final"] for r in dados if (r["valor_final"] or 0) > 0)
            total_deb  = sum(r["valor_final"] for r in dados if (r["valor_final"] or 0) < 0)
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Entradas", f"R$ {total_cred:,.2f}")
            col_m2.metric("Saídas",   f"R$ {abs(total_deb):,.2f}")
            col_m3.metric("Saldo",    f"R$ {total_cred + total_deb:,.2f}")

            st.markdown("---")

            visao = st.radio("Visualização", ["Tabela", "Editar por linha"],
                             horizontal=True, key="prov_visao")

            if visao == "Tabela":
                df_show = pd.DataFrame(dados).copy()
                df_show["vencimento"]  = pd.to_datetime(df_show["vencimento"]).dt.strftime("%d/%m/%Y")
                df_show["valor"]       = df_show["valor"].apply(lambda x: f"R$ {x:,.2f}")
                df_show["valor_final"] = df_show["valor_final"].apply(
                    lambda x: f"🟢 R$ {x:,.2f}" if (x or 0) >= 0 else f"🔴 R$ {abs(x or 0):,.2f}"
                )
                cols_show = ["id", "operacao", "razao_social", "descricao", "tipo", "lote",
                             "vencimento", "valor", "valor_final", "probabilidade", "imposto"]
                cols_show = [c for c in cols_show if c in df_show.columns]
                st.dataframe(df_show[cols_show], use_container_width=True,
                             height=500, hide_index=True)

                if st.button("📥 Exportar CSV", key="prov_export"):
                    csv = pd.DataFrame(dados).to_csv(index=False).encode("utf-8-sig")
                    st.download_button("⬇️ Baixar Provisoes.csv", data=csv,
                                       file_name="Provisoes.csv", mime="text/csv")

            else:
                # ── Editar por linha (modo original expandível) ──────────────────
                col_ord1, col_ord2 = st.columns([2, 1])
                with col_ord1:
                    ordem_campo = st.selectbox(
                        "Ordenar por",
                        ["ID", "Vencimento", "Razão Social", "Valor"],
                        key="prov_ordem_campo",
                    )
                with col_ord2:
                    ordem_dir = st.radio(
                        "Direção", ["↑ Crescente", "↓ Decrescente"],
                        horizontal=True, key="prov_ordem_dir"
                    )

                _campo_map = {
                    "ID":           "id",
                    "Vencimento":   "vencimento",
                    "Razão Social": "razao_social",
                    "Valor":        "valor",
                }
                dados = sorted(
                    dados,
                    key=lambda r: (r.get(_campo_map[ordem_campo]) or ""),
                    reverse=(ordem_dir == "↓ Decrescente"),
                )

                for r in dados:
                    with st.expander(
                        f"#{r['id']} | {r['vencimento']} | {r['operacao']} | "
                        f"{r['razao_social']} | R$ {r['valor']:,.2f}"
                    ):
                        col_e1, col_e2 = st.columns(2)
                        with col_e1:
                            n_op   = st.selectbox("Operação", ["CREDITO", "DEBITO"],
                                                  index=0 if r["operacao"]=="CREDITO" else 1,
                                                  key=f"op_{r['id']}")
                            n_rz   = st.text_input("Razão Social", value=r["razao_social"] or "", key=f"rz_{r['id']}")
                            n_desc = st.text_input("Descrição", value=r["descricao"] or "", key=f"ds_{r['id']}")
                            n_val  = st.number_input("Valor", value=float(r["valor"] or 0),
                                                     min_value=0.01, step=0.01, format="%.2f", key=f"vl_{r['id']}")
                        with col_e2:
                            try:
                                dt_default = datetime.strptime(r["vencimento"][:10], "%Y-%m-%d").date()
                            except:
                                dt_default = date.today()
                            n_ven  = st.date_input("Vencimento", value=dt_default, key=f"vc_{r['id']}")
                            n_prob = st.selectbox("Probabilidade", ["CONFIRMADO", "ALTA", "MEDIA"],
                                                  index=["CONFIRMADO","ALTA","MEDIA"].index(
                                                      r.get("probabilidade","CONFIRMADO") or "CONFIRMADO"),
                                                  key=f"pb_{r['id']}")
                            n_lote = st.text_input("Lote", value=r["lote"] or "", key=f"lt_{r['id']}")
                            n_tipo = st.text_input("Tipo", value=r["tipo"] or "PROVISAO", key=f"tp_{r['id']}")

                        col_btn1, col_btn2, _ = st.columns([1, 1, 3])
                        with col_btn1:
                            if st.button("💾 Atualizar", key=f"upd_{r['id']}"):
                                db.atualizar_provisao(r["id"], {
                                    "operacao":      n_op,
                                    "codigo":        r.get("codigo") or "",
                                    "tipo":          n_tipo,
                                    "lote":          n_lote,
                                    "razao_social":  n_rz,
                                    "descricao":     n_desc,
                                    "vencimento":    str(n_ven),
                                    "valor":         float(n_val),
                                    "probabilidade": n_prob,
                                    "imposto":       r.get("imposto") or "NAO",
                                })
                                st.success("Atualizado!")
                                st.rerun()
                        with col_btn2:
                            if st.button("🗑️ Excluir", key=f"del_{r['id']}"):
                                db.excluir_provisao(r["id"])
                                st.success("Excluído!")
                                st.rerun()

    # ─── ABA EXCLUIR POR ORIGEM ───────────────────────────────────────────────
    with tab_origem:
        st.subheader("🗑 Excluir lançamentos por origem")
        st.caption(
            "Lista todos os fluxos de FUP Vendas e Simulações que foram enviados para Provisões. "
            "Selecione um para excluir todos os seus lançamentos de uma vez."
        )

        origens = db.listar_origens_provisoes()

        if not origens:
            st.info("Nenhum lançamento de FUP Vendas ou Simulação encontrado em Provisões.")
        else:
            # Monta dataframe de exibição
            df_orig = pd.DataFrame(origens)
            df_orig["Origem"] = df_orig["tipo"].map(
                lambda t: "📡 FUP Vendas" if "FUP" in str(t) else "🧮 Simulação"
            )
            df_orig["Entradas (R$)"] = df_orig["total_cred"].apply(lambda x: f"R$ {x:,.2f}")
            df_orig["Saídas (R$)"]   = df_orig["total_deb"].apply(lambda x: f"R$ {x:,.2f}")
            df_orig["Período"]       = df_orig["dt_ini"] + " → " + df_orig["dt_fim"]

            cols_show = ["Origem", "razao_social", "codigo", "qtd", "Período",
                         "Entradas (R$)", "Saídas (R$)"]
            df_show = df_orig[cols_show].rename(columns={
                "razao_social": "Cliente / Negócio",
                "codigo":       "Código",
                "qtd":          "Lançamentos",
            })
            st.dataframe(df_show, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("**Selecione o fluxo para excluir:**")

            # Seletor
            opcoes = {
                f"{('📡 FUP' if 'FUP' in o['tipo'] else '🧮 Sim.')} — "
                f"{o['razao_social']} [{o['codigo']}] ({o['qtd']} lançamentos)": o
                for o in origens
            }
            escolha_label = st.selectbox(
                "Fluxo", list(opcoes.keys()), key="orig_sel"
            )
            escolha = opcoes[escolha_label]

            st.warning(
                f"⚠️ Isso excluirá **{escolha['qtd']} lançamento(s)** de "
                f"**{escolha['razao_social']}** (código: `{escolha['codigo']}`) "
                f"permanentemente."
            )

            confirmar = st.checkbox(
                "Confirmo que desejo excluir todos esses lançamentos", key="orig_confirm"
            )
            if st.button("🗑 Excluir lançamentos", type="primary",
                         key="orig_del_btn", disabled=not confirmar):
                n = db.excluir_provisoes_por_origem(
                    escolha["tipo"], escolha["codigo"], escolha["razao_social"]
                )
                st.success(f"✅ {n} lançamento(s) excluído(s) com sucesso.")
                st.rerun()
