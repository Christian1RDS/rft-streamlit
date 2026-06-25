
import io
import sqlite3
from datetime import datetime, date, time, timedelta
from calendar import monthrange

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    from streamlit_local_storage import LocalStorage
except Exception:
    LocalStorage = None

st.set_page_config(page_title="RFT Automático - V9.9.1", page_icon="R", layout="wide")

DB = "rft_v991_local.db"
POSTOS = ["QG09", "QG07"]
REQ = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO", "CD_POSTO_CN"]
FALHA_CANDIDATES = [
    "FALHA", "DEFEITO", "DS_DEFEITO", "NM_DEFEITO", "TIPO_FALHA", "DESCRICAO_DEFEITO",
    "DESCRIÇÃO_DEFEITO", "DESC_DEFEITO", "NOME_FALHA", "DS_FALHA", "NM_FALHA",
    "TIPO_DEFEITO", "CAUSA", "DESCRICAO", "DESCRIÇÃO", "OBS_DEFEITO", "PROBLEMA"
]
YEAR_CLOSE_DAY = 10

CSS = """
<style>
:root { --line:rgba(148,163,184,.18); --txt:#e5e7eb; --muted:#94a3b8; --ok:#22c55e; --bad:#ef4444; }
html, body, [data-testid="stAppViewContainer"], .stApp { background: radial-gradient(circle at top left, #13213d 0%, #0b1220 35%, #09101c 100%); color: var(--txt); }
[data-testid="stHeader"] { background: rgba(11,18,32,.76); border-bottom: 1px solid var(--line); }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#0f172a 0%, #101827 100%); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] * { color: var(--txt) !important; }
.block-container { padding-top: .8rem; padding-bottom: 2rem; }
h1,h2,h3,h4,h5,h6,p,label,div,span { color: var(--txt); }
.hero { background: linear-gradient(135deg, rgba(24,34,53,.97), rgba(16,24,40,.98)); border:1px solid var(--line); border-radius:22px; padding:1.15rem 1.25rem; box-shadow:0 12px 36px rgba(0,0,0,.24); margin-bottom:1rem; }
.panel { background: linear-gradient(180deg, rgba(34,48,73,.96), rgba(21,31,47,.98)); border:1px solid var(--line); border-radius:18px; padding:1rem; box-shadow:0 10px 30px rgba(0,0,0,.18); margin-bottom:1rem; }
.small { color: var(--muted); font-size:.86rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ---------------- DB ----------------
def conn():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db(c):
    c.execute("""
    CREATE TABLE IF NOT EXISTS upload_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT,
        uploaded_at TEXT,
        total_rows INTEGER,
        status TEXT,
        message TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS raw_inspections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        upload_id INTEGER,
        nr_wo TEXT,
        dt_hr_inspecao TEXT,
        c_dpu_qg_amarelo REAL,
        cd_posto_cn TEXT,
        falha TEXT
    )
    """)
    c.commit()

def create_upload(c, file_name, rows, status="PROCESSADO", message=""):
    cur = c.execute(
        "INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)",
        (file_name, datetime.now().isoformat(timespec="seconds"), int(rows), status, message),
    )
    c.commit()
    return int(cur.lastrowid)

def save_raw(c, upload_id, df):
    rows = []
    for _, r in df.iterrows():
        rows.append((
            upload_id,
            str(r["NR_WO"]),
            r["DT_HR_INSPECAO"].isoformat(sep=" ", timespec="seconds"),
            float(r["C_DPU_QG_AMARELO"]),
            r["CD_POSTO_CN"],
            r.get("FALHA_PARETO", ""),
        ))
    c.executemany(
        "INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn, falha) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    c.commit()

def delete_period(c, posto, year, start_date, end_date):
    c.execute(
        "DELETE FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=? AND datetime(dt_hr_inspecao) BETWEEN datetime(?) AND datetime(?)",
        (posto, str(year), datetime.combine(start_date, time(0,0,0)).isoformat(sep=" "), datetime.combine(end_date, time(23,59,59)).isoformat(sep=" ")),
    )
    c.commit()

def delete_year(c, posto, year):
    c.execute("DELETE FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", (posto, str(year)))
    c.commit()

def years_available(c):
    df = pd.read_sql_query("SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano FROM raw_inspections WHERE cd_posto_cn IN ('QG09','QG07') ORDER BY ano", c)
    return [int(x) for x in df["ano"].dropna().tolist()] if not df.empty else []

def load_year(c, posto, year):
    df = pd.read_sql_query(
        "SELECT nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN, COALESCE(falha,'') AS FALHA_PARETO FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?",
        c, params=[posto, str(year)],
    )
    if not df.empty:
        df["DT_HR_INSPECAO"] = pd.to_datetime(df["DT_HR_INSPECAO"], errors="coerce")
        df["C_DPU_QG_AMARELO"] = pd.to_numeric(df["C_DPU_QG_AMARELO"], errors="coerce").fillna(0)
    return df

def uploads_table(c):
    return pd.read_sql_query("SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC", c)

# ---------------- File prep ----------------
def normalize_columns(df):
    out = df.copy()
    out.columns = [str(x).strip().replace("\ufeff", "") for x in out.columns]
    return out

def read_file(uploaded):
    ext = uploaded.name.lower().split(".")[-1]
    content = uploaded.getvalue()
    if ext == "csv":
        last_err = None
        for enc in ["utf-8-sig", "utf-16", "latin1"]:
            for sep in [None, ";", ",", "\t"]:
                try:
                    if sep is None:
                        return normalize_columns(pd.read_csv(io.BytesIO(content), encoding=enc, sep=None, engine="python"))
                    return normalize_columns(pd.read_csv(io.BytesIO(content), encoding=enc, sep=sep))
                except Exception as err:
                    last_err = err
        raise ValueError(f"Não foi possível ler CSV: {last_err}")
    if ext in ["xlsx", "xls"]:
        return normalize_columns(pd.read_excel(io.BytesIO(content), engine="openpyxl" if ext == "xlsx" else "xlrd"))
    raise ValueError("Formato não suportado. Use .xlsx, .xls ou .csv")

def norm_posto(v):
    txt = str(v).upper().strip()
    if "QG09" in txt:
        return "QG09"
    if "QG07" in txt:
        return "QG07"
    return txt

def detect_falha_col(df):
    cols = {str(c).strip().upper(): c for c in df.columns}
    for cand in FALHA_CANDIDATES:
        if cand.upper() in cols:
            return cols[cand.upper()]
    for c in df.columns:
        u = str(c).upper()
        if "FALHA" in u or "DEFEITO" in u:
            return c
    return None

def prepare(df, falha_col=None):
    missing = [c for c in REQ if c not in df.columns]
    if missing:
        raise ValueError("Colunas obrigatórias ausentes: " + ", ".join(missing))
    w = df.copy()
    w["DT_HR_INSPECAO"] = pd.to_datetime(w["DT_HR_INSPECAO"], errors="coerce")
    mask = w["DT_HR_INSPECAO"].isna() & w["DT_HR_INSPECAO"].notna()
    if mask.any():
        w.loc[mask, "DT_HR_INSPECAO"] = pd.to_datetime(w.loc[mask, "DT_HR_INSPECAO"], errors="coerce", dayfirst=True)
    w["C_DPU_QG_AMARELO"] = pd.to_numeric(w["C_DPU_QG_AMARELO"], errors="coerce").fillna(0)
    w["NR_WO"] = w["NR_WO"].astype(str).str.strip()
    w["CD_POSTO_CN"] = w["CD_POSTO_CN"].astype(str).map(norm_posto)
    chosen = falha_col if falha_col else detect_falha_col(w)
    w["FALHA_PARETO"] = w[chosen].fillna("").astype(str).str.strip() if chosen else ""
    w = w[w["CD_POSTO_CN"].isin(POSTOS)].copy()
    return w[w["DT_HR_INSPECAO"].notna()].copy(), chosen

# ---------------- Calculations ----------------
def calc_rft(df, start_date, end_date):
    if df.empty:
        return {"rft_pct": None, "total": 0, "good": 0, "bad": 0}
    sdt = datetime.combine(start_date, time(0,0,0))
    edt = datetime.combine(end_date, time(23,59,59))
    f = df[(df["DT_HR_INSPECAO"] >= sdt) & (df["DT_HR_INSPECAO"] <= edt)].copy()
    if f.empty:
        return {"rft_pct": None, "total": 0, "good": 0, "bad": 0}
    g = f.groupby("NR_WO", as_index=False)["C_DPU_QG_AMARELO"].sum()
    g["RFT"] = (g["C_DPU_QG_AMARELO"] == 0).astype(int)
    total = int(len(g)); good = int(g["RFT"].sum()); bad = total - good
    return {"rft_pct": round(good/total*100,2), "total": total, "good": good, "bad": bad}

def pareto_table(df):
    df = df[df["FALHA_PARETO"].fillna("").astype(str).str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame(columns=["Rank", "Falha", "Quantidade", "%", "% Acumulado"])
    counts = df["FALHA_PARETO"].value_counts(sort=True, ascending=False).head(10).reset_index()
    counts.columns = ["Falha", "Quantidade"]
    total = counts["Quantidade"].sum()
    counts["%"] = (counts["Quantidade"] / total * 100).round(2)
    counts["% Acumulado"] = counts["%"].cumsum().round(2)
    counts.insert(0, "Rank", range(1, len(counts)+1))
    return counts

def format_pct(v):
    return "Sem dados" if v is None or pd.isna(v) else f"{v:.2f}".replace(".", ",") + "%"

# ---------------- Pareto Plotly ----------------
def render_pareto_plotly(pt, posto, ano, data_ini, data_fim):
    if pt.empty:
        st.info("Não há falhas preenchidas para montar o Pareto nesse período.")
        return
    d = pt.sort_values("Quantidade", ascending=False).reset_index(drop=True)
    title = f"Pareto de Falhas - Top 10 | {posto} | {ano} | {data_ini.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=d["Falha"], y=d["Quantidade"], name="Quantidade",
            marker_color="#2f62b3", text=d["Quantidade"], textposition="outside", cliponaxis=False
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=d["Falha"], y=d["% Acumulado"], name="% Acumulado",
            mode="lines+markers+text", line=dict(color="#f97316", width=3),
            marker=dict(size=8, color="#f97316"), text=[f"{v:.0f}%" for v in d["% Acumulado"]],
            textposition="top center"
        ),
        secondary_y=True,
    )
    fig.add_hline(y=80, line_dash="dash", line_color="#ef4444", annotation_text="80%", annotation_position="top right", secondary_y=True)
    max_qtd = max(float(d["Quantidade"].max()), 1.0)
    fig.update_yaxes(title_text="Quantidade", range=[0, max_qtd*1.22], secondary_y=False)
    fig.update_yaxes(title_text="% Acumulado", ticksuffix="%", range=[0, 105], secondary_y=True)
    fig.update_xaxes(tickangle=-45, title_text="Falha")
    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        height=650,
        margin=dict(l=65, r=65, t=85, b=180),
        legend=dict(orientation="h", yanchor="bottom", y=-0.36, xanchor="center", x=0.5),
        plot_bgcolor="white", paper_bgcolor="white", font=dict(color="#111827"), bargap=0.35,
        hovermode="x unified",
    )
    fig.update_yaxes(showgrid=True, gridcolor="rgba(148,163,184,.35)", secondary_y=False)
    st.plotly_chart(fig, use_container_width=True)

# ---------------- App ----------------
def main():
    c = conn(); init_db(c)
    st.markdown('<div class="hero"><div style="font-size:1.75rem;font-weight:900;">RFT Automático - V9.9.1</div><div class="small">Pareto clássico em Plotly: barras + curva acumulada no mesmo gráfico, Top 10 e filtro de período.</div></div>', unsafe_allow_html=True)

    anos = years_available(c)
    default_year = date.today().year if not anos else anos[-1]
    with st.sidebar:
        posto = st.radio("Posto", POSTOS, index=0, horizontal=True)
        ano = st.selectbox("Ano", anos if anos else [default_year], index=(len(anos)-1 if anos else 0))
        meta = st.number_input("Meta RFT (%)", min_value=0.0, max_value=100.0, value=DEFAULT_META_RFT, step=0.1)

    tabs = st.tabs(["Dashboard", "Tendência", "Pareto de Falhas", "Base & Upload", "Histórico", "Sobre"])
    df_post = load_year(c, posto, ano) if anos else pd.DataFrame()

    with tabs[0]:
        st.markdown('<div class="panel"><h3>Dashboard</h3>', unsafe_allow_html=True)
        if df_post.empty:
            st.info("Sem dados para o posto/ano selecionado.")
        else:
            min_d = df_post["DT_HR_INSPECAO"].dt.date.min(); max_d = df_post["DT_HR_INSPECAO"].dt.date.max()
            today_res = calc_rft(df_post, max_d, max_d)
            month_res = calc_rft(df_post, date(ano, max_d.month, 1), date(ano, max_d.month, monthrange(ano, max_d.month)[1]))
            ytd_res = calc_rft(df_post, date(ano, 1, 1), max_d)
            cols = st.columns(3)
            cols[0].metric("RFT último dia", format_pct(today_res["rft_pct"]), f"Total WOs: {today_res['total']}")
            cols[1].metric("RFT mensal", format_pct(month_res["rft_pct"]), f"Total WOs: {month_res['total']}")
            cols[2].metric("RFT YTD", format_pct(ytd_res["rft_pct"]), f"Total WOs: {ytd_res['total']}")
            st.caption(f"Janela consolidada: {min_d.strftime('%d/%m/%Y')} até {max_d.strftime('%d/%m/%Y')}")
        st.markdown('</div>', unsafe_allow_html=True)

    with tabs[1]:
        st.markdown('<div class="panel"><h3>Tendência</h3>', unsafe_allow_html=True)
        if df_post.empty:
            st.info("Sem dados para tendência.")
        else:
            rows=[]
            for m in sorted(df_post["DT_HR_INSPECAO"].dt.month.unique().tolist()):
                s=date(ano,int(m),1); e=date(ano,int(m),monthrange(ano,int(m))[1]); r=calc_rft(df_post,s,e)
                rows.append({"Mês":s.strftime("%m/%Y"),"RFT":r["rft_pct"] or 0,"Meta":meta})
            trend=pd.DataFrame(rows)
            st.bar_chart(trend.set_index("Mês")[["RFT","Meta"]], use_container_width=True)
            st.dataframe(trend, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with tabs[2]:
        st.markdown('<div class="panel"><h3>Pareto de Falhas</h3><div class="small">Escolha posto, ano e período. O gráfico mostra o Top 10 ordenado com curva acumulada.</div>', unsafe_allow_html=True)
        anos_p = years_available(c)
        if not anos_p:
            st.info("Sem dados para Pareto. Faça upload de uma base com coluna de falha/defeito.")
        else:
            c1,c2=st.columns(2)
            with c1: p_ano=st.selectbox("Ano do Pareto", anos_p, index=len(anos_p)-1, key="p_ano")
            with c2: p_posto=st.radio("Posto do Pareto", POSTOS, index=0, horizontal=True, key="p_posto")
            p_df = load_year(c, p_posto, p_ano)
            p_df = p_df[p_df["FALHA_PARETO"].fillna("").astype(str).str.strip() != ""].copy() if not p_df.empty else p_df
            if p_df.empty:
                st.info("Não há falhas preenchidas para esse posto/ano.")
            else:
                min_p=p_df["DT_HR_INSPECAO"].dt.date.min(); max_p=p_df["DT_HR_INSPECAO"].dt.date.max()
                d1,d2=st.columns(2)
                with d1: data_ini=st.date_input("Data inicial", value=min_p, min_value=min_p, max_value=max_p, format="DD/MM/YYYY", key="pareto_ini")
                with d2: data_fim=st.date_input("Data final", value=max_p, min_value=min_p, max_value=max_p, format="DD/MM/YYYY", key="pareto_fim")
                if data_ini > data_fim:
                    st.error("A data inicial não pode ser maior que a data final.")
                else:
                    f=p_df[(p_df["DT_HR_INSPECAO"].dt.date>=data_ini)&(p_df["DT_HR_INSPECAO"].dt.date<=data_fim)].copy()
                    pt=pareto_table(f)
                    render_pareto_plotly(pt, p_posto, p_ano, data_ini, data_fim)
                    if not pt.empty:
                        show=pt.copy(); show["%"] = show["%"].map(lambda x: f"{x:.2f}".replace('.', ',')+'%'); show["% Acumulado"] = show["% Acumulado"].map(lambda x: f"{x:.2f}".replace('.', ',')+'%')
                        st.dataframe(show, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with tabs[3]:
        st.markdown('<div class="panel"><h3>Base & Upload</h3>', unsafe_allow_html=True)
        mode=st.radio("Modo de importação", ["Somar ao histórico", "Substituir período sobreposto", "Reprocessar o ano inteiro"], horizontal=True)
        up=st.file_uploader("Base operacional (.xlsx, .xls ou .csv)", type=["xlsx","xls","csv"])
        prepared=None
        if up is not None:
            try:
                raw=read_file(up)
                auto=detect_falha_col(raw)
                opts=["Detectar automaticamente / sem coluna"] + [c for c in raw.columns if c not in REQ]
                idx=opts.index(auto) if auto in opts else 0
                chosen=st.selectbox("Coluna para Pareto de Falhas", opts, index=idx)
                falha_col=None if chosen==opts[0] else chosen
                prepared, used_col=prepare(raw, falha_col=falha_col)
                st.success(f"Arquivo carregado: {up.name} | Linhas QG09/QG07 válidas: {len(prepared)}")
                if used_col: st.info(f"Coluna de falha usada: {used_col}")
                else: st.warning("Nenhuma coluna de falha detectada/selecionada. O RFT será salvo, porém o Pareto ficará vazio.")
                impact=[]
                for (yr, pst), part in prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year,"CD_POSTO_CN"]):
                    impact.append({"Posto":pst,"Ano":int(yr),"Data mínima":part["DT_HR_INSPECAO"].dt.date.min(),"Data máxima":part["DT_HR_INSPECAO"].dt.date.max(),"Linhas":len(part),"Falhas preenchidas":int((part["FALHA_PARETO"]!="").sum())})
                if impact: st.dataframe(pd.DataFrame(impact), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")
        if st.button("Salvar arquivo localmente", type="primary", use_container_width=True):
            if up is None or prepared is None or prepared.empty:
                st.error("Selecione e carregue uma base válida antes de salvar.")
            else:
                if mode == "Substituir período sobreposto":
                    for (yr, pst), part in prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year,"CD_POSTO_CN"]):
                        delete_period(c, pst, int(yr), part["DT_HR_INSPECAO"].dt.date.min(), part["DT_HR_INSPECAO"].dt.date.max())
                elif mode == "Reprocessar o ano inteiro":
                    for (yr, pst), _ in prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year,"CD_POSTO_CN"]):
                        delete_year(c, pst, int(yr))
                uid=create_upload(c, up.name, len(prepared), message="Upload V9.9.1")
                save_raw(c, uid, prepared)
                st.success("Arquivo salvo com sucesso.")
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with tabs[4]:
        st.markdown('<div class="panel"><h3>Histórico</h3>', unsafe_allow_html=True)
        hist=uploads_table(c)
        if hist.empty: st.info("Sem uploads salvos.")
        else: st.dataframe(hist, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with tabs[5]:
        st.markdown('<div class="panel"><h3>Sobre</h3><div class="small">V9.9.1: Pareto clássico com Plotly em gráfico único, barras + curva acumulada e filtro de período.</div></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
