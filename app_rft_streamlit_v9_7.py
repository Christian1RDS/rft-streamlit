
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

st.set_page_config(
    page_title="RFT Automatico - V9.7",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB = "rft_v61_local.db"
REQ = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO", "CD_POSTO_CN"]
POSTOS = ["QG09", "QG07"]
POSTO_PADRAO = "QG09"
LS_PREFIX = "rft_v97_"
DEFAULT_META_RFT = 95.0
YEAR_CLOSE_DAY = 10
FALHA_CANDIDATES = [
    "FALHA", "DEFEITO", "DS_DEFEITO", "NM_DEFEITO", "TIPO_FALHA",
    "DESCRICAO_DEFEITO", "DESCRIÇÃO_DEFEITO", "DESC_DEFEITO",
    "NOME_FALHA", "DS_FALHA", "NM_FALHA", "TIPO_DEFEITO",
    "CAUSA", "DESCRICAO", "DESCRIÇÃO", "OBS_DEFEITO",
]

CSS = """
<style>
:root {
  --line:rgba(148,163,184,.18);
  --txt:#e5e7eb;
  --muted:#94a3b8;
  --ok:#22c55e;
  --bad:#ef4444;
}
html, body, [data-testid="stAppViewContainer"], .stApp {
  background: radial-gradient(circle at top left, #13213d 0%, #0b1220 35%, #09101c 100%);
  color: var(--txt);
}
[data-testid="stHeader"] { background: rgba(11,18,32,.76); border-bottom: 1px solid var(--line); }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#0f172a 0%, #101827 100%); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] * { color: var(--txt) !important; }
.block-container { padding-top: .8rem; padding-bottom: 2rem; }
h1,h2,h3,h4,h5,h6,p,label,div,span { color: var(--txt); }
.hero { background: linear-gradient(135deg, rgba(24,34,53,.97), rgba(16,24,40,.98)); border:1px solid var(--line); border-radius:22px; padding:1.15rem 1.25rem; box-shadow: 0 12px 36px rgba(0,0,0,.24); margin-bottom:1rem; }
.panel { background: linear-gradient(180deg, rgba(34,48,73,.96), rgba(21,31,47,.98)); border:1px solid var(--line); border-radius:18px; padding:1rem; box-shadow: 0 10px 30px rgba(0,0,0,.18); margin-bottom:1rem; }
.metric-box { border:1px solid var(--line); background: linear-gradient(180deg, rgba(36,50,74,.96), rgba(25,36,54,.98)); border-radius:18px; padding:1rem; min-height:150px; box-shadow: 0 10px 24px rgba(0,0,0,.18); }
.kv { display:flex; justify-content:space-between; gap:1rem; padding:.6rem .75rem; border-radius:14px; background: rgba(255,255,255,.03); border:1px solid rgba(148,163,184,.10); margin-bottom:.5rem; }
.pill { display:inline-flex; align-items:center; gap:.35rem; padding:.45rem .8rem; border-radius:999px; background:rgba(59,130,246,.12); border:1px solid rgba(59,130,246,.28); margin-right:.35rem; margin-bottom:.35rem; }
.muted { color: var(--muted); font-size:.83rem; }
.ok { color: var(--ok); }
.bad { color: var(--bad); }
.neutral { color: var(--txt); }
</style>
"""

# -------------------- Local Storage --------------------
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
        val = ls.getItem(LS_PREFIX + key, key=f"get_{key}")
        return default if val in (None, "", "null", "None") else val
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

# -------------------- Database --------------------
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)


def ensure_column(conn, table, column, sql_type):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
        conn.commit()


def init_db(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS upload_log (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL, uploaded_at TEXT NOT NULL, total_rows INTEGER NOT NULL, status TEXT NOT NULL, message TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS raw_inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, nr_wo TEXT, dt_hr_inspecao TEXT, c_dpu_qg_amarelo REAL, cd_posto_cn TEXT)"
    )
    ensure_column(conn, "raw_inspections", "falha", "TEXT")
    conn.commit()


def create_upload(conn, file_name, total_rows, status="RECEBIDO", message=""):
    cur = conn.execute(
        "INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)",
        (file_name, datetime.now().isoformat(timespec="seconds"), int(total_rows), status, message),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_upload(conn, upload_id, status, message=""):
    conn.execute("UPDATE upload_log SET status=?, message=? WHERE id=?", (status, message, int(upload_id)))
    conn.commit()


def save_raw(conn, upload_id, df):
    rows = []
    for _, r in df.iterrows():
        rows.append((
            int(upload_id),
            r["NR_WO"],
            r["DT_HR_INSPECAO"].isoformat(sep=" ", timespec="seconds"),
            float(r["C_DPU_QG_AMARELO"]),
            r["CD_POSTO_CN"],
            r.get("FALHA_PARETO", ""),
        ))
    conn.executemany(
        "INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn, falha) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def uploads_table(conn):
    return pd.read_sql_query(
        "SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC LIMIT 300",
        conn,
    )


def upload_info(conn, upload_id):
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM upload_log WHERE id=?", (int(upload_id),)).fetchone()
    conn.row_factory = None
    return row


def upload_detail_df(conn, upload_id):
    df = pd.read_sql_query(
        'SELECT nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN, COALESCE(falha, "") AS FALHA_PARETO FROM raw_inspections WHERE upload_id=? ORDER BY dt_hr_inspecao, nr_wo',
        conn,
        params=[int(upload_id)],
    )
    if not df.empty:
        df["DT_HR_INSPECAO"] = pd.to_datetime(df["DT_HR_INSPECAO"], errors="coerce")
    return df


def delete_upload(conn, upload_id):
    conn.execute("DELETE FROM raw_inspections WHERE upload_id=?", (int(upload_id),))
    conn.execute("DELETE FROM upload_log WHERE id=?", (int(upload_id),))
    conn.commit()


def reprocess_upload(conn, upload_id):
    df = upload_detail_df(conn, upload_id)
    if df.empty:
        update_upload(conn, upload_id, "ERRO", "Upload sem linhas brutas para reprocessar.")
        return None
    info = upload_info(conn, upload_id)
    new_name = f"REPROCESSADO_{info['file_name']}" if info else f"REPROCESSADO_{upload_id}"
    new_id = create_upload(conn, new_name, len(df), message=f"Reprocessado a partir do upload {upload_id}.")
    save_raw(conn, new_id, df[["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO", "CD_POSTO_CN", "FALHA_PARETO"]])
    update_upload(conn, new_id, "PROCESSADO", f"Upload {upload_id} reprocessado com sucesso.")
    return new_id


def available_years(conn, posto):
    df = pd.read_sql_query(
        "SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano FROM raw_inspections WHERE cd_posto_cn=? ORDER BY ano",
        conn,
        params=[posto],
    )
    return [int(x) for x in df["ano"].dropna().tolist()] if not df.empty else []


def available_years_any(conn):
    df = pd.read_sql_query(
        "SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano FROM raw_inspections WHERE cd_posto_cn IN ('QG09','QG07') ORDER BY ano",
        conn,
    )
    return [int(x) for x in df["ano"].dropna().tolist()] if not df.empty else []


def latest_upload_id_for_year(conn, posto, year):
    df = pd.read_sql_query(
        "SELECT MAX(upload_id) AS upload_id FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?",
        conn,
        params=[posto, str(year)],
    )
    if df.empty or pd.isna(df.loc[0, "upload_id"]):
        return None
    return int(df.loc[0, "upload_id"])


def existing_range_for_posto_year(conn, posto, year):
    df = pd.read_sql_query(
        "SELECT MIN(date(dt_hr_inspecao)) AS min_d, MAX(date(dt_hr_inspecao)) AS max_d FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?",
        conn,
        params=[posto, str(year)],
    )
    if df.empty or pd.isna(df.loc[0, "min_d"]):
        return None, None
    return pd.to_datetime(df.loc[0, "min_d"]).date(), pd.to_datetime(df.loc[0, "max_d"]).date()


def delete_overlapped_period(conn, posto, year, start_date, end_date):
    conn.execute(
        "DELETE FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=? AND datetime(dt_hr_inspecao) BETWEEN datetime(?) AND datetime(?)",
        (
            posto,
            str(year),
            datetime.combine(start_date, time(0, 0, 0)).isoformat(sep=" "),
            datetime.combine(end_date, time(23, 59, 59)).isoformat(sep=" "),
        ),
    )
    conn.commit()


def delete_year_for_posto(conn, posto, year):
    conn.execute("DELETE FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", (posto, str(year)))
    conn.commit()


def apply_import_mode(conn, df, mode):
    affected = []
    if df is None or df.empty or mode == "Somar ao historico":
        return affected
    for (year, posto), part in df.groupby([df["DT_HR_INSPECAO"].dt.year, "CD_POSTO_CN"]):
        if mode == "Substituir periodo sobreposto":
            start_date = part["DT_HR_INSPECAO"].dt.date.min()
            end_date = part["DT_HR_INSPECAO"].dt.date.max()
            delete_overlapped_period(conn, posto, int(year), start_date, end_date)
            affected.append(f'{posto}/{year}: substituido periodo {start_date.strftime("%d/%m/%Y")} a {end_date.strftime("%d/%m/%Y")}')
        elif mode == "Reprocessar o ano inteiro":
            delete_year_for_posto(conn, posto, int(year))
            affected.append(f"{posto}/{year}: reprocessado ano inteiro")
    return affected

# -------------------- File preparation --------------------
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
                except Exception as err:
                    last_err = err
        raise ValueError(f"Nao foi possivel ler o CSV. Detalhe: {last_err}")
    if ext in ["xlsx", "xls"]:
        engine = "openpyxl" if ext == "xlsx" else "xlrd"
        return normalize_columns(pd.read_excel(io.BytesIO(content), engine=engine))
    raise ValueError("Formato nao suportado. Use .xlsx, .xls ou .csv")


def validate_df(df):
    missing = [c for c in REQ if c not in df.columns]
    return len(missing) == 0, missing


def parse_dt(series):
    dt = pd.to_datetime(series, errors="coerce")
    mask = dt.isna() & series.notna()
    if mask.any():
        dt.loc[mask] = pd.to_datetime(series[mask], errors="coerce", dayfirst=True)
    return dt


def norm_posto(v):
    txt = str(v).upper().strip()
    if "QG09" in txt:
        return "QG09"
    if "QG07" in txt:
        return "QG07"
    return txt


def detect_falha_col(df):
    cols_norm = {str(c).strip().upper(): c for c in df.columns}
    for cand in FALHA_CANDIDATES:
        if cand.upper() in cols_norm:
            return cols_norm[cand.upper()]
    for c in df.columns:
        cu = str(c).strip().upper()
        if "FALHA" in cu or "DEFEITO" in cu:
            return c
    return None


def prepare(df, falha_col=None):
    w = df.copy()
    w["DT_HR_INSPECAO"] = parse_dt(w["DT_HR_INSPECAO"])
    w["C_DPU_QG_AMARELO"] = pd.to_numeric(w["C_DPU_QG_AMARELO"], errors="coerce").fillna(0)
    w["NR_WO"] = w["NR_WO"].astype(str).str.strip()
    w["CD_POSTO_CN"] = w["CD_POSTO_CN"].astype(str).map(norm_posto)
    if falha_col and falha_col in w.columns:
        w["FALHA_PARETO"] = w[falha_col].fillna("").astype(str).str.strip()
    else:
        detected = detect_falha_col(w)
        w["FALHA_PARETO"] = w[detected].fillna("").astype(str).str.strip() if detected else ""
    w = w[w["CD_POSTO_CN"].isin(POSTOS)].copy()
    return w[w["DT_HR_INSPECAO"].notna()].copy()


def upload_overlap_warning(conn, df):
    warnings = []
    if df is None or df.empty:
        return warnings
    for (year, posto), part in df.groupby([df["DT_HR_INSPECAO"].dt.year, "CD_POSTO_CN"]):
        new_min = part["DT_HR_INSPECAO"].dt.date.min()
        new_max = part["DT_HR_INSPECAO"].dt.date.max()
        old_min, old_max = existing_range_for_posto_year(conn, posto, int(year))
        if old_min is None:
            continue
        overlap_start = max(new_min, old_min)
        overlap_end = min(new_max, old_max)
        if overlap_start <= overlap_end:
            warnings.append({"texto": f'Este arquivo cobre datas ja existentes entre {overlap_start.strftime("%d/%m")} e {overlap_end.strftime("%d/%m")}.', "posto": posto, "ano": int(year)})
    return warnings


def preview_file_impact(conn, df):
    if df is None or df.empty:
        return pd.DataFrame(), []
    overlaps = upload_overlap_warning(conn, df)
    overlap_keys = {(x["posto"], x["ano"]) for x in overlaps}
    rows = []
    for (year, posto), part in df.groupby([df["DT_HR_INSPECAO"].dt.year, "CD_POSTO_CN"]):
        rows.append({
            "Posto": posto,
            "Ano": int(year),
            "Data minima do arquivo": part["DT_HR_INSPECAO"].dt.date.min().strftime("%d/%m/%Y"),
            "Data maxima do arquivo": part["DT_HR_INSPECAO"].dt.date.max().strftime("%d/%m/%Y"),
            "Linhas do arquivo": int(len(part)),
            "Falhas preenchidas": int((part["FALHA_PARETO"].astype(str).str.strip() != "").sum()),
            "Sobreposicao": "Sim" if (posto, int(year)) in overlap_keys else "Nao",
        })
    return pd.DataFrame(rows), overlaps


def load_merged_year_df(conn, posto, year):
    df = pd.read_sql_query(
        "SELECT upload_id, nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN, COALESCE(falha, '') AS FALHA_PARETO FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=? ORDER BY upload_id ASC, id ASC",
        conn,
        params=[posto, str(year)],
    )
    if df.empty:
        return df
    df["DT_HR_INSPECAO"] = pd.to_datetime(df["DT_HR_INSPECAO"], errors="coerce")
    df["C_DPU_QG_AMARELO"] = pd.to_numeric(df["C_DPU_QG_AMARELO"], errors="coerce").fillna(0)
    df["CD_POSTO_CN"] = df["CD_POSTO_CN"].astype(str).map(norm_posto)
    df["NR_WO"] = df["NR_WO"].astype(str).str.strip()
    df["FALHA_PARETO"] = df["FALHA_PARETO"].fillna("").astype(str).str.strip()
    df = df[df["DT_HR_INSPECAO"].notna()].copy()
    return df.drop_duplicates(subset=["NR_WO", "DT_HR_INSPECAO", "CD_POSTO_CN"], keep="last").reset_index(drop=True)


def load_pareto_df(conn, posto, year):
    df = pd.read_sql_query(
        "SELECT nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, cd_posto_cn AS CD_POSTO_CN, COALESCE(falha, '') AS FALHA_PARETO FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?",
        conn,
        params=[posto, str(year)],
    )
    if df.empty:
        return df
    df["DT_HR_INSPECAO"] = pd.to_datetime(df["DT_HR_INSPECAO"], errors="coerce")
    df["FALHA_PARETO"] = df["FALHA_PARETO"].fillna("").astype(str).str.strip()
    df["CD_POSTO_CN"] = df["CD_POSTO_CN"].astype(str).map(norm_posto)
    return df[(df["CD_POSTO_CN"].isin(POSTOS)) & (df["FALHA_PARETO"] != "")].copy()

# -------------------- Calculations --------------------
def calc_rft(df, start_date, end_date):
    sdt = datetime.combine(start_date, time(0, 0, 0))
    edt = datetime.combine(end_date, time(23, 59, 59))
    f = df[(df["DT_HR_INSPECAO"] >= sdt) & (df["DT_HR_INSPECAO"] <= edt)].copy()
    if f.empty:
        return {"rft_pct": None, "total": 0, "good": 0, "bad": 0}
    grp = f.groupby("NR_WO", as_index=False)["C_DPU_QG_AMARELO"].sum()
    grp["RFT"] = (grp["C_DPU_QG_AMARELO"] == 0).astype(int)
    total = int(len(grp))
    good = int(grp["RFT"].sum())
    bad = total - good
    return {"rft_pct": round(good / total * 100, 2) if total else None, "total": total, "good": good, "bad": bad}


def year_close_info(df, year):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year]
    if ydf.empty:
        return False, None, "Sem dados"
    max_d = ydf["DT_HR_INSPECAO"].dt.date.max()
    cutoff = date(year, 12, YEAR_CLOSE_DAY)
    if max_d >= cutoff:
        return True, max_d, "Fechado em " + max_d.strftime("%d/%m/%Y")
    return False, None, "Ate " + max_d.strftime("%d/%m/%Y")


def week_options(df, year):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year].copy()
    if ydf.empty:
        return []
    dates = sorted(ydf["DT_HR_INSPECAO"].dt.date.unique().tolist())
    mondays = sorted({d - timedelta(days=d.weekday()) for d in dates})
    return [(f'Semana {i:02d} - {m.strftime("%d/%m/%Y")} a {(m + timedelta(days=6)).strftime("%d/%m/%Y")}', m, m + timedelta(days=6)) for i, m in enumerate(mondays, start=1)]


def month_options(df, year):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year].copy()
    if ydf.empty:
        return []
    opts = []
    for m in sorted(ydf["DT_HR_INSPECAO"].dt.month.unique().tolist()):
        s = date(year, int(m), 1)
        e = date(year, int(m), monthrange(year, int(m))[1])
        opts.append((f'{s.strftime("%m/%Y")} - {s.strftime("%d/%m/%Y")} a {e.strftime("%d/%m/%Y")}', s, e))
    return opts


def resolve_period_selection(df, ano, mode):
    min_d = df["DT_HR_INSPECAO"].dt.date.min()
    max_d = df["DT_HR_INSPECAO"].dt.date.max()
    label = f"Ano {ano}"
    rng = (date(ano, 1, 1), max_d)
    if mode == "Diario":
        saved = ls_get("dia", "")
        try:
            default = datetime.fromisoformat(saved).date() if saved else max_d
        except Exception:
            default = max_d
        if default < min_d or default > max_d:
            default = max_d
        sel = st.sidebar.date_input("Dia", value=default, min_value=min_d, max_value=max_d, format="DD/MM/YYYY", key="day_v97")
        ls_set("dia", sel.isoformat())
        label = sel.strftime("%d/%m/%Y")
        rng = (sel, sel)
    elif mode == "Semanal":
        opts = week_options(df, ano)
        labels = [x[0] for x in opts]
        if not labels:
            return min_d, max_d, label, rng, False
        saved = ls_get("semana_label", "")
        idx = labels.index(saved) if saved in labels else len(labels) - 1
        chose = st.sidebar.selectbox("Semana do ano", labels, index=idx, key="week_v97")
        ls_set("semana_label", chose)
        found = next(x for x in opts if x[0] == chose)
        label = chose
        rng = (found[1], found[2])
    elif mode == "Mensal":
        opts = month_options(df, ano)
        labels = [x[0] for x in opts]
        if not labels:
            return min_d, max_d, label, rng, False
        saved = ls_get("mes_label", "")
        idx = labels.index(saved) if saved in labels else len(labels) - 1
        chose = st.sidebar.selectbox("Mes do ano", labels, index=idx, key="month_v97")
        ls_set("mes_label", chose)
        found = next(x for x in opts if x[0] == chose)
        label = chose
        rng = (found[1], found[2])
    return min_d, max_d, label, rng, True


def compute_selected_metrics(df, ano, mode, selected_range, closed_year, year_end, max_date):
    daily = weekly = monthly = yearly = ytd = None
    start, end = selected_range
    if mode == "Diario":
        selected = start
        daily = calc_rft(df, selected, selected)
        ws = selected - timedelta(days=selected.weekday())
        we = ws + timedelta(days=6)
        weekly = calc_rft(df, ws, we)
        ms = date(ano, selected.month, 1)
        me = date(ano, selected.month, monthrange(ano, selected.month)[1])
        monthly = calc_rft(df, ms, me)
        ytd = calc_rft(df, date(ano, 1, 1), selected)
    elif mode == "Semanal":
        weekly = calc_rft(df, start, end)
        ytd = calc_rft(df, date(ano, 1, 1), min(end, max_date))
    elif mode == "Mensal":
        monthly = calc_rft(df, start, end)
        ytd = calc_rft(df, date(ano, 1, 1), min(end, max_date))
    else:
        ytd = calc_rft(df, date(ano, 1, 1), max_date)
    yearly = calc_rft(df, date(ano, 1, 1), year_end) if closed_year and year_end is not None else None
    return {"daily": daily, "weekly": weekly, "monthly": monthly, "yearly": yearly, "ytd": ytd}


def monthly_trend(df, year, meta):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year].copy()
    if ydf.empty:
        return pd.DataFrame(columns=["Mes", "RFT", "Meta"])
    rows = []
    for m in sorted(ydf["DT_HR_INSPECAO"].dt.month.unique().tolist()):
        s = date(year, int(m), 1)
        e = date(year, int(m), monthrange(year, int(m))[1])
        res = calc_rft(ydf, s, e)
        rows.append({"Mes": s.strftime("%m/%Y"), "RFT": res["rft_pct"] or 0, "Meta": meta})
    return pd.DataFrame(rows)


def weekly_trend(df, year):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year].copy()
    if ydf.empty:
        return pd.DataFrame(columns=["Semana", "RFT"])
    rows = []
    for label, ws, we in week_options(ydf, year):
        res = calc_rft(ydf, ws, we)
        rows.append({"Semana": label.split("-")[0].strip(), "RFT": res["rft_pct"] or 0})
    return pd.DataFrame(rows)


def day_history_df(df):
    if df.empty:
        return pd.DataFrame(columns=["Dia", "RFT"])
    rows = []
    for d in sorted(df["DT_HR_INSPECAO"].dt.date.unique().tolist()):
        rows.append({"Dia": d.strftime("%d/%m/%Y"), "RFT": calc_rft(df, d, d)["rft_pct"] or 0})
    return pd.DataFrame(rows)


def pareto_table(df):
    if df.empty:
        return pd.DataFrame(columns=["Rank", "Falha", "Quantidade", "%", "% Acumulado"])
    counts = df["FALHA_PARETO"].value_counts().head(10).reset_index()
    counts.columns = ["Falha", "Quantidade"]
    total = counts["Quantidade"].sum()
    counts["%"] = (counts["Quantidade"] / total * 100).round(2) if total else 0
    counts["% Acumulado"] = counts["%"].cumsum().round(2)
    counts.insert(0, "Rank", range(1, len(counts) + 1))
    return counts

# -------------------- UI helpers --------------------
def format_pct(v):
    return "Sem dados" if v is None or pd.isna(v) else f"{v:.2f}".replace(".", ",") + "%"


def status_css(v, meta):
    if v is None or pd.isna(v):
        return "neutral"
    return "ok" if v >= meta else "bad"


def metric_card_html(title, result, subtitle, meta):
    if result is None or result["rft_pct"] is None:
        value = "Sem dados"
        css = "neutral"
        aux = subtitle
    else:
        value = format_pct(result["rft_pct"])
        css = status_css(result["rft_pct"], meta)
        aux = f"{subtitle}<br>WOs boas: {result['good']} | ruins: {result['bad']} | total: {result['total']}"
    return f'<div class="metric-box"><div class="muted">{title}</div><div style="font-size:2rem;font-weight:900;margin:.35rem 0;" class="{css}">{value}</div><div class="muted">{aux}</div></div>'


def render_meta_resultado(metrics, meta):
    cur = metrics["ytd"] if metrics["ytd"] is not None else metrics["monthly"]
    pct = None if cur is None else cur["rft_pct"]
    diff = "Sem dados" if pct is None else f"{(pct - meta):+.2f}".replace(".", ",") + " p.p."
    val = "Sem dados" if pct is None else f"{pct:.2f}".replace(".", ",") + "%"
    css = status_css(pct, meta)
    st.markdown(
        '<div class="panel"><div style="font-size:1.08rem;font-weight:800;">Meta x resultado</div><div class="muted">Regra visual aplicada conforme sua configuracao.</div>'
        + f'<div style="font-size:2.15rem;font-weight:900;margin:.5rem 0;" class="{css}">{val}</div>'
        + f'<div class="muted">Meta: <b>{str(meta).replace(".", ",")}%</b><br>Diferenca: <b>{diff}</b><br>Regra: abaixo da meta = vermelho | acima ou igual a meta = verde</div></div>',
        unsafe_allow_html=True,
    )


def render_resumo(info, posto, ano, min_d, max_d, label, meta):
    st.markdown('<div class="panel"><div style="font-size:1.08rem;font-weight:800;">Resumo executivo do recorte</div>', unsafe_allow_html=True)
    rows = [
        ("Recorte", label),
        ("Ultimo arquivo salvo", info["file_name"] if info else "-"),
        ("Ultimo upload", info["uploaded_at"] if info else "-"),
        ("Posto", posto),
        ("Ano", str(ano)),
        ("Janela consolidada", f'{min_d.strftime("%d/%m/%Y")} ate {max_d.strftime("%d/%m/%Y")}'),
        ("Meta ativa", str(meta).replace(".", ",") + "%"),
    ]
    for k, v in rows:
        st.markdown(f'<div class="kv"><div class="muted">{k}</div><div><strong>{v}</strong></div></div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_pareto_chart(pt):
    if pt.empty:
        st.info("Não há falhas preenchidas para montar o Pareto desse posto/ano.")
        return
    st.bar_chart(pt[["Falha", "Quantidade"]].set_index("Falha"), use_container_width=True)
    st.caption("Curva acumulada (%)")
    st.line_chart(pt[["Falha", "% Acumulado"]].set_index("Falha"), use_container_width=True)

# -------------------- Main --------------------
def main():
    conn = get_conn()
    init_db(conn)
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="hero"><div style="font-size:1.75rem;font-weight:900;">RFT Automatico - V9.7</div><div class="muted">Versão consolidada: Pareto de Falhas sem matplotlib, upload simples e requisitos mínimos.</div></div>', unsafe_allow_html=True)

    with st.sidebar:
        posto = st.radio("Posto", POSTOS, index=POSTOS.index(ls_get("posto", POSTO_PADRAO)) if ls_get("posto", POSTO_PADRAO) in POSTOS else 0, horizontal=True)
        ls_set("posto", posto)
        anos = available_years(conn, posto)
        if anos:
            prev = ls_get("ano", None)
            try:
                prev = int(prev) if prev is not None else None
            except Exception:
                prev = None
            ano = st.selectbox("Ano", anos, index=anos.index(prev) if prev in anos else len(anos) - 1)
            ls_set("ano", ano)
        else:
            ano = None
            st.info("Sem dados salvos para este posto.")
        modes = ["Diario", "Semanal", "Mensal", "Anual"]
        mode = st.radio("Modo", modes, index=modes.index(ls_get("modo", "Diario")) if ls_get("modo", "Diario") in modes else 0)
        ls_set("modo", mode)
        try:
            saved = float(str(ls_get("meta_rft", DEFAULT_META_RFT)).replace(",", "."))
        except Exception:
            saved = DEFAULT_META_RFT
        meta = st.number_input("Meta RFT (%)", min_value=0.0, max_value=100.0, value=float(saved), step=0.1)
        ls_set("meta_rft", meta)
        st.caption("Regra visual: abaixo da meta = vermelho | acima ou igual a meta = verde")

    tabs = st.tabs(["Dashboard", "Tendencia", "Pareto de Falhas", "Base & Upload", "Historico", "Sobre"])
    latest = latest_upload_id_for_year(conn, posto, ano) if ano is not None else None
    info = upload_info(conn, latest) if latest is not None else None
    df = load_merged_year_df(conn, posto, ano) if latest is not None else pd.DataFrame()

    with tabs[0]:
        if ano is None or df.empty:
            st.info("Sem histórico para esse ano/posto.")
        else:
            closed, year_end, status = year_close_info(df, ano)
            min_d, max_d, label, rng, valid = resolve_period_selection(df, ano, mode)
            if not valid:
                st.info("Nenhum período disponível para o modo selecionado.")
            else:
                metrics = compute_selected_metrics(df, ano, mode, rng, closed, year_end, max_d)
                st.markdown(f'<div class="pill">Posto: <strong>{posto}</strong></div><div class="pill">Ano: <strong>{ano}</strong></div><div class="pill">Fechamento: <strong>{status}</strong></div><div class="pill">Meta: <strong>{str(meta).replace(".", ",")}%</strong></div>', unsafe_allow_html=True)
                cols = st.columns(5)
                items = [
                    ("RFT Diario", "Dia selecionado", "daily"),
                    ("RFT Semanal", "Consolidacao semanal", "weekly"),
                    ("RFT Mensal", "Consolidacao mensal", "monthly"),
                    ("RFT Anual", "Ano até o último dia trabalhado de dezembro", "yearly"),
                    ("RFT YTD", "Acumulado até o recorte", "ytd"),
                ]
                for col, (title, sub, key) in zip(cols, items):
                    with col:
                        st.markdown(metric_card_html(title, metrics[key], sub, meta), unsafe_allow_html=True)
                left, right = st.columns([1.15, 1.0])
                with left:
                    render_resumo(info, posto, ano, min_d, max_d, label, meta)
                with right:
                    render_meta_resultado(metrics, meta)
                hd = day_history_df(df)
                st.markdown('<div class="panel"><div style="font-size:1.08rem;font-weight:800;">Leitura diaria do RFT</div><div class="muted">Historico dia a dia dentro da base consolidada.</div>', unsafe_allow_html=True)
                if not hd.empty:
                    st.line_chart(hd.set_index("Dia"), use_container_width=True)
                else:
                    st.info("Sem dados diários disponíveis.")
                st.markdown("</div>", unsafe_allow_html=True)

    with tabs[1]:
        if ano is None or df.empty:
            st.info("Sem histórico válido para a tendência.")
        else:
            mdf = monthly_trend(df, ano, meta)
            wdf = weekly_trend(df, ano)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown('<div class="panel"><div style="font-size:1.08rem;font-weight:800;">Tendencia mensal</div>', unsafe_allow_html=True)
                if not mdf.empty:
                    st.bar_chart(mdf.set_index("Mes")[["RFT", "Meta"]], use_container_width=True)
                    st.dataframe(mdf, use_container_width=True, hide_index=True)
                else:
                    st.info("Sem dados mensais disponíveis.")
                st.markdown("</div>", unsafe_allow_html=True)
            with c2:
                st.markdown('<div class="panel"><div style="font-size:1.08rem;font-weight:800;">Tendencia semanal</div>', unsafe_allow_html=True)
                if not wdf.empty:
                    st.bar_chart(wdf.set_index("Semana"), use_container_width=True)
                    st.dataframe(wdf, use_container_width=True, hide_index=True)
                else:
                    st.info("Sem dados semanais disponíveis.")
                st.markdown("</div>", unsafe_allow_html=True)

    with tabs[2]:
        st.markdown('<div class="panel"><div style="font-size:1.08rem;font-weight:800;">Pareto de Falhas</div><div class="muted">Top 10 falhas por QG09 ou QG07. Demais postos são ignorados.</div>', unsafe_allow_html=True)
        anos_p = available_years_any(conn)
        if not anos_p:
            st.info("Sem dados para Pareto. Faça upload de uma base com coluna de falha/defeito.")
        else:
            def_year = ano if ano in anos_p else anos_p[-1]
            p_ano = st.selectbox("Ano do Pareto", anos_p, index=anos_p.index(def_year), key="pareto_year_v97")
            p_posto = st.radio("Posto do Pareto", POSTOS, index=0, horizontal=True, key="pareto_posto_v97")
            pt = pareto_table(load_pareto_df(conn, p_posto, p_ano))
            render_pareto_chart(pt)
            if not pt.empty:
                show = pt.copy()
                show["%"] = show["%"].map(lambda x: f"{x:.2f}".replace(".", ",") + "%")
                show["% Acumulado"] = show["% Acumulado"].map(lambda x: f"{x:.2f}".replace(".", ",") + "%")
                st.dataframe(show, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with tabs[3]:
        st.markdown('<div class="panel"><div style="font-size:1.08rem;font-weight:800;">Base & Upload</div>', unsafe_allow_html=True)
        import_mode = st.radio("Modo de importação", ["Somar ao historico", "Substituir periodo sobreposto", "Reprocessar o ano inteiro"], key="import_mode_v97")
        uploaded = st.file_uploader("Base operacional atual (.xlsx, .xls ou .csv)", type=["xlsx", "xls", "csv"], key="file_uploader_v97")
        prepared = None
        if uploaded is not None:
            try:
                raw = read_file(uploaded)
                ok, miss = validate_df(raw)
                if not ok:
                    st.error("Base operacional invalida: " + ", ".join(miss))
                else:
                    detected = detect_falha_col(raw)
                    opts = ["Detectar automaticamente / sem coluna"] + [c for c in raw.columns if c not in REQ]
                    idx = opts.index(detected) if detected in opts else 0
                    chosen = st.selectbox("Coluna para Pareto de Falhas", opts, index=idx, key="falha_col_v97")
                    falha_col = None if chosen == opts[0] else chosen
                    prepared = prepare(raw, falha_col=falha_col)
                    impact, overlaps = preview_file_impact(conn, prepared)
                    st.success(f"Arquivo carregado: {uploaded.name} | Linhas válidas QG09/QG07: {len(prepared)}")
                    if detected or falha_col:
                        st.info(f"Coluna de falha usada no Pareto: {falha_col or detected}")
                    else:
                        st.warning("Nenhuma coluna de falha detectada. O RFT será salvo normalmente, mas o Pareto ficará vazio para esse upload.")
                    if not impact.empty:
                        st.dataframe(impact, use_container_width=True, hide_index=True)
                    for item in overlaps:
                        st.warning(item["texto"])
            except Exception as err:
                st.error(f"Erro ao ler a base operacional: {err}")
        if st.button("Salvar arquivo localmente", type="primary", use_container_width=True, key="save_upload_v97"):
            if uploaded is None:
                st.error("Selecione um arquivo antes de salvar.")
            elif prepared is None:
                st.error("O arquivo foi anexado, mas houve erro na leitura. Corrija e tente novamente.")
            elif prepared.empty:
                st.error("A base foi lida, mas não restaram linhas válidas após o tratamento.")
            else:
                affected = apply_import_mode(conn, prepared, import_mode)
                uid = create_upload(conn, uploaded.name, len(prepared), message="Base recebida e salva localmente.")
                save_raw(conn, uid, prepared)
                msg = "Arquivo salvo com sucesso." + (" " + " | ".join(affected) if affected else "")
                update_upload(conn, uid, "PROCESSADO", msg)
                st.success(msg)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with tabs[4]:
        st.markdown('<div class="panel"><div style="font-size:1.08rem;font-weight:800;">Historico</div>', unsafe_allow_html=True)
        hist = uploads_table(conn)
        if hist.empty:
            st.info("Os uploads processados aparecerão aqui.")
        else:
            st.dataframe(hist, use_container_width=True, hide_index=True)
            selected_id = st.selectbox("Selecionar upload", hist["id"].tolist(), format_func=lambda x: f"Upload {x}", key="history_select_v97")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("Ver detalhes do upload", use_container_width=True, key="history_view_v97"):
                    detail = upload_detail_df(conn, selected_id)
                    if detail.empty:
                        st.warning("Upload sem detalhes disponíveis.")
                    else:
                        st.dataframe(detail.head(200), use_container_width=True, hide_index=True)
            with c2:
                if st.button("Reprocessar upload", use_container_width=True, key="history_reprocess_v97"):
                    nid = reprocess_upload(conn, selected_id)
                    st.success(f"Upload reprocessado com sucesso. Novo upload: {nid}." if nid else "Não foi possível reprocessar o upload.")
                    st.rerun()
            with c3:
                if st.button("Excluir upload específico", use_container_width=True, key="history_delete_v97"):
                    delete_upload(conn, selected_id)
                    st.success("Upload excluído com sucesso.")
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with tabs[5]:
        st.markdown('<div class="panel"><div style="font-size:1.08rem;font-weight:800;">Sobre</div><div class="muted">V9.7 consolida o Pareto de Falhas sem matplotlib. Use apenas app_rft_streamlit_v9_7.py e requirements.txt no GitHub.</div></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
