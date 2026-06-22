import io
import sqlite3
from datetime import date, datetime, time, timedelta
from calendar import monthrange

import pandas as pd
import streamlit as st

try:
    from streamlit_local_storage import LocalStorage
except Exception:
    LocalStorage = None

# -----------------------------------------------------------------------------
# Configuração geral
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="RFT Automático — V6.0",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB = "rft_v60_local.db"
REQ = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO", "CD_POSTO_CN"]
POSTOS = ["QG09", "QG07"]
POSTO_PADRAO = "QG09"
LS_PREFIX = "rft_v60_"
META_RFT = 95.0
CUTOFF_MONTH = 12
CUTOFF_DAY = 12

# -----------------------------------------------------------------------------
# Tema / CSS
# -----------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
:root {
    --bg: #0f172a;
    --bg-2: #111827;
    --panel: #1e293b;
    --panel-2: #243041;
    --panel-3: #334155;
    --text: #e5e7eb;
    --muted: #94a3b8;
    --line: rgba(148, 163, 184, 0.18);
    --primary: #3b82f6;
    --primary-soft: rgba(59, 130, 246, 0.14);
    --ok: #22c55e;
    --warn: #f59e0b;
    --bad: #ef4444;
    --shadow: 0 20px 40px rgba(2, 6, 23, 0.45);
    --radius-xl: 22px;
    --radius-lg: 18px;
    --radius-md: 14px;
}

html, body, [class*="css"] {
    font-family: "Segoe UI", Inter, Arial, sans-serif;
}

.stApp {
    background:
        radial-gradient(circle at top right, rgba(59,130,246,0.10), transparent 25%),
        radial-gradient(circle at top left, rgba(34,197,94,0.08), transparent 20%),
        linear-gradient(180deg, #0b1220 0%, var(--bg) 100%);
    color: var(--text);
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b1220 0%, #111827 100%);
    border-right: 1px solid var(--line);
}

section[data-testid="stSidebar"] * {
    color: var(--text) !important;
}

div[data-testid="stMarkdownContainer"] p {
    color: var(--text);
}

.block-container {
    padding-top: 1.8rem;
    padding-bottom: 2rem;
}

.hero {
    background: linear-gradient(135deg, rgba(59,130,246,0.16), rgba(30,41,59,0.95));
    border: 1px solid rgba(59,130,246,0.22);
    box-shadow: var(--shadow);
    border-radius: var(--radius-xl);
    padding: 1.5rem 1.5rem 1.35rem 1.5rem;
    margin-bottom: 1.15rem;
}

.hero-title {
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    margin: 0 0 .15rem 0;
    color: #f8fafc;
}

.hero-subtitle {
    color: var(--muted);
    margin-bottom: 1rem;
}

.hero-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: .8rem;
}

.info-chip {
    background: rgba(15, 23, 42, .55);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: .85rem 1rem;
}

.info-chip-label {
    color: var(--muted);
    font-size: .82rem;
    margin-bottom: .2rem;
}

.info-chip-value {
    color: #f8fafc;
    font-size: 1rem;
    font-weight: 700;
}

.section-card {
    background: linear-gradient(180deg, rgba(30,41,59,.92), rgba(17,24,39,.96));
    border: 1px solid var(--line);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow);
    padding: 1rem 1rem .9rem 1rem;
    margin-bottom: 1rem;
}

.section-title {
    color: #f8fafc;
    font-size: 1.1rem;
    font-weight: 700;
    margin-bottom: .25rem;
}

.section-subtitle {
    color: var(--muted);
    font-size: .92rem;
    margin-bottom: .8rem;
}

.metric-card {
    border-radius: var(--radius-lg);
    padding: 1rem 1rem .95rem 1rem;
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(36,48,65,.96), rgba(15,23,42,.96));
    min-height: 150px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.02), var(--shadow);
}

.metric-title {
    color: var(--muted);
    font-size: .88rem;
    font-weight: 600;
    margin-bottom: .45rem;
}

.metric-value {
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    margin-bottom: .25rem;
}

.metric-sub {
    color: var(--text);
    font-size: .95rem;
    margin-bottom: .45rem;
}

.metric-caption {
    color: var(--muted);
    font-size: .82rem;
    line-height: 1.35;
}

.status-ok { color: var(--ok); }
.status-warn { color: var(--warn); }
.status-bad { color: var(--bad); }
.status-neutral { color: #cbd5e1; }

.small-stat {
    background: rgba(15, 23, 42, .55);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: .9rem 1rem;
    min-height: 102px;
}

.small-stat-label {
    color: var(--muted);
    font-size: .82rem;
}

.small-stat-value {
    color: #f8fafc;
    font-size: 1.5rem;
    font-weight: 800;
    margin-top: .2rem;
}

.small-stat-sub {
    color: var(--muted);
    font-size: .8rem;
    margin-top: .2rem;
}

.notice {
    background: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.18);
    color: var(--text);
    border-radius: 18px;
    padding: .95rem 1rem;
}

.success-box {
    background: rgba(34,197,94,.10);
    border:1px solid rgba(34,197,94,.20);
    border-radius: 18px;
    padding: .95rem 1rem;
}

.warning-box {
    background: rgba(245,158,11,.10);
    border:1px solid rgba(245,158,11,.20);
    border-radius: 18px;
    padding: .95rem 1rem;
}

.badge {
    display: inline-flex;
    align-items: center;
    gap: .45rem;
    padding: .42rem .68rem;
    border-radius: 999px;
    font-weight: 600;
    font-size: .82rem;
    border: 1px solid var(--line);
    background: rgba(15,23,42,.55);
}

div[data-testid="stDataFrame"] {
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    overflow: hidden;
}

[data-baseweb="select"] > div,
[data-baseweb="input"] > div,
div[data-testid="stDateInput"] input {
    background: rgba(15,23,42,.7) !important;
    color: var(--text) !important;
    border-color: var(--line) !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: .5rem;
}

.stTabs [data-baseweb="tab"] {
    height: 46px;
    background: rgba(15,23,42,.45);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 0 1rem;
    color: var(--text);
}

.stTabs [aria-selected="true"] {
    background: rgba(59,130,246,.14) !important;
    border-color: rgba(59,130,246,.35) !important;
}

div.stButton > button {
    border-radius: 14px;
    border: 1px solid rgba(59,130,246,.35);
    background: linear-gradient(180deg, rgba(59,130,246,.90), rgba(37,99,235,.90));
    color: white;
    font-weight: 700;
    min-height: 46px;
}

div.stDownloadButton > button {
    border-radius: 14px;
    border: 1px solid var(--line);
    background: rgba(15,23,42,.55);
    color: var(--text);
    font-weight: 700;
    min-height: 46px;
}

div[data-testid="metric-container"] {
    background: rgba(15,23,42,.35);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: .65rem .85rem;
}

hr {
    border-color: var(--line);
}

@media (max-width: 1100px) {
    .hero-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 680px) {
    .hero-grid {
        grid-template-columns: 1fr;
    }
    .hero-title {
        font-size: 1.5rem;
    }
}
</style>
"""

# -----------------------------------------------------------------------------
# Utilidades de persistência local (preferências leves)
# -----------------------------------------------------------------------------
def get_local_storage():
    if LocalStorage is None:
        return None
    try:
        return LocalStorage()
    except Exception:
        return None


def ls_get(key, default=None):
    ls = get_local_storage()
    if ls is None:
        return default
    try:
        value = ls.getItem(LS_PREFIX + key, key=f"get_{key}")
        return default if value in (None, "", "null", "None") else value
    except Exception:
        return default


def ls_set(key, value):
    ls = get_local_storage()
    if ls is None:
        return
    try:
        ls.setItem(LS_PREFIX + key, str(value), key=f"set_{key}")
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Banco local
# -----------------------------------------------------------------------------
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)


def init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            total_rows INTEGER NOT NULL,
            status TEXT NOT NULL,
            message TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            nr_wo TEXT,
            dt_hr_inspecao TEXT,
            c_dpu_qg_amarelo REAL,
            cd_posto_cn TEXT
        )
        """
    )
    conn.commit()


def create_upload(conn, file_name, total_rows, status="RECEBIDO", message=""):
    cur = conn.execute(
        "INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)",
        (file_name, datetime.now().isoformat(timespec="seconds"), int(total_rows), status, message),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_upload(conn, upload_id, status, message=""):
    conn.execute(
        "UPDATE upload_log SET status=?, message=? WHERE id=?",
        (status, message, upload_id),
    )
    conn.commit()


def save_raw(conn, upload_id, df):
    rows = []
    for _, r in df.iterrows():
        rows.append(
            (
                int(upload_id),
                r["NR_WO"],
                r["DT_HR_INSPECAO"].isoformat(sep=" ", timespec="seconds"),
                float(r["C_DPU_QG_AMARELO"]),
                r["CD_POSTO_CN"],
            )
        )
    conn.executemany(
        "INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def uploads_table(conn):
    return pd.read_sql_query(
        "SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC LIMIT 500",
        conn,
    )


def upload_info(conn, upload_id):
    query = "SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log WHERE id=?"
    df = pd.read_sql_query(query, conn, params=[upload_id])
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def latest_upload_id_for_year(conn, posto, year):
    q = """
        SELECT MAX(upload_id) AS upload_id
        FROM raw_inspections
        WHERE cd_posto_cn = ?
          AND strftime('%Y', dt_hr_inspecao) = ?
    """
    df = pd.read_sql_query(q, conn, params=[posto, str(year)])
    if df.empty or pd.isna(df.loc[0, "upload_id"]):
        return None
    return int(df.loc[0, "upload_id"])


def available_years(conn, posto):
    q = """
        SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano
        FROM raw_inspections
        WHERE cd_posto_cn = ?
        ORDER BY ano
    """
    df = pd.read_sql_query(q, conn, params=[posto])
    if df.empty:
        return []
    return [int(x) for x in df["ano"].dropna().tolist()]


def load_upload_df(conn, upload_id):
    df = pd.read_sql_query(
        """
        SELECT nr_wo AS NR_WO,
               dt_hr_inspecao AS DT_HR_INSPECAO,
               c_dpu_qg_amarelo AS C_DPU_QG_AMARELO,
               cd_posto_cn AS CD_POSTO_CN
        FROM raw_inspections
        WHERE upload_id = ?
        """,
        conn,
        params=[upload_id],
    )
    if df.empty:
        return df
    df["DT_HR_INSPECAO"] = pd.to_datetime(df["DT_HR_INSPECAO"], errors="coerce")
    df["C_DPU_QG_AMARELO"] = pd.to_numeric(df["C_DPU_QG_AMARELO"], errors="coerce").fillna(0)
    df["CD_POSTO_CN"] = df["CD_POSTO_CN"].astype(str).map(norm_posto)
    df["NR_WO"] = df["NR_WO"].astype(str).str.strip()
    return df

# -----------------------------------------------------------------------------
# Leitura / preparo dos dados
# -----------------------------------------------------------------------------
def normalize_columns(df):
    out = df.copy()
    out.columns = [str(x).strip().replace("\ufeff", "") for x in out.columns]
    return out


def read_file(uploaded_file):
    ext = uploaded_file.name.lower().split(".")[-1]
    content = uploaded_file.getvalue()
    if ext == "csv":
        last_err = None
        for enc in ["utf-8-sig", "utf-16", "latin1"]:
            for sep in [None, ";", ",", "\t"]:
                try:
                    if sep is None:
                        df = pd.read_csv(io.BytesIO(content), encoding=enc, sep=None, engine="python")
                    else:
                        df = pd.read_csv(io.BytesIO(content), encoding=enc, sep=sep)
                    return normalize_columns(df)
                except Exception as e:
                    last_err = e
        raise ValueError(f"Não foi possível ler o CSV. Detalhe: {last_err}")
    if ext in ["xlsx", "xls"]:
        engine = "openpyxl" if ext == "xlsx" else "xlrd"
        return normalize_columns(pd.read_excel(io.BytesIO(content), engine=engine))
    raise ValueError("Formato não suportado. Utilize .xlsx, .xls ou .csv")


def validate_df(df):
    missing = [c for c in REQ if c not in df.columns]
    return len(missing) == 0, missing


def parse_dt(series):
    dt = pd.to_datetime(series, errors="coerce")
    if hasattr(series, "notna"):
        mask = dt.isna() & series.notna()
        if mask.any():
            dt.loc[mask] = pd.to_datetime(series[mask], errors="coerce", dayfirst=True)
    return dt


def norm_posto(value):
    text = str(value).upper().strip()
    if "QG09" in text:
        return "QG09"
    if "QG07" in text:
        return "QG07"
    return text


def prepare(df):
    work = df.copy()
    work["DT_HR_INSPECAO"] = parse_dt(work["DT_HR_INSPECAO"])
    work["C_DPU_QG_AMARELO"] = pd.to_numeric(work["C_DPU_QG_AMARELO"], errors="coerce").fillna(0)
    work["NR_WO"] = work["NR_WO"].astype(str).str.strip()
    work["CD_POSTO_CN"] = work["CD_POSTO_CN"].astype(str).map(norm_posto)
    work = work[work["DT_HR_INSPECAO"].notna()].copy()
    return work

# -----------------------------------------------------------------------------
# Cálculos de RFT
# -----------------------------------------------------------------------------
def calc_rft(df, start_date, end_date):
    start_dt = datetime.combine(start_date, time(0, 0, 0))
    end_dt = datetime.combine(end_date, time(23, 59, 59))
    filt = df[(df["DT_HR_INSPECAO"] >= start_dt) & (df["DT_HR_INSPECAO"] <= end_dt)].copy()
    if filt.empty:
        return {"rft_pct": None, "total": 0, "good": 0, "bad": 0}
    grouped = (
        filt.groupby("NR_WO", as_index=False)["C_DPU_QG_AMARELO"]
        .sum()
        .rename(columns={"C_DPU_QG_AMARELO": "SOMA"})
    )
    grouped["RFT"] = (grouped["SOMA"] == 0).astype(int)
    total = int(len(grouped))
    good = int(grouped["RFT"].sum())
    bad = int(total - good)
    pct = round((good / total) * 100, 2) if total else None
    return {"rft_pct": pct, "total": total, "good": good, "bad": bad}


def year_status(df, year):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year].copy()
    if ydf.empty:
        return False, "Sem dados"
    max_d = ydf["DT_HR_INSPECAO"].dt.date.max()
    cutoff = date(year, CUTOFF_MONTH, CUTOFF_DAY)
    if max_d >= cutoff:
        return True, f"Fechado em {cutoff.strftime('%d/%m')}"
    return False, f"Até {max_d.strftime('%d/%m/%Y')}"


def week_options(df, year):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year].copy()
    if ydf.empty:
        return []
    dates = sorted(ydf["DT_HR_INSPECAO"].dt.date.unique().tolist())
    mondays = sorted({d - timedelta(days=d.weekday()) for d in dates})
    opts = []
    for i, monday in enumerate(mondays, start=1):
        sunday = monday + timedelta(days=6)
        label = f"Semana {i} — {monday.strftime('%d/%m/%Y')} a {sunday.strftime('%d/%m/%Y')}"
        opts.append((label, monday, sunday))
    return opts


def month_options(df, year):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year].copy()
    if ydf.empty:
        return []
    opts = []
    for month in sorted(ydf["DT_HR_INSPECAO"].dt.month.unique().tolist()):
        start = date(year, int(month), 1)
        end = date(year, int(month), monthrange(year, int(month))[1])
        label = f"{start.strftime('%m/%Y')} — {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}"
        opts.append((label, start, end))
    return opts


def trend_monthly(df, year):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year].copy()
    if ydf.empty:
        return pd.DataFrame(columns=["Mês", "RFT", "Meta"])

    rows = []
    for month in range(1, 13):
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        result = calc_rft(ydf, start, end)
        rows.append(
            {
                "Mês": start.strftime("%m/%Y"),
                "RFT": result["rft_pct"],
                "Meta": META_RFT,
            }
        )
    out = pd.DataFrame(rows)
    return out[out["RFT"].notna()].reset_index(drop=True)


def trend_daily_selected(df, start_date, end_date):
    filt = df[
        (df["DT_HR_INSPECAO"].dt.date >= start_date)
        & (df["DT_HR_INSPECAO"].dt.date <= end_date)
    ].copy()
    if filt.empty:
        return pd.DataFrame(columns=["Data", "RFT"])

    rows = []
    for day in sorted(filt["DT_HR_INSPECAO"].dt.date.unique().tolist()):
        result = calc_rft(df, day, day)
        rows.append({"Data": day.strftime("%d/%m/%Y"), "RFT": result["rft_pct"]})
    return pd.DataFrame(rows)


def wo_summary(df, start_date, end_date):
    start_dt = datetime.combine(start_date, time(0, 0, 0))
    end_dt = datetime.combine(end_date, time(23, 59, 59))
    filt = df[(df["DT_HR_INSPECAO"] >= start_dt) & (df["DT_HR_INSPECAO"] <= end_dt)].copy()
    if filt.empty:
        return pd.DataFrame(columns=["NR_WO", "SOMA_DEFEITO", "STATUS"])
    grouped = (
        filt.groupby("NR_WO", as_index=False)["C_DPU_QG_AMARELO"]
        .sum()
        .rename(columns={"C_DPU_QG_AMARELO": "SOMA_DEFEITO"})
        .sort_values(["SOMA_DEFEITO", "NR_WO"], ascending=[False, True])
        .reset_index(drop=True)
    )
    grouped["STATUS"] = grouped["SOMA_DEFEITO"].apply(lambda x: "Boa" if x == 0 else "Ruim")
    return grouped

# -----------------------------------------------------------------------------
# Formatação visual
# -----------------------------------------------------------------------------
def format_pct(v):
    if v is None or pd.isna(v):
        return "Sem dados"
    return f"{v:.2f}".replace(".", ",") + "%"


def format_date(d):
    if d is None or pd.isna(d):
        return "-"
    if isinstance(d, str):
        return d
    return d.strftime("%d/%m/%Y")


def status_class(value):
    if value is None or pd.isna(value):
        return "status-neutral"
    if value >= META_RFT:
        return "status-ok"
    if value >= 90:
        return "status-warn"
    return "status-bad"


def metric_card(title, result, caption):
    pct = None if result is None else result.get("rft_pct")
    css = status_class(pct)
    value = format_pct(pct)
    good = 0 if result is None else result.get("good", 0)
    bad = 0 if result is None else result.get("bad", 0)
    total = 0 if result is None else result.get("total", 0)
    return f"""
    <div class='metric-card'>
        <div class='metric-title'>{title}</div>
        <div class='metric-value {css}'>{value}</div>
        <div class='metric-sub'>Boas: <b>{good}</b> &nbsp;&nbsp; Ruins: <b>{bad}</b> &nbsp;&nbsp; Total: <b>{total}</b></div>
        <div class='metric-caption'>{caption}</div>
    </div>
    """


def small_stat_card(label, value, subtitle=""):
    return f"""
    <div class='small-stat'>
        <div class='small-stat-label'>{label}</div>
        <div class='small-stat-value'>{value}</div>
        <div class='small-stat-sub'>{subtitle}</div>
    </div>
    """


def header_block(posto, ano, info, min_date, max_date, year_label):
    file_name = info.get("file_name", "-") if info else "-"
    uploaded_at = info.get("uploaded_at", "-") if info else "-"
    return f"""
    <div class='hero'>
        <div class='hero-title'>RFT Automático — V6.0</div>
        <div class='hero-subtitle'>Painel corporativo da qualidade com visual premium, leitura rápida dos indicadores e operação simplificada da base.</div>
        <div class='hero-grid'>
            <div class='info-chip'>
                <div class='info-chip-label'>Posto selecionado</div>
                <div class='info-chip-value'>{posto}</div>
            </div>
            <div class='info-chip'>
                <div class='info-chip-label'>Ano de consulta</div>
                <div class='info-chip-value'>{ano}</div>
            </div>
            <div class='info-chip'>
                <div class='info-chip-label'>Último upload</div>
                <div class='info-chip-value'>{uploaded_at}</div>
            </div>
            <div class='info-chip'>
                <div class='info-chip-label'>Status do ano</div>
                <div class='info-chip-value'>{year_label}</div>
            </div>
            <div class='info-chip'>
                <div class='info-chip-label'>Arquivo ativo</div>
                <div class='info-chip-value'>{file_name}</div>
            </div>
            <div class='info-chip'>
                <div class='info-chip-label'>Janela da base</div>
                <div class='info-chip-value'>{format_date(min_date)} até {format_date(max_date)}</div>
            </div>
            <div class='info-chip'>
                <div class='info-chip-label'>Meta de RFT</div>
                <div class='info-chip-value'>{format_pct(META_RFT)}</div>
            </div>
            <div class='info-chip'>
                <div class='info-chip-label'>Leitura operacional</div>
                <div class='info-chip-value'>GitHub + Streamlit Ready</div>
            </div>
        </div>
    </div>
    """

# -----------------------------------------------------------------------------
# Interface / seleção de período
# -----------------------------------------------------------------------------
def sidebar_filters(conn):
    st.sidebar.markdown("## Painel de controle")
    st.sidebar.caption("Filtros corporativos da consulta")

    default_posto = ls_get("posto", POSTO_PADRAO)
    idx_posto = POSTOS.index(default_posto) if default_posto in POSTOS else 0
    posto = st.sidebar.radio("Posto", POSTOS, index=idx_posto, horizontal=True)
    ls_set("posto", posto)

    years = available_years(conn, posto)
    if not years:
        st.sidebar.info("Sem histórico disponível. Faça o primeiro upload da base.")
        return {"has_data": False, "posto": posto}

    previous_year = ls_get("ano", None)
    try:
        previous_year = int(previous_year) if previous_year is not None else None
    except Exception:
        previous_year = None
    idx_year = years.index(previous_year) if previous_year in years else len(years) - 1
    ano = st.sidebar.selectbox("Ano", years, index=idx_year)
    ls_set("ano", ano)

    mode_options = ["Diário", "Semanal", "Mensal", "Anual"]
    default_mode = ls_get("modo", "Diário")
    idx_mode = mode_options.index(default_mode) if default_mode in mode_options else 0
    mode = st.sidebar.radio("Modo de visualização", mode_options, index=idx_mode)
    ls_set("modo", mode)

    return {
        "has_data": True,
        "posto": posto,
        "ano": ano,
        "modo": mode,
    }


def resolve_period_selection(df, year, mode):
    min_date = df["DT_HR_INSPECAO"].dt.date.min()
    max_date = df["DT_HR_INSPECAO"].dt.date.max()

    selected_label = "—"
    start_sel = min_date
    end_sel = max_date
    daily = weekly = monthly = yearly = ytd = None
    ok_year, status_label = year_status(df, year)

    if mode == "Diário":
        saved_day = ls_get("dia", "")
        try:
            default_day = datetime.fromisoformat(saved_day).date() if saved_day else max_date
        except Exception:
            default_day = max_date
        if default_day < min_date or default_day > max_date:
            default_day = max_date

        selected = st.sidebar.date_input(
            "Dia",
            value=default_day,
            min_value=min_date,
            max_value=max_date,
            format="DD/MM/YYYY",
            key="day_v60",
        )
        ls_set("dia", selected.isoformat())

        selected_label = format_date(selected)
        start_sel = selected
        end_sel = selected
        daily = calc_rft(df, selected, selected)

        ws = selected - timedelta(days=selected.weekday())
        we = ws + timedelta(days=6)
        weekly = calc_rft(df, ws, we)

        ms = date(year, selected.month, 1)
        me = date(year, selected.month, monthrange(year, selected.month)[1])
        monthly = calc_rft(df, ms, me)

        yearly = calc_rft(df, date(year, 1, 1), date(year, 12, 12)) if ok_year else None
        ytd = calc_rft(df, date(year, 1, 1), selected)

    elif mode == "Semanal":
        opts = week_options(df, year)
        labels = [x[0] for x in opts]
        if not labels:
            return None
        saved = ls_get("semana_label", "")
        idx = labels.index(saved) if saved in labels else len(labels) - 1
        label = st.sidebar.selectbox("Semana do ano", labels, index=idx)
        ls_set("semana_label", label)
        found = next(x for x in opts if x[0] == label)
        ws, we = found[1], found[2]
        selected_label = label
        start_sel = ws
        end_sel = we if we <= max_date else max_date
        weekly = calc_rft(df, ws, we)
        monthly = calc_rft(df, date(year, ws.month, 1), date(year, ws.month, monthrange(year, ws.month)[1]))
        yearly = calc_rft(df, date(year, 1, 1), date(year, 12, 12)) if ok_year else None
        ytd = calc_rft(df, date(year, 1, 1), end_sel)

    elif mode == "Mensal":
        opts = month_options(df, year)
        labels = [x[0] for x in opts]
        if not labels:
            return None
        saved = ls_get("mes_label", "")
        idx = labels.index(saved) if saved in labels else len(labels) - 1
        label = st.sidebar.selectbox("Mês do ano", labels, index=idx)
        ls_set("mes_label", label)
        found = next(x for x in opts if x[0] == label)
        ms, me = found[1], found[2]
        selected_label = label
        start_sel = ms
        end_sel = me if me <= max_date else max_date
        monthly = calc_rft(df, ms, me)
        yearly = calc_rft(df, date(year, 1, 1), date(year, 12, 12)) if ok_year else None
        ytd = calc_rft(df, date(year, 1, 1), end_sel)

    else:
        selected_label = f"Ano {year}"
        start_sel = date(year, 1, 1)
        end_sel = max_date if max_date <= date(year, 12, 12) else date(year, 12, 12)
        yearly = calc_rft(df, date(year, 1, 1), date(year, 12, 12)) if ok_year else None
        ytd = calc_rft(df, date(year, 1, 1), end_sel)

    return {
        "selected_label": selected_label,
        "start_sel": start_sel,
        "end_sel": end_sel,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "yearly": yearly,
        "ytd": ytd,
        "min_date": min_date,
        "max_date": max_date,
        "status_label": status_label,
        "ok_year": ok_year,
    }

# -----------------------------------------------------------------------------
# Renderização
# -----------------------------------------------------------------------------
def render_empty_state(title, text):
    st.markdown(
        f"<div class='section-card'><div class='section-title'>{title}</div><div class='warning-box'>{text}</div></div>",
        unsafe_allow_html=True,
    )


def render_dashboard(df, posto, ano, info, selection):
    st.markdown(
        header_block(
            posto=posto,
            ano=ano,
            info=info,
            min_date=selection["min_date"],
            max_date=selection["max_date"],
            year_label=selection["status_label"],
        ),
        unsafe_allow_html=True,
    )

    tab_dashboard, tab_tendencia, tab_operacao = st.tabs(["Dashboard", "Tendência", "Operacional"])

    with tab_dashboard:
        st.markdown(
            "<div class='section-card'><div class='section-title'>Indicadores principais</div><div class='section-subtitle'>Leitura rápida do desempenho por recorte temporal.</div></div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.markdown(metric_card("RFT Diário", selection["daily"], "Leitura fechada do dia selecionado."), unsafe_allow_html=True)
        with c2:
            st.markdown(metric_card("RFT Semanal", selection["weekly"], "Consolidação da semana do recorte."), unsafe_allow_html=True)
        with c3:
            st.markdown(metric_card("RFT Mensal", selection["monthly"], "Consolidação do mês competente."), unsafe_allow_html=True)
        with c4:
            st.markdown(metric_card("RFT Anual", selection["yearly"], "Resultado do ano até 12/12."), unsafe_allow_html=True)
        with c5:
            st.markdown(metric_card("RFT YTD", selection["ytd"], "Acumulado do ano até o período selecionado."), unsafe_allow_html=True)

        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown("<div class='section-title'>Resumo executivo do recorte</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='section-subtitle'>Visão consolidada do período <b>{selection['selected_label']}</b>.</div>", unsafe_allow_html=True)
        s1, s2, s3, s4 = st.columns(4)
        active_result = selection["daily"] or selection["weekly"] or selection["monthly"] or selection["yearly"] or selection["ytd"]
        active_pct = format_pct(active_result["rft_pct"]) if active_result else "Sem dados"
        total = active_result["total"] if active_result else 0
        good = active_result["good"] if active_result else 0
        bad = active_result["bad"] if active_result else 0
        taxa_falha = "0,00%"
        if active_result and active_result.get("total", 0):
            taxa_falha = f"{(active_result['bad']/active_result['total']*100):.2f}".replace(".", ",") + "%"
        with s1:
            st.markdown(small_stat_card("Recorte atual", active_pct, selection["selected_label"]), unsafe_allow_html=True)
        with s2:
            st.markdown(small_stat_card("Total de WOs", str(total), "Unidades avaliadas no recorte"), unsafe_allow_html=True)
        with s3:
            st.markdown(small_stat_card("WOs boas", str(good), "Sem ocorrência de defeito"), unsafe_allow_html=True)
        with s4:
            st.markdown(small_stat_card("Taxa de falha", taxa_falha, f"WOs ruins: {bad}"), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        k1, k2 = st.columns([1.6, 1.1])
        with k1:
            monthly_df = trend_monthly(df, ano)
            st.markdown("<div class='section-card'><div class='section-title'>Tendência mensal do RFT</div><div class='section-subtitle'>Evolução do desempenho no ano selecionado.</div>", unsafe_allow_html=True)
            if monthly_df.empty:
                st.info("Sem dados mensais suficientes para exibir a tendência.")
            else:
                monthly_chart = monthly_df.set_index("Mês")[["RFT", "Meta"]]
                st.line_chart(monthly_chart, use_container_width=True)
                st.dataframe(monthly_df, use_container_width=True, hide_index=True)
            st.markdown("</div>", unsafe_allow_html=True)
        with k2:
            st.markdown("<div class='section-card'><div class='section-title'>Contexto do arquivo ativo</div><div class='section-subtitle'>Resumo corporativo da base utilizada.</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='notice'><b>Arquivo:</b> {info.get('file_name', '-') if info else '-'}<br><b>Upload:</b> {info.get('uploaded_at', '-') if info else '-'}<br><b>Posto:</b> {posto}<br><b>Ano:</b> {ano}<br><b>Período disponível:</b> {format_date(selection['min_date'])} até {format_date(selection['max_date'])}<br><b>Status do ano:</b> {selection['status_label']}</div>", unsafe_allow_html=True)
            meta_gap = None
            if selection["ytd"] and selection["ytd"]["rft_pct"] is not None:
                meta_gap = round(selection["ytd"]["rft_pct"] - META_RFT, 2)
            gap_text = "Sem dados"
            if meta_gap is not None:
                prefix = "+" if meta_gap >= 0 else ""
                gap_text = prefix + str(meta_gap).replace(".", ",") + " p.p."
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(small_stat_card("Meta x realizado (YTD)", gap_text, f"Meta corporativa: {format_pct(META_RFT)}"), unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    with tab_tendencia:
        st.markdown("<div class='section-card'><div class='section-title'>Evolução diária do período selecionado</div><div class='section-subtitle'>Leitura do RFT dia a dia dentro do recorte ativo.</div>", unsafe_allow_html=True)
        daily_df = trend_daily_selected(df, selection["start_sel"], selection["end_sel"])
        if daily_df.empty:
            st.info("Sem dados diários para exibir neste recorte.")
        else:
            st.bar_chart(daily_df.set_index("Data")[["RFT"]], use_container_width=True)
            st.dataframe(daily_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-card'><div class='section-title'>Distribuição mensal consolidada</div><div class='section-subtitle'>Comparativo mês a mês no ano selecionado.</div>", unsafe_allow_html=True)
        mensal = trend_monthly(df, ano)
        if mensal.empty:
            st.info("Sem dados para distribuir por mês.")
        else:
            st.bar_chart(mensal.set_index("Mês")[["RFT"]], use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_operacao:
        st.markdown("<div class='section-card'><div class='section-title'>Consolidação por WO</div><div class='section-subtitle'>Detalhamento das ordens no período selecionado.</div>", unsafe_allow_html=True)
        summary = wo_summary(df, selection["start_sel"], selection["end_sel"])
        if summary.empty:
            st.info("Sem WOs no período selecionado.")
        else:
            top_bad = summary[summary["STATUS"] == "Ruim"].head(10)
            a1, a2 = st.columns([1.3, 1.7])
            with a1:
                st.markdown("<div class='section-subtitle'><b>Top WOs com defeito</b></div>", unsafe_allow_html=True)
                if top_bad.empty:
                    st.markdown("<div class='success-box'>Nenhuma WO ruim encontrada no recorte disponível.</div>", unsafe_allow_html=True)
                else:
                    st.dataframe(top_bad, use_container_width=True, hide_index=True)
            with a2:
                st.markdown("<div class='section-subtitle'><b>Tabela completa do recorte</b></div>", unsafe_allow_html=True)
                st.dataframe(summary, use_container_width=True, hide_index=True)

            csv_data = summary.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="Baixar consolidação por WO (CSV)",
                data=csv_data,
                file_name=f"rft_consolidado_{selection['start_sel']}_{selection['end_sel']}_{posto}.csv",
                mime="text/csv",
                use_container_width=False,
            )
        st.markdown("</div>", unsafe_allow_html=True)


def render_upload_area(conn):
    st.markdown("<div class='section-card'><div class='section-title'>Atualizar base do sistema</div><div class='section-subtitle'>Envie o arquivo operacional e salve localmente para leitura imediata do dashboard.</div>", unsafe_allow_html=True)
    uploaded = st.file_uploader("Base operacional atual (.xlsx, .xls ou .csv)", type=["xlsx", "xls", "csv"])

    if st.button("Salvar arquivo localmente", type="primary", use_container_width=True):
        if uploaded is None:
            st.error("Selecione um arquivo antes de salvar.")
            st.stop()
        try:
            raw = read_file(uploaded)
            ok, missing = validate_df(raw)
            if not ok:
                st.error("Base operacional inválida. Colunas faltantes: " + ", ".join(missing))
                st.stop()
            prepared = prepare(raw)
            if prepared.empty:
                st.error("A base foi lida, mas não restaram linhas válidas após o tratamento das datas.")
                st.stop()
        except Exception as e:
            st.error(f"Erro ao ler a base operacional: {e}")
            st.stop()

        upload_id = create_upload(conn, uploaded.name, len(prepared), message="Base recebida e salva localmente.")
        try:
            save_raw(conn, upload_id, prepared)
            update_upload(conn, upload_id, "PROCESSADO", "Base salva com sucesso.")
            st.success("Arquivo salvo com sucesso. O dashboard já pode ser consultado.")
            st.rerun()
        except Exception as e:
            update_upload(conn, upload_id, "ERRO", str(e))
            st.error(f"Erro ao salvar a base: {e}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div class='notice'><b>Colunas obrigatórias:</b> NR_WO, DT_HR_INSPECAO, C_DPU_QG_AMARELO e CD_POSTO_CN.</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_history(conn):
    st.markdown("<div class='section-card'><div class='section-title'>Histórico local de uploads</div><div class='section-subtitle'>Rastreabilidade das bases processadas no sistema.</div>", unsafe_allow_html=True)
    hist = uploads_table(conn)
    if hist.empty:
        st.info("Nenhum upload processado até o momento.")
    else:
        st.dataframe(hist, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_about():
    st.markdown("<div class='section-card'><div class='section-title'>Sobre a versão V6.0</div><div class='section-subtitle'>Nova camada visual e organizacional do sistema de RFT.</div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class='notice'>
        <b>Novidades principais:</b><br>
        • design corporativo escuro, sem aparência totalmente branca;<br>
        • cabeçalho executivo com contexto da base;<br>
        • sidebar organizada para filtros e navegação;<br>
        • dashboard mais limpo com KPIs em cards premium;<br>
        • tendência mensal e visão diária do período;<br>
        • área operacional com consolidação por WO e download em CSV;<br>
        • estrutura pronta para GitHub + Streamlit Community Cloud.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        "<div class='warning-box'><b>Observação:</b> esta versão continua usando SQLite local para facilitar o uso imediato. Para produção corporativa com histórico persistente, a próxima evolução natural é conectar um banco externo.</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    conn = get_conn()
    init_db(conn)

    selection_state = sidebar_filters(conn)

    if not selection_state.get("has_data"):
        st.markdown(
            "<div class='hero'><div class='hero-title'>RFT Automático — V6.0</div><div class='hero-subtitle'>Painel corporativo da qualidade pronto para receber a primeira base operacional.</div></div>",
            unsafe_allow_html=True,
        )
        render_upload_area(conn)
        render_history(conn)
        render_about()
        return

    posto = selection_state["posto"]
    ano = selection_state["ano"]
    modo = selection_state["modo"]

    upload_id = latest_upload_id_for_year(conn, posto, ano)
    if upload_id is None:
        render_empty_state("Sem histórico do filtro", "Não existe upload salvo para este ano e posto. Faça novo upload ou ajuste o filtro.")
        render_upload_area(conn)
        render_history(conn)
        render_about()
        return

    info = upload_info(conn, upload_id)
    df_all = load_upload_df(conn, upload_id)
    df = df_all[(df_all["CD_POSTO_CN"] == posto) & (df_all["DT_HR_INSPECAO"].dt.year == ano)].copy()

    if df.empty:
        render_empty_state("Sem dados válidos", "O arquivo salvo não possui linhas válidas para este filtro.")
        render_upload_area(conn)
        render_history(conn)
        render_about()
        return

    selection = resolve_period_selection(df, ano, modo)
    if selection is None:
        render_empty_state("Sem períodos disponíveis", "Não há dados suficientes para montar o período solicitado.")
        render_upload_area(conn)
        render_history(conn)
        render_about()
        return

    render_dashboard(df, posto, ano, info, selection)
    st.divider()
    render_upload_area(conn)
    st.divider()
    render_history(conn)
    st.divider()
    render_about()


if __name__ == "__main__":
    main()
