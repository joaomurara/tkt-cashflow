"""
Página Terminal Financeiro — Mercado em tempo real.
Integra os módulos: Ações, Câmbio, Macro BR, Cripto, Notícias, Renda Fixa, Macro EUA, Macro Europa, Macro China.
"""

import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timedelta

# Importa sistema de configuração do app (para API keys)
try:
    from tkt_app.db import get_cfg, set_cfg
except ImportError:
    try:
        from db import get_cfg, set_cfg
    except ImportError:
        def get_cfg(k): return ""
        def set_cfg(k, v): pass


# ══════════════════════════════════════════════════════════════════════════════
# FUNÇÕES DE DADOS — reaproveitadas do terminal_financeiro original
# ══════════════════════════════════════════════════════════════════════════════

# ── Câmbio ────────────────────────────────────────────────────────────────────
def get_pair_rate(base, quote):
    try:
        url = f"https://economia.awesomeapi.com.br/json/last/{base}-{quote}"
        r = requests.get(url, timeout=8)
        data = r.json()
        key = f"{base}{quote}"
        if key in data:
            d = data[key]
            return {
                "bid":  float(d.get("bid", 0)),
                "ask":  float(d.get("ask", 0)),
                "high": float(d.get("high", 0)),
                "low":  float(d.get("low", 0)),
                "pct":  float(d.get("pctChange", 0)),
                "name": d.get("name", f"{base}/{quote}"),
            }
    except Exception:
        return None


# ── Macro BR ──────────────────────────────────────────────────────────────────
SERIES_BCB = {
    "SELIC Meta (% a.a.)":  432,
    "SELIC Efetiva (% a.a.)": 11,
    "IPCA Mensal (%)":      433,
    "INPC Mensal (%)":      188,
    "IGP-M Mensal (%)":     189,
    "CDI (% a.a.)":         4389,
    "Dólar PTAX (R$)":      1,
    "Euro PTAX (R$)":       21619,
}

def get_bcb_serie(codigo, n=13):
    try:
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{n}?formato=json"
        r = requests.get(url, timeout=10)
        return r.json()
    except Exception:
        return []


# ── Cripto ────────────────────────────────────────────────────────────────────
CRIPTO_IDS = "bitcoin,ethereum,solana,bnb,xrp,cardano,dogecoin,chainlink"
CRIPTO_NOMES = {
    "bitcoin":   "Bitcoin (BTC)",
    "ethereum":  "Ethereum (ETH)",
    "solana":    "Solana (SOL)",
    "bnb":       "BNB",
    "xrp":       "XRP",
    "cardano":   "Cardano (ADA)",
    "dogecoin":  "Dogecoin (DOGE)",
    "chainlink": "Chainlink (LINK)",
}

def get_cripto():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": CRIPTO_IDS,
                "vs_currencies": "usd,brl",
                "include_24hr_change": "true",
                "include_market_cap": "true",
            },
            timeout=10,
        )
        return r.json()
    except Exception:
        return {}


# ── Notícias ──────────────────────────────────────────────────────────────────
FEEDS = [
    ("https://feeds.valor.com.br/financas/rss.xml", "Valor Econômico"),
    ("https://feeds.valor.com.br/brasil/rss.xml",   "Valor — Brasil"),
    ("https://www.infomoney.com.br/feed/",           "InfoMoney"),
    ("https://exame.com/rss/",                       "Exame"),
]

def get_noticias_rss(url, fonte, n=5):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, timeout=10, headers=headers)
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        result = []
        for item in items[:n]:
            titulo = item.findtext("title") or ""
            link   = item.findtext("link") or ""
            data   = item.findtext("pubDate") or ""
            desc   = item.findtext("description") or ""
            desc   = re.sub("<[^<]+?>", "", desc)[:200]
            result.append({
                "fonte":  fonte,
                "titulo": titulo.strip(),
                "data":   data[:16],
                "desc":   desc.strip(),
                "link":   link.strip(),
            })
        return result
    except Exception:
        return []


# ── Renda Fixa ────────────────────────────────────────────────────────────────
def get_tesouro_direto():
    try:
        url = "https://www.tesourodireto.com.br/json/br/com/b3/tesourodireto/model/dto/TesouroDiretoDto.json"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        return r.json().get("response", {}).get("TrsrBdTradgList", [])
    except Exception:
        return []

def get_bcb_selic():
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        r = requests.get(url, timeout=8)
        return float(r.json()[0]["valor"].replace(",", "."))
    except Exception:
        return None


# ── Macro EUA (BLS) ───────────────────────────────────────────────────────────
BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
SERIES_BLS = {
    "CPI-U (All Urban Consumers)":    "CUSR0000SA0",
    "CPI-U Core (ex. Food & Energy)": "CUSR0000SA0L1E",
    "CPI-U Food":                     "CUSR0000SAF1",
    "CPI-U Energy":                   "CUSR0000SA0E",
    "Non-Farm Payroll (Total)":       "CES0000000001",
    "NFP — Private Sector":           "CES0500000001",
    "NFP — Manufacturing":            "CES3000000001",
    "Unemployment Rate (%)":          "LNS14000000",
    "Average Hourly Earnings ($)":    "CES0500000003",
}

def get_bls_data(years=2):
    try:
        ano_fim = datetime.now().year
        payload = {
            "seriesid": list(SERIES_BLS.values()),
            "startyear": str(ano_fim - years),
            "endyear":   str(ano_fim),
        }
        r = requests.post(BLS_URL, json=payload, timeout=15)
        data = r.json()
        if data.get("status") == "REQUEST_SUCCEEDED":
            return {s["seriesID"]: s for s in data.get("Results", {}).get("series", [])}
    except Exception:
        pass
    return {}


# ── Macro Europa (ECB) ────────────────────────────────────────────────────────
ECB_TAXAS = {
    "Taxa Principal (MRR)":     "FM/B.U2.EUR.4F.KR.MRR_FR.LEV",
    "Taxa de Depósito (DFR)":   "FM/B.U2.EUR.4F.KR.DFR.LEV",
    "Taxa Marginal (MLF)":      "FM/B.U2.EUR.4F.KR.MLFR.LEV",
}

def get_ecb_serie(flow_key, lastN=5):
    """Busca série do ECB Statistical Data Warehouse (SDMX-JSON)."""
    try:
        parts    = flow_key.split("/", 1)
        flow     = parts[0]
        key      = parts[1] if len(parts) > 1 else ""
        url      = f"https://sdw-wsrest.ecb.europa.eu/service/data/{flow}/{key}"
        params   = {"lastNObservations": lastN, "format": "jsondata"}
        headers  = {"Accept": "application/json"}
        r        = requests.get(url, params=params, headers=headers, timeout=12)
        data     = r.json()
        # Extrai séries e períodos do SDMX-JSON
        datasets = data.get("dataSets", [{}])
        struct   = data.get("structure", {})
        dims_obs = struct.get("dimensions", {}).get("observation", [])
        periodos = []
        for dim in dims_obs:
            if dim.get("id") == "TIME_PERIOD":
                periodos = [v["id"] for v in dim.get("values", [])]
                break
        series_dict = datasets[0].get("series", {}) if datasets else {}
        result = []
        for _skey, sval in series_dict.items():
            obs = sval.get("observations", {})
            for idx_str, vals in sorted(obs.items(), key=lambda x: int(x[0])):
                idx = int(idx_str)
                v   = vals[0] if vals else None
                per = periodos[idx] if idx < len(periodos) else str(idx)
                if v is not None:
                    result.append({"periodo": per, "valor": float(v)})
        return result
    except Exception:
        return []

def get_ecb_hicp(lastN=13):
    """HICP — inflação da Zona Euro (taxa anual %)."""
    return get_ecb_serie("ICP/M.U2.N.000000.4.ANR", lastN=lastN)

def get_ecb_desemprego(lastN=5):
    """Taxa de desemprego da Zona Euro (%)."""
    return get_ecb_serie("LFSI/M.I9.S.UNEHRT.TOTAL0.15_74.T", lastN=lastN)

# Índices europeus via yfinance
INDICES_EUROPA = {
    "DAX (Frankfurt)":   "^GDAXI",
    "CAC 40 (Paris)":    "^FCHI",
    "FTSE 100 (Londres)":"^FTSE",
    "IBEX 35 (Madri)":   "^IBEX",
    "Euro Stoxx 50":     "^STOXX50E",
    "SMI (Suíça)":       "^SSMI",
}


# ── Macro China ───────────────────────────────────────────────────────────────
WB_BASE = "https://api.worldbank.org/v2/country/{code}/indicator/{ind}"
WB_CHINA_INDICATORS = {
    "CPI — Inflação (% a.a.)":         "FP.CPI.TOTL.ZG",
    "PIB — Crescimento Real (% a.a.)": "NY.GDP.MKTP.KD.ZG",
    "Desemprego (% força de trabalho)":"SL.UEM.TOTL.ZS",
    "Balança Comercial (% PIB)":        "BN.CAB.XOKA.GD.ZS",
    "Formação Bruta de Capital (% PIB)":"NE.GDI.TOTL.ZS",
    "Exportações (% PIB)":             "NE.EXP.GNFS.ZS",
}

def get_worldbank(country, indicator, mrv=6):
    """Busca indicador do World Bank API (sem chave, dados anuais)."""
    try:
        url    = WB_BASE.format(code=country, ind=indicator)
        params = {"format": "json", "mrv": mrv, "per_page": mrv}
        r      = requests.get(url, params=params, timeout=12)
        data   = r.json()
        if isinstance(data, list) and len(data) > 1:
            return [
                {"ano": d["date"], "valor": d["value"]}
                for d in data[1]
                if d.get("value") is not None
            ]
    except Exception:
        pass
    return []

# Índices chineses via yfinance
INDICES_CHINA = {
    "Shanghai Composite":  "000001.SS",
    "CSI 300":             "000300.SS",
    "Hang Seng (HK)":      "^HSI",
    "Hang Seng Tech (HK)": "^HSTECH",
}

CNY_PARES = ["CNY", "HKD"]


# ── Treasury Yields via yfinance ──────────────────────────────────────────────
# Yahoo Finance publica yields dos Treasuries em tempo real (valores já em %)
TREASURY_TICKERS_YF = {
    "3 meses":  "^IRX",   # 13-Week T-Bill Yield
    "5 anos":   "^FVX",   # 5-Year T-Note Yield
    "10 anos":  "^TNX",   # 10-Year T-Note Yield
    "30 anos":  "^TYX",   # 30-Year T-Bond Yield
}

def get_treasury_yf():
    """Busca Treasury Yields via yfinance (mais confiável que FRED CSV)."""
    try:
        import yfinance as yf
        rows = []
        for prazo, ticker in TREASURY_TICKERS_YF.items():
            try:
                hist = yf.Ticker(ticker).history(period="5d")
                if not hist.empty:
                    ult = float(hist["Close"].iloc[-1])
                    ant = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
                    var = round(ult - ant, 3) if ant is not None else None
                    rows.append({
                        "Prazo":     prazo,
                        "Yield (%)": round(ult, 3),
                        "Data":      str(hist.index[-1].date()),
                        "_var":      var,
                    })
                else:
                    rows.append({"Prazo": prazo, "Yield (%)": None, "Data": "-", "_var": None})
            except Exception:
                rows.append({"Prazo": prazo, "Yield (%)": None, "Data": "-", "_var": None})
        return rows
    except Exception:
        return []


# ── PMI via Nasdaq Data Link (ex-Quandl) ─────────────────────────────────────
# API gratuita: cadastro em https://data.nasdaq.com/ → My Account → API Key
# Datasets usados:
#   ISM/MAN_PMI    → ISM Manufacturing PMI
#   ISM/NONMAN_NMI → ISM Services NMI (Non-Manufacturing Index)
# Datasets FRED via Nasdaq Data Link (mesmos dados do FRED, host diferente)
# Documentação: https://data.nasdaq.com/data/FRED-federal-reserve-economic-data
NASDAQ_PMI_DATASETS = {
    "ISM Manufacturing PMI": "FRED/NAPM",
    "ISM Services NMI":      "FRED/NMFBAI",
}

def get_nasdaq_pmi(api_key: str, n: int = 3):
    """Busca PMI via Nasdaq Data Link (ex-Quandl). Requer API key gratuita.
    Usa datasets FRED/NAPM e FRED/NMFBAI — disponíveis no plano gratuito.
    Retorna (rows, erros): rows = lista de dicts; erros = lista de strings para debug.
    """
    if not api_key:
        return [], ["API key não configurada."]
    rows  = []
    erros = []
    for nome, dataset in NASDAQ_PMI_DATASETS.items():
        try:
            url    = f"https://data.nasdaq.com/api/v3/datasets/{dataset}.json"
            params = {"api_key": api_key, "rows": n + 1, "order": "desc"}
            r      = requests.get(url, params=params, timeout=15)
            # Captura erro HTTP antes de raise_for_status
            if r.status_code != 200:
                try:
                    msg = r.json().get("quandl_error", {}).get("message", r.text[:200])
                except Exception:
                    msg = r.text[:200]
                erros.append(f"{nome} [{dataset}] HTTP {r.status_code}: {msg}")
                rows.append({"nome": nome, "valor": None, "data": "-", "var": None, "status": "-"})
                continue
            data   = r.json().get("dataset", {})
            cols   = data.get("column_names", [])
            points = data.get("data", [])
            if not points or not cols:
                erros.append(f"{nome} [{dataset}]: resposta vazia (cols={cols}, points={len(points)})")
                rows.append({"nome": nome, "valor": None, "data": "-", "var": None, "status": "-"})
                continue
            # Pega coluna de valor numérico (ignora "Date")
            val_idx = next(
                (i for i, c in enumerate(cols) if c.upper() not in ("DATE", "PERIOD")),
                1  # fallback: segunda coluna
            )
            ult   = points[0]
            ant   = points[1] if len(points) >= 2 else None
            v     = float(ult[val_idx]) if ult[val_idx] is not None else None
            v_ant = float(ant[val_idx]) if ant and ant[val_idx] is not None else None
            var   = round(v - v_ant, 1) if v is not None and v_ant is not None else None
            status = ("🟢 Expansão" if v >= 50 else "🔴 Contração") if v is not None else "-"
            rows.append({
                "nome":   nome,
                "valor":  v,
                "data":   str(ult[0])[:7],
                "var":    var,
                "status": status,
            })
        except Exception as e:
            erros.append(f"{nome} [{dataset}] exceção: {type(e).__name__}: {e}")
            rows.append({"nome": nome, "valor": None, "data": "-", "var": None, "status": "-"})
    return rows, erros


# ── PMI via FRED (fallback — requer acesso a fred.stlouisfed.org) ─────────────
PMI_SERIES = {
    "ISM Manufacturing PMI": "NAPM",
    "ISM Services PMI":      "NMFBAI",
}

def get_fred_csv(series_id, n=10):
    """Busca série do FRED via CSV público (sem API key).
    Requer acesso de rede a fred.stlouisfed.org.
    """
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
            "Referer": "https://fred.stlouisfed.org/",
        }
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        lines  = r.text.strip().split("\n")
        result = []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() not in (".", ""):
                try:
                    result.append({"data": parts[0].strip(), "valor": float(parts[1].strip())})
                except ValueError:
                    continue
        return result[-n:] if result else []
    except Exception:
        return []


# ── PTAX geral (BCB SGS — série 1 = USD, 21619 = EUR) ────────────────────────
def get_ptax(moeda="USD"):
    """Retorna PTAX via BCB SGS (mesma API usada em Macro BR — mais confiável).
    Série 1  = Dólar Americano PTAX (venda, diário)
    Série 21619 = Euro PTAX (venda, diário)
    """
    codigo = 1 if moeda == "USD" else 21619
    dados = get_bcb_serie(codigo, n=7)   # pede 7 dias para garantir dia útil
    if dados:
        for d in reversed(dados):        # do mais recente ao mais antigo
            try:
                v = float(d["valor"].replace(",", "."))
                if v > 0:
                    # Converte "DD/MM/AAAA" → "AAAA-MM-DD" para exibição
                    raw_data = d.get("data", "")
                    try:
                        dt_fmt = datetime.strptime(raw_data, "%d/%m/%Y").strftime("%Y-%m-%d")
                    except Exception:
                        dt_fmt = raw_data
                    return {"compra": v, "venda": v, "data": dt_fmt}
            except Exception:
                continue
    return None


# ── IBOVESPA ──────────────────────────────────────────────────────────────────
def get_ibovespa():
    """Retorna último valor e variação do IBOVESPA via yfinance."""
    try:
        import yfinance as yf
        t     = yf.Ticker("^BVSP")
        info  = t.fast_info
        preco = getattr(info, "last_price", None)
        prev  = getattr(info, "previous_close", None)
        var   = (preco - prev) / prev * 100 if preco and prev else None
        return {"preco": preco, "var": var}
    except Exception:
        return None


# ── Acumulado de taxas mensais ─────────────────────────────────────────────────
def _acumular(valores_pct: list) -> float:
    """Retorna o acumulado composto de uma lista de taxas mensais em %."""
    acum = 1.0
    for v in valores_pct:
        acum *= (1 + v / 100)
    return (acum - 1) * 100


# ══════════════════════════════════════════════════════════════════════════════
# RENDER PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def render():
    st.title("📡 Terminal Financeiro")
    st.markdown("Cotações e indicadores de mercado em tempo real.")

    tab_dash, tab_acoes, tab_cambio, tab_macro_br, tab_cripto, tab_noticias, tab_renda_fixa, tab_macro_eua, tab_europa, tab_china = st.tabs([
        "🏠 Dashboard",
        "📈 Ações",
        "💱 Câmbio",
        "🏦 Macro BR",
        "🟡 Cripto",
        "📰 Notícias",
        "💰 Renda Fixa",
        "🇺🇸 Macro EUA",
        "🇪🇺 Macro Europa",
        "🇨🇳 Macro China",
    ])

    # ── DASHBOARD ─────────────────────────────────────────────────────────────
    with tab_dash:
        st.subheader("🏠 Painel Consolidado")
        st.caption(f"Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

        if st.button("🔄 Atualizar tudo", key="dash_refresh"):
            st.cache_data.clear()

        with st.spinner("Carregando indicadores..."):
            # Câmbio spot
            usd_spot = get_pair_rate("USD", "BRL")
            eur_spot = get_pair_rate("EUR", "BRL")
            # PTAX
            ptax_usd = get_ptax("USD")
            ptax_eur = get_ptax("EUR")
            # Macro BR
            selic_d  = get_bcb_serie(432,  n=2)   # SELIC Meta
            ipca_d   = get_bcb_serie(433,  n=13)  # IPCA mensal
            cdi_d    = get_bcb_serie(4389, n=2)   # CDI
            tlp_d    = get_bcb_serie(27574, n=2)  # TLP
            # Mercado
            ibov     = get_ibovespa()

        st.markdown("---")

        # ── Câmbio ──
        st.markdown("#### 💱 Câmbio")
        c1, c2, c3, c4 = st.columns(4)
        if usd_spot:
            c1.metric("USD/BRL (Spot)",  f"R$ {usd_spot['bid']:.4f}",
                      delta=f"{usd_spot['pct']:+.2f}%")
        if ptax_usd and ptax_usd.get("compra"):
            c2.metric(f"PTAX USD ({ptax_usd['data']})", f"R$ {ptax_usd['compra']:.4f}")
        if eur_spot:
            c3.metric("EUR/BRL (Spot)",  f"R$ {eur_spot['bid']:.4f}",
                      delta=f"{eur_spot['pct']:+.2f}%")
        if ptax_eur and ptax_eur.get("compra"):
            c4.metric(f"PTAX EUR ({ptax_eur['data']})", f"R$ {ptax_eur['compra']:.4f}")

        st.markdown("---")

        # ── Macro Brasil ──
        st.markdown("#### 🏦 Macro Brasil")

        def _ultimo_bcb(serie):
            if serie:
                try:
                    return float(serie[-1]["valor"].replace(",", "."))
                except Exception:
                    return None
            return None

        selic_v = _ultimo_bcb(selic_d)
        cdi_v   = _ultimo_bcb(cdi_d)
        tlp_v   = _ultimo_bcb(tlp_d)

        # IPCA: último mensal + acumulado 12m + acumulado no ano
        ipca_ult = _ultimo_bcb(ipca_d)
        if ipca_d and len(ipca_d) >= 2:
            ipca_vals = [float(d["valor"].replace(",", ".")) for d in ipca_d if d.get("valor")]
            ipca_12m = _acumular(ipca_vals[-12:]) if len(ipca_vals) >= 12 else None
            # Acumulado no ano corrente
            ano_atual = str(datetime.now().year)
            ipca_ano_vals = [
                float(d["valor"].replace(",", "."))
                for d in ipca_d
                if d.get("data", "").endswith(ano_atual)
            ]
            ipca_ytd = _acumular(ipca_ano_vals) if ipca_ano_vals else None
        else:
            ipca_12m = ipca_ytd = None

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("SELIC Meta",    f"{selic_v:.2f}% a.a."  if selic_v else "N/A")
        c2.metric("CDI",           f"{cdi_v:.2f}% a.a."    if cdi_v   else "N/A")
        if ipca_ult is not None:
            c3.metric("IPCA (mês)",    f"{ipca_ult:.2f}%")
        if ipca_ytd is not None:
            c4.metric("IPCA (ano)",    f"{ipca_ytd:.2f}%")
        if ipca_12m is not None:
            c5.metric("IPCA (12m)",    f"{ipca_12m:.2f}%")

        c1b, c2b, c3b = st.columns(3)
        c1b.metric("TLP",           f"{tlp_v:.2f}% a.a."   if tlp_v   else "N/A")

        st.markdown("---")

        # ── Mercado ──
        st.markdown("#### 📈 Mercado")
        c1, c2 = st.columns(2)
        if ibov and ibov.get("preco"):
            c1.metric("IBOVESPA",
                      f"{ibov['preco']:,.0f} pts",
                      delta=f"{ibov['var']:+.2f}%" if ibov.get("var") else None)

    # ── AÇÕES ─────────────────────────────────────────────────────────────────
    with tab_acoes:
        st.subheader("📈 Cotação de Ações")
        st.markdown("Busque qualquer ativo: B3 (`PETR4.SA`, `VALE3.SA`), NYSE/NASDAQ (`AAPL`, `MSFT`, `NVDA`) etc.")

        col_a, col_b = st.columns([2, 1])
        with col_a:
            ticker = st.text_input("Ticker", placeholder="ex: PETR4.SA ou AAPL", key="tf_ticker").upper().strip()
        with col_b:
            periodo = st.selectbox("Histórico", ["5d", "10d", "1mo", "3mo", "6mo", "1y"], index=1, key="tf_periodo")

        if ticker:
            try:
                import yfinance as yf
            except ImportError:
                st.error("Instale yfinance: `pip install yfinance`")
                st.stop()

            with st.spinner(f"Buscando {ticker}..."):
                try:
                    stock = yf.Ticker(ticker)
                    info  = stock.info
                    hist  = stock.history(period=periodo)
                except Exception as e:
                    st.error(f"Erro ao buscar dados: {e}")
                    st.stop()

            nome     = info.get("longName") or info.get("shortName") or ticker
            preco    = info.get("currentPrice") or info.get("regularMarketPrice")
            fechante = info.get("previousClose") or info.get("regularMarketPreviousClose")
            moeda    = info.get("currency", "")

            st.markdown(f"### {nome} `{ticker}`")
            st.caption(f"Setor: {info.get('sector', 'N/A')} · Moeda: {moeda}")

            # Métricas principais
            if preco and fechante:
                var = ((preco - fechante) / fechante) * 100
            else:
                var = None

            def _fmt(v, prefix=""):
                if v is None or v == "N/A": return "N/A"
                try:
                    return f"{prefix}{float(v):,.2f}"
                except Exception:
                    return str(v)

            def _fmt_big(v):
                if v is None: return "N/A"
                try:
                    v = float(v)
                    if v >= 1e12: return f"{v/1e12:.2f} T"
                    if v >= 1e9:  return f"{v/1e9:.2f} B"
                    if v >= 1e6:  return f"{v/1e6:.2f} M"
                    return f"{v:,.0f}"
                except Exception:
                    return str(v)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Preço Atual",   _fmt(preco, moeda+" "),
                      delta=f"{var:+.2f}%" if var is not None else None)
            c2.metric("Abertura",      _fmt(info.get("open") or info.get("regularMarketOpen"), moeda+" "))
            c3.metric("Máx. 52 sem.",  _fmt(info.get("fiftyTwoWeekHigh"), moeda+" "))
            c4.metric("Mín. 52 sem.",  _fmt(info.get("fiftyTwoWeekLow"),  moeda+" "))
            c5.metric("Market Cap",    _fmt_big(info.get("marketCap")))

            c6, c7, c8, _ = st.columns(4)
            c6.metric("P/L",     _fmt(info.get("trailingPE")))
            c7.metric("P/VP",    _fmt(info.get("priceToBook")))
            dy = info.get("dividendYield")
            c8.metric("Div. Yield", f"{float(dy)*100:.2f}%" if dy else "N/A")

            # Gráfico histórico
            if not hist.empty:
                st.markdown("**Evolução do preço — fechamento**")
                st.line_chart(hist[["Close"]], height=250)

                st.markdown("**Histórico recente**")
                df_hist = hist.tail(10).copy().reset_index()
                df_hist["Date"] = pd.to_datetime(df_hist["Date"]).dt.strftime("%d/%m/%Y")
                df_hist = df_hist[["Date", "Open", "Close", "High", "Low", "Volume"]].rename(
                    columns={"Date": "Data", "Open": "Abertura", "Close": "Fechamento",
                             "High": "Máx", "Low": "Mín", "Volume": "Volume"}
                )
                for col in ["Abertura", "Fechamento", "Máx", "Mín"]:
                    df_hist[col] = df_hist[col].apply(lambda x: f"{x:.2f}")
                df_hist["Volume"] = df_hist["Volume"].apply(_fmt_big)
                st.dataframe(df_hist, use_container_width=True, hide_index=True)

    # ── CÂMBIO ────────────────────────────────────────────────────────────────
    with tab_cambio:
        st.subheader("💱 Câmbio em Tempo Real")

        MOEDAS_BRL = ["USD", "EUR", "GBP", "JPY", "ARS", "CAD", "AUD", "CHF"]

        if st.button("🔄 Atualizar cotações", key="tf_cambio_btn"):
            st.cache_data.clear()

        with st.spinner("Buscando cotações..."):
            rows = []
            for m in MOEDAS_BRL:
                d = get_pair_rate(m, "BRL")
                if d:
                    rows.append({
                        "Par":       f"{m}/BRL",
                        "Compra":    d["bid"],
                        "Venda":     d["ask"],
                        "Máx":       d["high"],
                        "Mín":       d["low"],
                        "Var. %":    d["pct"],
                    })

        if rows:
            df_cambio = pd.DataFrame(rows)

            # Métricas USD e EUR em destaque
            usd = next((r for r in rows if r["Par"] == "USD/BRL"), None)
            eur = next((r for r in rows if r["Par"] == "EUR/BRL"), None)
            c1, c2, c3 = st.columns(3)
            if usd:
                c1.metric("USD/BRL", f"R$ {usd['Compra']:.4f}", delta=f"{usd['Var. %']:+.2f}%")
            if eur:
                c2.metric("EUR/BRL", f"R$ {eur['Compra']:.4f}", delta=f"{eur['Var. %']:+.2f}%")
            c3.caption(f"Atualizado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

            st.markdown("**Todas as moedas vs Real**")
            df_show = df_cambio.copy()
            df_show["Compra"] = df_show["Compra"].apply(lambda x: f"R$ {x:.4f}")
            df_show["Venda"]  = df_show["Venda"].apply(lambda x: f"R$ {x:.4f}")
            df_show["Máx"]    = df_show["Máx"].apply(lambda x: f"R$ {x:.4f}")
            df_show["Mín"]    = df_show["Mín"].apply(lambda x: f"R$ {x:.4f}")
            df_show["Var. %"] = df_show["Var. %"].apply(lambda x: f"{'▲' if x>=0 else '▼'} {x:+.2f}%")
            st.dataframe(df_show, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("**Consultar par específico**")
        col_p1, col_p2, col_p3 = st.columns([1, 1, 1])
        with col_p1:
            base_par  = st.text_input("Moeda base", value="EUR", key="tf_base").upper().strip()
        with col_p2:
            quote_par = st.text_input("Moeda destino", value="USD", key="tf_quote").upper().strip()
        with col_p3:
            st.markdown("<br>", unsafe_allow_html=True)
            buscar_par = st.button("🔍 Buscar par", key="tf_buscar_par")

        if buscar_par and base_par and quote_par:
            with st.spinner(f"Buscando {base_par}/{quote_par}..."):
                par = get_pair_rate(base_par, quote_par)
            if par:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(f"{base_par}/{quote_par} Compra", f"{par['bid']:.4f}", delta=f"{par['pct']:+.2f}%")
                c2.metric("Venda",  f"{par['ask']:.4f}")
                c3.metric("Máx",    f"{par['high']:.4f}")
                c4.metric("Mín",    f"{par['low']:.4f}")
            else:
                st.warning(f"Par {base_par}/{quote_par} não encontrado.")

    # ── MACRO BR ──────────────────────────────────────────────────────────────
    with tab_macro_br:
        st.subheader("🏦 Macroeconomia Brasil")
        st.caption("Fonte: Banco Central do Brasil — api.bcb.gov.br")

        if st.button("🔄 Atualizar indicadores", key="tf_macro_btn"):
            st.cache_data.clear()

        ano_atual = str(datetime.now().year)

        # Indicadores que são mensais (suportam acumulado) vs anuais (não acumulam)
        SERIES_MENSAIS = {433, 188, 189}  # IPCA, INPC, IGP-M

        with st.spinner("Buscando indicadores do BCB..."):
            macro_rows = []
            for nome_ind, codigo in SERIES_BCB.items():
                # Busca 14 meses para cobrir acumulado do ano + 12m
                dados = get_bcb_serie(codigo, n=14)
                if dados and len(dados) >= 1:
                    ultimo   = dados[-1]
                    anterior = dados[-2] if len(dados) >= 2 else None
                    try:
                        v = float(ultimo["valor"].replace(",", "."))
                        a = float(anterior["valor"].replace(",", ".")) if anterior else None
                        var = round(v - a, 4) if a is not None else None
                    except Exception:
                        v, a, var = None, None, None

                    # Acumulado: só faz sentido para séries mensais de taxa
                    acum_ano = acum_12m = None
                    if codigo in SERIES_MENSAIS and v is not None:
                        try:
                            vals_todos = [float(d["valor"].replace(",", ".")) for d in dados if d.get("valor")]
                            vals_ano   = [
                                float(d["valor"].replace(",", "."))
                                for d in dados
                                if d.get("data", "").endswith(ano_atual) and d.get("valor")
                            ]
                            if vals_ano:
                                acum_ano = round(_acumular(vals_ano), 4)
                            if len(vals_todos) >= 12:
                                acum_12m = round(_acumular(vals_todos[-12:]), 4)
                        except Exception:
                            pass

                    macro_rows.append({
                        "Indicador":    nome_ind,
                        "Último":       v,
                        "Data":         ultimo.get("data", ""),
                        "Anterior":     a,
                        "Variação":     var,
                        "Acum. Ano":    acum_ano,
                        "Acum. 12m":    acum_12m,
                    })

        if macro_rows:
            # Métricas em destaque
            selic_row = next((r for r in macro_rows if "SELIC Meta" in r["Indicador"]), None)
            ipca_row  = next((r for r in macro_rows if "IPCA" in r["Indicador"]), None)
            cdi_row   = next((r for r in macro_rows if "CDI" in r["Indicador"]), None)
            c1, c2, c3, c4, c5 = st.columns(5)
            if selic_row and selic_row["Último"]:
                c1.metric("SELIC Meta", f"{selic_row['Último']:.2f}% a.a.",
                          delta=f"{selic_row['Variação']:+.4f}" if selic_row["Variação"] else None)
            if cdi_row and cdi_row["Último"]:
                c2.metric("CDI", f"{cdi_row['Último']:.2f}% a.a.")
            if ipca_row and ipca_row["Último"]:
                c3.metric("IPCA (mês)", f"{ipca_row['Último']:.2f}%",
                          delta=f"{ipca_row['Variação']:+.4f}" if ipca_row["Variação"] else None)
            if ipca_row and ipca_row["Acum. Ano"]:
                c4.metric("IPCA (ano)", f"{ipca_row['Acum. Ano']:.2f}%")
            if ipca_row and ipca_row["Acum. 12m"]:
                c5.metric("IPCA (12m)", f"{ipca_row['Acum. 12m']:.2f}%")

            st.markdown("**Todos os indicadores**")
            df_macro = pd.DataFrame(macro_rows)

            def _fmt_val(x):
                return f"{x:.4f}" if x is not None else "—"
            def _fmt_var(x):
                if x is None: return "—"
                return f"{'▲' if x>=0 else '▼'} {x:+.4f}"
            def _fmt_acum(x):
                return f"{x:.2f}%" if x is not None else "—"

            df_macro["Último"]     = df_macro["Último"].apply(_fmt_val)
            df_macro["Anterior"]   = df_macro["Anterior"].apply(_fmt_val)
            df_macro["Variação"]   = df_macro["Variação"].apply(_fmt_var)
            df_macro["Acum. Ano"]  = df_macro["Acum. Ano"].apply(_fmt_acum)
            df_macro["Acum. 12m"]  = df_macro["Acum. 12m"].apply(_fmt_acum)

            cols_show = ["Indicador", "Último", "Data", "Anterior", "Variação", "Acum. Ano", "Acum. 12m"]
            st.dataframe(df_macro[cols_show], use_container_width=True, hide_index=True)

            # IPCA histórico — 12 meses
            st.markdown("**IPCA Mensal — últimos 12 meses**")
            with st.spinner("Carregando histórico IPCA..."):
                ipca_hist = get_bcb_serie(433, n=12)
            if ipca_hist:
                df_ipca = pd.DataFrame([
                    {"Mês": i["data"],
                     "IPCA (%)": float(i["valor"].replace(",", "."))}
                    for i in ipca_hist if i.get("valor")
                ])
                st.bar_chart(df_ipca.set_index("Mês"), height=250)

    # ── CRIPTO ────────────────────────────────────────────────────────────────
    with tab_cripto:
        st.subheader("🟡 Criptomoedas")
        st.caption(f"Fonte: CoinGecko · Atualizado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

        if st.button("🔄 Atualizar", key="tf_cripto_btn"):
            st.cache_data.clear()

        with st.spinner("Buscando cotações cripto..."):
            dados_cripto = get_cripto()

        if dados_cripto:
            rows_cripto = []
            for coin_id, nome_c in CRIPTO_NOMES.items():
                d = dados_cripto.get(coin_id, {})
                if not d:
                    continue
                usd  = d.get("usd", 0)
                brl  = d.get("brl", 0)
                chg  = d.get("usd_24h_change") or 0
                mkt  = d.get("usd_market_cap", 0)

                def fmt_mkt(v):
                    try:
                        v = float(v)
                        if v >= 1e12: return f"$ {v/1e12:.2f}T"
                        if v >= 1e9:  return f"$ {v/1e9:.2f}B"
                        if v >= 1e6:  return f"$ {v/1e6:.2f}M"
                        return f"$ {v:,.0f}"
                    except Exception:
                        return "N/A"

                rows_cripto.append({
                    "Ativo":          nome_c,
                    "USD":            f"$ {usd:,.2f}" if usd >= 1 else f"$ {usd:.6f}",
                    "BRL":            f"R$ {brl:,.2f}" if brl >= 1 else f"R$ {brl:.6f}",
                    "Var. 24h":       f"{'▲' if chg>=0 else '▼'} {chg:+.2f}%",
                    "Market Cap":     fmt_mkt(mkt),
                    "_chg":           chg,
                })

            # BTC e ETH em destaque
            btc = dados_cripto.get("bitcoin", {})
            eth = dados_cripto.get("ethereum", {})
            c1, c2, c3 = st.columns(3)
            if btc:
                c1.metric("Bitcoin (BTC)", f"$ {btc.get('usd',0):,.2f}",
                          delta=f"{btc.get('usd_24h_change',0):+.2f}%")
            if eth:
                c2.metric("Ethereum (ETH)", f"$ {eth.get('usd',0):,.2f}",
                          delta=f"{eth.get('usd_24h_change',0):+.2f}%")

            df_cripto = pd.DataFrame([{k: v for k, v in r.items() if k != "_chg"} for r in rows_cripto])
            st.dataframe(df_cripto, use_container_width=True, hide_index=True)
        else:
            st.warning("Não foi possível obter dados da CoinGecko. Tente novamente.")

    # ── NOTÍCIAS ──────────────────────────────────────────────────────────────
    with tab_noticias:
        st.subheader("📰 Notícias Financeiras")
        st.caption(f"Atualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

        if st.button("🔄 Recarregar notícias", key="tf_noticias_btn"):
            st.cache_data.clear()

        with st.spinner("Buscando notícias..."):
            todas_noticias = []
            for url, fonte in FEEDS:
                todas_noticias.extend(get_noticias_rss(url, fonte, n=5))

        if todas_noticias:
            # Filtro por fonte
            fontes_disp = sorted({n["fonte"] for n in todas_noticias})
            fonte_sel = st.multiselect("Filtrar por fonte", fontes_disp, default=fontes_disp, key="tf_fonte_sel")
            filtradas = [n for n in todas_noticias if n["fonte"] in fonte_sel]

            for noticia in filtradas:
                with st.container():
                    col_n1, col_n2 = st.columns([4, 1])
                    with col_n1:
                        st.markdown(f"**[{noticia['titulo']}]({noticia['link']})**")
                        st.caption(f"{noticia['desc']}")
                    with col_n2:
                        st.caption(f"🗞 {noticia['fonte']}")
                        st.caption(noticia["data"])
                    st.divider()
        else:
            st.warning("Não foi possível carregar notícias no momento. Verifique sua conexão.")

    # ── RENDA FIXA ────────────────────────────────────────────────────────────
    with tab_renda_fixa:
        st.subheader("💰 Renda Fixa Brasil")

        if st.button("🔄 Atualizar", key="tf_rf_btn"):
            st.cache_data.clear()

        with st.spinner("Buscando dados..."):
            selic   = get_bcb_selic()
            titulos = get_tesouro_direto()

        if selic:
            c1, c2, c3 = st.columns(3)
            c1.metric("SELIC Meta", f"{selic:.2f}% a.a.")
            c2.metric("CDI (aprox.)", f"{selic - 0.1:.2f}% a.a.")
            c3.metric("Poupança (aprox.)", f"{selic * 0.7:.2f}% a.a." if selic > 8.5 else f"{selic * 0.7:.2f}% a.a.")

        if titulos:
            st.markdown("**Tesouro Direto — Títulos Disponíveis**")
            rows_td = []
            for t in titulos:
                bond = t.get("TrsrBd", {})
                try:
                    rows_td.append({
                        "Título":            bond.get("nm", "N/A"),
                        "Vencimento":        (bond.get("mtrtyDt") or "")[:10],
                        "Taxa Compra (%)":   float(bond.get("anulInvstmtRate", 0)),
                        "Preço Compra (R$)": float(bond.get("untrInvstmtVal", 0)),
                        "Preço Venda (R$)":  float(bond.get("untrRedVal", 0)),
                        "Mín. Invest. (R$)": float(bond.get("minInvstmtAmt", 0)),
                    })
                except Exception:
                    continue

            if rows_td:
                df_td = pd.DataFrame(rows_td).sort_values("Taxa Compra (%)", ascending=False)
                df_td_show = df_td.copy()
                df_td_show["Taxa Compra (%)"]   = df_td_show["Taxa Compra (%)"].apply(lambda x: f"{x:.2f}%")
                df_td_show["Preço Compra (R$)"] = df_td_show["Preço Compra (R$)"].apply(lambda x: f"R$ {x:,.2f}")
                df_td_show["Preço Venda (R$)"]  = df_td_show["Preço Venda (R$)"].apply(lambda x: f"R$ {x:,.2f}")
                df_td_show["Mín. Invest. (R$)"] = df_td_show["Mín. Invest. (R$)"].apply(lambda x: f"R$ {x:,.2f}")
                st.dataframe(df_td_show, use_container_width=True, hide_index=True)

        st.info(
            "**Referências:** CDI é a base para fundos e CDB (~SELIC). "
            "Tesouro IPCA+ oferece proteção contra inflação. "
            "Tesouro Prefixado trava a taxa. Tesouro Selic é o mais conservador."
        )

    # ── MACRO EUA ─────────────────────────────────────────────────────────────
    with tab_macro_eua:
        st.subheader("🇺🇸 Macroeconomia EUA")
        st.caption("Fonte: Bureau of Labor Statistics (bls.gov)")

        if st.button("🔄 Atualizar dados do BLS", key="tf_bls_btn"):
            st.cache_data.clear()

        with st.spinner("Buscando dados do BLS (pode demorar alguns segundos)..."):
            series_map = get_bls_data(years=2)

        if not series_map:
            st.warning("Não foi possível obter dados do BLS. Tente novamente.")
            return

        def parse_serie(sid):
            s = series_map.get(sid)
            if not s:
                return None, None, None, None
            dados = s.get("data", [])
            if not dados:
                return None, None, None, None
            u = dados[0]
            a = dados[1] if len(dados) >= 2 else None
            try:
                v = float(u["value"])
                periodo = f"{u['periodName']} {u['year']}"
                v_ant = float(a["value"]) if a else None
                return v, periodo, v_ant, s
            except Exception:
                return None, None, None, None

        # ── CPI ──
        st.markdown("### 📊 CPI — Inflação Americana")
        cpi_ids = {
            "CPI-U (All Urban)":   "CUSR0000SA0",
            "CPI Core":            "CUSR0000SA0L1E",
            "CPI Food":            "CUSR0000SAF1",
            "CPI Energy":          "CUSR0000SA0E",
        }

        cpi_rows = []
        for nome_cpi, sid in cpi_ids.items():
            v, periodo, v_ant, serie_raw = parse_serie(sid)
            if v is None:
                cpi_rows.append({"Indicador": nome_cpi, "Índice": "N/A", "Período": "-", "MoM": "-", "YoY": "-"})
                continue
            mom = ((v - v_ant) / v_ant * 100) if v_ant else None
            dados_raw = serie_raw.get("data", []) if serie_raw else []
            yoy = ((v - float(dados_raw[12]["value"])) / float(dados_raw[12]["value"]) * 100) \
                  if len(dados_raw) >= 13 else None
            cpi_rows.append({
                "Indicador": nome_cpi,
                "Índice":    f"{v:.3f}",
                "Período":   periodo or "-",
                "MoM":       f"{'▲' if mom>=0 else '▼'} {mom:+.2f}%" if mom is not None else "-",
                "YoY":       f"{'▲' if yoy>=0 else '▼'} {yoy:+.2f}%" if yoy is not None else "-",
            })

        st.dataframe(pd.DataFrame(cpi_rows), use_container_width=True, hide_index=True)
        st.info("**Meta do Fed:** 2,0% YoY. 🟢 ≤ 2% dentro da meta · 🟡 2–3,5% acima · 🔴 > 3,5% alerta.")

        # ── Payroll ──
        st.markdown("### 👷 Non-Farm Payroll — Emprego nos EUA")
        payroll_ids = {
            "NFP Total":           "CES0000000001",
            "NFP Setor Privado":   "CES0500000001",
            "NFP Manufatura":      "CES3000000001",
            "Desemprego (%)":      "LNS14000000",
            "Rend. Hora Médio ($)":"CES0500000003",
        }

        pay_rows = []
        for nome_pay, sid in payroll_ids.items():
            v, periodo, v_ant, _ = parse_serie(sid)
            if v is None:
                pay_rows.append({"Indicador": nome_pay, "Valor": "N/A", "Período": "-", "Variação": "-"})
                continue
            if sid == "LNS14000000":
                val_str = f"{v:.1f}%"
                var_str = f"{'▲' if (v-v_ant)>=0 else '▼'} {v-v_ant:+.1f}pp" if v_ant else "-"
            elif sid == "CES0500000003":
                val_str = f"$ {v:.2f}"
                var_str = f"{'▲' if (v-v_ant)>=0 else '▼'} {v-v_ant:+.2f}" if v_ant else "-"
            else:
                val_str = f"{v:,.0f}K"
                var_str = f"{'▲' if (v-v_ant)>=0 else '▼'} {v-v_ant:+,.0f}K" if v_ant else "-"
            pay_rows.append({"Indicador": nome_pay, "Valor": val_str, "Período": periodo, "Variação": var_str})

        st.dataframe(pd.DataFrame(pay_rows), use_container_width=True, hide_index=True)
        st.info(
            "**Como interpretar NFP:** "
            "▲ > 200K = mercado forte (pressão de alta nos juros) · "
            "100–200K = crescimento moderado · "
            "< 100K = desaceleração."
        )

        # ── PMI ──
        st.markdown("### 🏭 PMI — Índice de Gerentes de Compras")

        # ── Configuração de API key (Nasdaq Data Link) ──
        with st.expander("⚙️ Configurar fonte de dados do PMI", expanded=False):
            st.markdown(
                "O PMI do ISM está disponível gratuitamente via **Nasdaq Data Link** (ex-Quandl). "
                "Crie sua conta em [data.nasdaq.com](https://data.nasdaq.com/) → "
                "*My Account* → *API Key* e cole abaixo."
            )
            _saved_key = get_cfg("nasdaq_api_key") or ""
            _col_key, _col_btn = st.columns([4, 1])
            with _col_key:
                _input_key = st.text_input(
                    "Nasdaq Data Link API Key",
                    value=_saved_key,
                    type="password",
                    placeholder="sua_api_key_aqui",
                    key="nasdaq_key_input",
                )
            with _col_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾 Salvar", key="nasdaq_save_btn"):
                    set_cfg("nasdaq_api_key", _input_key.strip())
                    st.success("Chave salva!")
                    st.rerun()

        # ── Busca: Nasdaq → FRED → aviso ──
        nasdaq_key = get_cfg("nasdaq_api_key") or ""
        _pmi_fonte = None
        pmi_rows   = []

        if nasdaq_key:
            st.caption("Fonte: Nasdaq Data Link (FRED/NAPM · FRED/NMFBAI)")
            with st.spinner("Buscando PMI via Nasdaq Data Link..."):
                nasdaq_data, nasdaq_erros = get_nasdaq_pmi(nasdaq_key, n=3)
            if nasdaq_data and any(r["valor"] is not None for r in nasdaq_data):
                _pmi_fonte = "nasdaq"
                for r in nasdaq_data:
                    v   = r["valor"]
                    var = r["var"]
                    pmi_rows.append({
                        "Índice":   r["nome"],
                        "Valor":    f"{v:.1f}" if v is not None else "N/A",
                        "Período":  r["data"],
                        "Variação": f"{'▲' if var and var>=0 else '▼'} {var:+.1f}" if var is not None else "-",
                        "Status":   r["status"],
                    })
            elif nasdaq_erros:
                with st.expander("🔍 Diagnóstico do erro Nasdaq", expanded=True):
                    for e in nasdaq_erros:
                        st.code(e)

        if _pmi_fonte is None:
            # Fallback: FRED
            st.caption("Fonte: FRED / ISM (fallback)")
            with st.spinner("Buscando PMI via FRED..."):
                _pmi_ok = False
                for nome_pmi, sid_pmi in PMI_SERIES.items():
                    dados_pmi = get_fred_csv(sid_pmi, n=3)
                    if dados_pmi:
                        _pmi_ok = True
                        ult_pmi = dados_pmi[-1]
                        ant_pmi = dados_pmi[-2] if len(dados_pmi) >= 2 else None
                        var_pmi = round(ult_pmi["valor"] - ant_pmi["valor"], 1) if ant_pmi else None
                        status  = "🟢 Expansão" if ult_pmi["valor"] >= 50 else "🔴 Contração"
                        pmi_rows.append({
                            "Índice":   nome_pmi,
                            "Valor":    f"{ult_pmi['valor']:.1f}",
                            "Período":  ult_pmi["data"][:7],
                            "Variação": f"{'▲' if var_pmi and var_pmi>=0 else '▼'} {var_pmi:+.1f}" if var_pmi is not None else "-",
                            "Status":   status,
                        })
                    else:
                        pmi_rows.append({"Índice": nome_pmi, "Valor": "N/A", "Período": "-", "Variação": "-", "Status": "-"})
                if _pmi_ok:
                    _pmi_fonte = "fred"

        if _pmi_fonte:
            cols_pmi = st.columns(len(pmi_rows))
            for i, row in enumerate(pmi_rows):
                cols_pmi[i].metric(
                    row["Índice"].replace("ISM ", ""),
                    row["Valor"],
                    delta=row["Variação"] if row["Variação"] != "-" else None,
                )
            st.dataframe(pd.DataFrame(pmi_rows), use_container_width=True, hide_index=True)
            st.info("**PMI/NMI:** Acima de 50 = expansão econômica · Abaixo de 50 = contração.")
        else:
            st.warning(
                "⚠️ Não foi possível obter PMI. "
                "Configure uma **API key gratuita do Nasdaq Data Link** acima, "
                "ou verifique se `fred.stlouisfed.org` está acessível na sua rede."
            )

        # ── Treasury Yields ──
        st.markdown("### 📉 Treasury Yields — Juros dos Títulos do Tesouro dos EUA")
        st.caption("Fonte: Yahoo Finance (yfinance) — ^IRX · ^FVX · ^TNX · ^TYX")
        with st.spinner("Buscando Treasury Yields..."):
            raw_yields = get_treasury_yf()

        yield_rows = []
        for r in raw_yields:
            v   = r["Yield (%)"]
            var = r["_var"]
            yield_rows.append({
                "Prazo":     r["Prazo"],
                "Yield (%)": f"{v:.3f}%" if v is not None else "N/A",
                "Data":      r["Data"],
                "Variação":  f"{'▲' if var and var>=0 else '▼'} {var:+.3f}pp" if var is not None else "-",
                "_num":      v,
            })

        if yield_rows:
            # Métricas em linha
            cols_yld = st.columns(len(yield_rows))
            for i, row in enumerate(yield_rows):
                cols_yld[i].metric(f"T-{row['Prazo']}", row["Yield (%)"])

            # Curva de juros (yield curve)
            yld_vals = [(r["Prazo"], r["_num"]) for r in yield_rows if r["_num"] is not None]
            if yld_vals:
                df_curve = pd.DataFrame(yld_vals, columns=["Prazo", "Yield (%)"])
                st.markdown("**Curva de Juros (Yield Curve)**")
                st.line_chart(df_curve.set_index("Prazo"), height=220)
                if yld_vals[0][1] > yld_vals[-1][1]:
                    st.warning("⚠️ Curva invertida — historicamente associada a recessões.")

            df_yld_show = pd.DataFrame([{k: v for k, v in r.items() if k != "_num"} for r in yield_rows])
            st.dataframe(df_yld_show, use_container_width=True, hide_index=True)
        else:
            st.warning("Não foi possível obter Treasury Yields. Tente novamente.")

    # ── MACRO EUROPA ──────────────────────────────────────────────────────────
    with tab_europa:
        st.subheader("🇪🇺 Macroeconomia Europa")
        st.caption("Fontes: BCE (sdw-wsrest.ecb.europa.eu) · yfinance")

        if st.button("🔄 Atualizar", key="tf_eu_btn"):
            st.cache_data.clear()

        # ── Taxas BCE ──
        st.markdown("### 🏦 Taxas de Juros do BCE")
        with st.spinner("Buscando taxas do BCE..."):
            taxas_rows = []
            for nome_taxa, flow_key in ECB_TAXAS.items():
                serie = get_ecb_serie(flow_key, lastN=2)
                if serie:
                    ultimo   = serie[-1]
                    anterior = serie[-2] if len(serie) >= 2 else None
                    var = round(ultimo["valor"] - anterior["valor"], 4) if anterior else None
                    taxas_rows.append({
                        "Taxa":      nome_taxa,
                        "Valor":     f"{ultimo['valor']:.2f}%",
                        "Período":   ultimo["periodo"],
                        "Variação":  f"{'▲' if var >= 0 else '▼'} {var:+.2f}pp" if var is not None else "-",
                    })
                else:
                    taxas_rows.append({"Taxa": nome_taxa, "Valor": "N/A", "Período": "-", "Variação": "-"})

        if taxas_rows:
            # Métricas em destaque
            c1, c2, c3 = st.columns(3)
            for i, row in enumerate(taxas_rows[:3]):
                [c1, c2, c3][i].metric(row["Taxa"], row["Valor"])
            st.dataframe(pd.DataFrame(taxas_rows), use_container_width=True, hide_index=True)

        # ── HICP ──
        st.markdown("### 📊 HICP — Inflação da Zona Euro")
        with st.spinner("Buscando HICP..."):
            hicp = get_ecb_hicp(lastN=13)

        if hicp:
            ultimo_hicp   = hicp[-1]
            anterior_hicp = hicp[-2] if len(hicp) >= 2 else None
            var_hicp = round(ultimo_hicp["valor"] - anterior_hicp["valor"], 4) if anterior_hicp else None
            c1, c2 = st.columns(2)
            c1.metric("HICP (último)", f"{ultimo_hicp['valor']:.2f}%",
                      delta=f"{var_hicp:+.2f}pp" if var_hicp is not None else None)
            c2.metric("Período", ultimo_hicp["periodo"])

            df_hicp = pd.DataFrame(hicp[-12:])
            df_hicp.columns = ["Período", "HICP (%)"]
            st.bar_chart(df_hicp.set_index("Período"), height=220)
        else:
            st.warning("Não foi possível carregar dados de inflação do BCE.")

        # ── Desemprego ──
        st.markdown("### 👷 Desemprego — Zona Euro")
        with st.spinner("Buscando desemprego..."):
            desemp = get_ecb_desemprego(lastN=3)
        if desemp:
            ult_d = desemp[-1]
            st.metric("Taxa de Desemprego", f"{ult_d['valor']:.1f}%",
                      delta=f"{ult_d['valor'] - desemp[-2]['valor']:+.1f}pp" if len(desemp) >= 2 else None)
        else:
            st.info("Dado de desemprego indisponível no momento.")

        # ── Índices europeus ──
        st.markdown("### 📈 Principais Índices Europeus")
        with st.spinner("Buscando índices..."):
            try:
                import yfinance as yf
                idx_rows = []
                for nome_idx, ticker_idx in INDICES_EUROPA.items():
                    try:
                        t    = yf.Ticker(ticker_idx)
                        info = t.fast_info
                        preco_idx = getattr(info, "last_price", None)
                        prev_close = getattr(info, "previous_close", None)
                        if preco_idx and prev_close:
                            var_idx = (preco_idx - prev_close) / prev_close * 100
                        else:
                            var_idx = None
                        idx_rows.append({
                            "Índice":  nome_idx,
                            "Último":  f"{preco_idx:,.2f}" if preco_idx else "N/A",
                            "Var. %":  f"{'▲' if var_idx and var_idx>=0 else '▼'} {var_idx:+.2f}%" if var_idx is not None else "-",
                        })
                    except Exception:
                        idx_rows.append({"Índice": nome_idx, "Último": "N/A", "Var. %": "-"})

                if idx_rows:
                    # Linha de métricas para DAX e CAC
                    top = idx_rows[:4]
                    cols_idx = st.columns(len(top))
                    for i, row in enumerate(top):
                        cols_idx[i].metric(row["Índice"].split(" ")[0], row["Último"], delta=row["Var. %"] if row["Var. %"] != "-" else None)
                    st.dataframe(pd.DataFrame(idx_rows), use_container_width=True, hide_index=True)
            except ImportError:
                st.warning("yfinance não instalado — índices indisponíveis.")

        # ── EUR ──
        st.markdown("### 💱 Euro — Principais Pares")
        with st.spinner("Buscando EUR..."):
            eur_pares = [("EUR", "USD"), ("EUR", "BRL"), ("EUR", "GBP"), ("GBP", "USD")]
            eur_rows = []
            for base, quote in eur_pares:
                d = get_pair_rate(base, quote)
                if d:
                    eur_rows.append({
                        "Par":    f"{base}/{quote}",
                        "Compra": f"{d['bid']:.4f}",
                        "Venda":  f"{d['ask']:.4f}",
                        "Var. %": f"{'▲' if d['pct']>=0 else '▼'} {d['pct']:+.2f}%",
                    })
        if eur_rows:
            cols_e = st.columns(len(eur_rows))
            for i, row in enumerate(eur_rows):
                cols_e[i].metric(row["Par"], row["Compra"])

    # ── MACRO CHINA ───────────────────────────────────────────────────────────
    with tab_china:
        st.subheader("🇨🇳 Macroeconomia China")
        st.caption("Fontes: World Bank API (dados anuais) · AwesomeAPI (câmbio) · yfinance (índices)")

        if st.button("🔄 Atualizar", key="tf_cn_btn"):
            st.cache_data.clear()

        # ── Indicadores World Bank ──
        st.markdown("### 📊 Indicadores Macroeconômicos")
        st.info("ℹ️ Dados do World Bank são anuais — última leitura disponível pode ser do ano anterior.")

        with st.spinner("Buscando indicadores da China (World Bank)..."):
            wb_rows = []
            for nome_wb, ind_wb in WB_CHINA_INDICATORS.items():
                dados_wb = get_worldbank("CN", ind_wb, mrv=3)
                if dados_wb:
                    ult   = dados_wb[0]
                    ant   = dados_wb[1] if len(dados_wb) >= 2 else None
                    var   = round(ult["valor"] - ant["valor"], 2) if ant else None
                    wb_rows.append({
                        "Indicador": nome_wb,
                        "Valor":     f"{ult['valor']:.2f}%",
                        "Ano":       ult["ano"],
                        "Anterior":  f"{ant['valor']:.2f}%" if ant else "-",
                        "Variação":  f"{'▲' if var >= 0 else '▼'} {var:+.2f}pp" if var is not None else "-",
                    })
                else:
                    wb_rows.append({"Indicador": nome_wb, "Valor": "N/A", "Ano": "-", "Anterior": "-", "Variação": "-"})

        if wb_rows:
            # Destaque PIB e CPI
            pib_row = next((r for r in wb_rows if "PIB" in r["Indicador"]), None)
            cpi_row = next((r for r in wb_rows if "CPI" in r["Indicador"]), None)
            des_row = next((r for r in wb_rows if "Desemprego" in r["Indicador"]), None)
            c1, c2, c3 = st.columns(3)
            if pib_row: c1.metric("PIB China",      pib_row["Valor"])
            if cpi_row: c2.metric("Inflação (CPI)", cpi_row["Valor"])
            if des_row: c3.metric("Desemprego",     des_row["Valor"])
            st.dataframe(pd.DataFrame(wb_rows), use_container_width=True, hide_index=True)

            # Gráfico PIB histórico
            st.markdown("**PIB China — Crescimento Anual (%)**")
            with st.spinner("Carregando histórico PIB..."):
                pib_hist = get_worldbank("CN", "NY.GDP.MKTP.KD.ZG", mrv=15)
            if pib_hist:
                df_pib = pd.DataFrame(pib_hist[::-1])
                df_pib.columns = ["Ano", "PIB (%)"]
                st.bar_chart(df_pib.set_index("Ano"), height=220)

        # ── Índices chineses ──
        st.markdown("### 📈 Principais Índices da China")
        with st.spinner("Buscando índices chineses..."):
            try:
                import yfinance as yf
                cn_rows = []
                for nome_cn, ticker_cn in INDICES_CHINA.items():
                    try:
                        t     = yf.Ticker(ticker_cn)
                        info  = t.fast_info
                        preco_cn   = getattr(info, "last_price", None)
                        prev_cn    = getattr(info, "previous_close", None)
                        var_cn = (preco_cn - prev_cn) / prev_cn * 100 if preco_cn and prev_cn else None
                        cn_rows.append({
                            "Índice":  nome_cn,
                            "Último":  f"{preco_cn:,.2f}" if preco_cn else "N/A",
                            "Var. %":  f"{'▲' if var_cn and var_cn>=0 else '▼'} {var_cn:+.2f}%" if var_cn is not None else "-",
                        })
                    except Exception:
                        cn_rows.append({"Índice": nome_cn, "Último": "N/A", "Var. %": "-"})

                if cn_rows:
                    cols_cn = st.columns(len(cn_rows))
                    for i, row in enumerate(cn_rows):
                        cols_cn[i].metric(row["Índice"].split(" ")[0], row["Último"])
                    st.dataframe(pd.DataFrame(cn_rows), use_container_width=True, hide_index=True)
            except ImportError:
                st.warning("yfinance não instalado — índices indisponíveis.")

        # ── CNY Câmbio ──
        st.markdown("### 💱 Yuan — Principais Pares")
        with st.spinner("Buscando CNY..."):
            cny_rows = []
            for moeda in CNY_PARES:
                d = get_pair_rate(moeda, "BRL")
                if d:
                    cny_rows.append({
                        "Par":    f"{moeda}/BRL",
                        "Compra": f"R$ {d['bid']:.4f}",
                        "Venda":  f"R$ {d['ask']:.4f}",
                        "Var. %": f"{'▲' if d['pct']>=0 else '▼'} {d['pct']:+.2f}%",
                    })
            # CNY/USD via par invertido
            d_usd = get_pair_rate("USD", "CNY")
            if d_usd:
                cny_rows.append({
                    "Par":    "USD/CNY",
                    "Compra": f"¥ {d_usd['bid']:.4f}",
                    "Venda":  f"¥ {d_usd['ask']:.4f}",
                    "Var. %": f"{'▲' if d_usd['pct']>=0 else '▼'} {d_usd['pct']:+.2f}%",
                })

        if cny_rows:
            cols_cny = st.columns(min(len(cny_rows), 3))
            for i, row in enumerate(cny_rows[:3]):
                cols_cny[i].metric(row["Par"], row["Compra"])
            st.dataframe(pd.DataFrame(cny_rows), use_container_width=True, hide_index=True)
