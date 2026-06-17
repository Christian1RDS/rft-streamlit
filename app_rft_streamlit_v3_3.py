import io
import sqlite3
from datetime import date, datetime, time, timedelta
from calendar import monthrange
from typing import Optional, Tuple, Dict, Any

import pandas as pd
import streamlit as st

st.set_page_config(page_title="RFT Automático — V3.3", page_icon="📈", layout="wide")

DB_PATH = "rft_phase1.db"
REQUIRED_COLUMNS = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO"]

# =====================================================
# ESTILO
# =====================================================
CUSTOM_CSS = """
<style>
    .block-container {
        max-width: 1440px;
        padding-top: 1rem;
        padding-bottom: 2rem;
    }
    .hero {
        background: linear-gradient(135deg, #0f2747 0%, #1f6fb2 100%);
        color: white;
        padding: 1.4rem 1.6rem;
        border-radius: 18px;
        box-shadow: 0 8px 24px rgba(15,39,71,0.20);
        margin-bottom: 1rem;
    }
    .hero h1 { margin: 0; font-size: 2rem; }
    .hero p { margin: 0.35rem 0 0 0; opacity: 0.96; }
    .section-title {
        font-size: 1.12rem;
        font-weight: 700;
        color: #12355b;
        margin-top: 0.75rem;
        margin-bottom: 0.5rem;
    }
    .card {
        background: white;
        border: 1px solid #e6eef7;
        border-left: 6px solid #1f6fb2;
        border-radius: 16px;
        padding: 1rem 1rem 0.85rem 1rem;
        box-shadow: 0 6px 18px rgba(10,35,66,0.06);
        min-height: 132px;
    }
    .card-ok { border-left-color: #2c8f4e; }
    .card-warn { border-left-color: #d97706; }
    .card-crit { border-left-color: #c2410c; }
    .card-title {
        color: #5d6b78;
        font-size: 0.92rem;
        font-weight: 600;
        margin-bottom: 0.15rem;
    }
    .card-value {
        color: #12355b;
        font-size: 1.95rem;
        font-weight: 800;
        line-height: 1.1;
        margin-bottom: 0.25rem;
    }
    .card-sub {
        color: #6f7f8d;
        font-size: 0.82rem;
    }
    .chip {
        display: inline-block;
        background: #eef5fb;
        color: #12355b;
        border: 1px solid #d7e7f5;
        border-radius: 999px;
        padding: 0.35rem 0.8rem;
        margin: 0 0.35rem 0.35rem 0;
        font-size: 0.9rem;
    }
    .status-box-ok, .status-box-warn, .status-box-crit {
        border-radius: 14px;
        padding: 0.9rem 1rem;
        font-weight: 600;
        margin-top: 0.25rem;
        margin-bottom: 0.5rem;
    }
    .status-box-ok { background: #edf8f1; color: #166534; border: 1px solid #b7dfc2; }
    .status-box-warn { background: #fff7ed; color: #9a3412; border: 1px solid #f7d4b3; }
    .status-box-crit { background: #fff1f2; color: #9f1239; border: 1px solid #fecdd3; }
    .mini {
        background: #f8fbfe;
        border: 1px solid #e8f0f8;
        border-radius: 14px;
        padding: 0.95rem 1rem;
        min-height: 92px;
    }
    .mini-title { color: #5a6a7a; font-size: 0.9rem; font-weight: 600; margin-bottom: 0.2rem; }
    .mini-value { color: #12355b; font-size: 1.2rem; font-weight: 800; }
    div.stButton > button[kind="primary"] {
        border-radius: 12px;
        height: 3rem;
        font-weight: 700;
        border: none;
    }
    div.stButton > button {
        border-radius: 12px;
        height: 2.85rem;
        font-weight: 600;
    }
</style>
"""


# =====================================================
# BANCO DE DADOS
# =====================================================
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
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
            cd_modelo TEXT,
            cd_posto_cn TEXT,
            anomalia_falha TEXT,
            FOREIGN KEY (upload_id) REFERENCES upload_log(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_calendar (
            work_date TEXT PRIMARY KEY,
            is_working INTEGER NOT NULL,
            note TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kpi_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            reference_date TEXT NOT NULL,
            daily_effective_date TEXT,
            weekly_start TEXT,
            weekly_end TEXT,
            monthly_start TEXT,
            monthly_end TEXT,
            daily_rft_pct REAL,
            weekly_rft_pct REAL,
            monthly_rft_pct REAL,
            ytd_rft_pct REAL,
            prev_2025_rft_pct REAL,
            note_daily TEXT,
            total_wos_daily INTEGER,
            total_wos_weekly INTEGER,
            total_wos_monthly INTEGER,
            good_wos_daily INTEGER,
            good_wos_weekly INTEGER,
            good_wos_monthly INTEGER,
            bad_wos_daily INTEGER,
            bad_wos_weekly INTEGER,
            bad_wos_monthly INTEGER,
            FOREIGN KEY (upload_id) REFERENCES upload_log(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()


# =====================================================
# LEITURA DO ARQUIVO
# =====================================================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
    return df


def try_read_csv(file_bytes: bytes) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-16", "latin1"]
    seps = [None, ";", ",", "\t"]
    last_err = None
    for enc in encodings:
        for sep in seps:
            try:
                if sep is None:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, sep=None, engine="python")
                else:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, sep=sep)
                df = normalize_columns(df)
                if len(df.columns) >= 3:
                    return df
            except Exception as e:
                last_err = e
    raise ValueError(f"Não foi possível ler o CSV. Detalhe: {last_err}")


def load_uploaded_file(uploaded_file) -> pd.DataFrame:
    ext = uploaded_file.name.lower().split(".")[-1]
    file_bytes = uploaded_file.getvalue()
    if ext == "csv":
        df = try_read_csv(file_bytes)
    elif ext in ["xlsx", "xls"]:
        engine = "openpyxl" if ext == "xlsx" else "xlrd"
        df = pd.read_excel(io.BytesIO(file_bytes), engine=engine)
        df = normalize_columns(df)
    else:
        raise ValueError("Formato não suportado. Use .xlsx, .xls ou .csv")
    return df


def validate_dataframe(df: pd.DataFrame) -> Tuple[bool, str]:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return False, "A planilha não contém as colunas obrigatórias: " + ", ".join(missing)
    return True, ""


def parse_datetime_series(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    mask = dt.isna() & series.notna()
    if mask.any():
        dt2 = pd.to_datetime(series[mask], errors="coerce", dayfirst=True)
        dt.loc[mask] = dt2
    return dt


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["DT_HR_INSPECAO"] = parse_datetime_series(work["DT_HR_INSPECAO"])
    work["C_DPU_QG_AMARELO"] = pd.to_numeric(work["C_DPU_QG_AMARELO"], errors="coerce").fillna(0)
    work["NR_WO"] = work["NR_WO"].astype(str).str.strip()
    for optional in ["CD_MODELO", "CD_POSTO_CN", "ANOMALIA_FALHA"]:
        if optional not in work.columns:
            work[optional] = None
    work = work[work["DT_HR_INSPECAO"].notna()].copy()
    return work


# =====================================================
# CALENDÁRIO DE TRABALHO
# =====================================================
def get_workday_override(conn: sqlite3.Connection, d: date) -> Optional[bool]:
    row = conn.execute("SELECT is_working FROM work_calendar WHERE work_date = ?", (d.isoformat(),)).fetchone()
    if row is None:
        return None
    return bool(row[0])


def is_working_day(conn: sqlite3.Connection, d: date) -> bool:
    override = get_workday_override(conn, d)
    if override is not None:
        return override
    if d.weekday() == 6:
        return False
    if d.weekday() == 5:
        return False
    return True


def set_workday(conn: sqlite3.Connection, d: date, is_working: bool, note: str = "") -> None:
    conn.execute(
        """
        INSERT INTO work_calendar (work_date, is_working, note, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(work_date) DO UPDATE SET
            is_working=excluded.is_working,
            note=excluded.note,
            updated_at=excluded.updated_at
        """,
        (d.isoformat(), 1 if is_working else 0, note, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def previous_working_day(conn: sqlite3.Connection, ref_date: date) -> date:
    d = ref_date - timedelta(days=1)
    for _ in range(20):
        if is_working_day(conn, d):
            return d
        d -= timedelta(days=1)
    return d


def resolve_daily_effective_date(conn: sqlite3.Connection, reference_date: date) -> Tuple[date, str]:
    if reference_date.weekday() == 0:
        saturday = reference_date - timedelta(days=2)
        if is_working_day(conn, saturday):
            return saturday, "Segunda-feira usando D-2 (sábado marcado como trabalhado)."
        prev_day = previous_working_day(conn, reference_date)
        return prev_day, "Segunda-feira usando o último dia útil anterior, pois sábado não está marcado como trabalhado."
    prev_day = previous_working_day(conn, reference_date)
    return prev_day, "Terça a sábado usando D-1 (último dia útil anterior)."


def resolve_weekly_s1(reference_date: date) -> Tuple[date, date]:
    current_monday = reference_date - timedelta(days=reference_date.weekday())
    prev_monday = current_monday - timedelta(days=7)
    prev_saturday = prev_monday + timedelta(days=5)
    return prev_monday, prev_saturday


def resolve_monthly_period(reference_date: date) -> Tuple[date, date]:
    start = reference_date.replace(day=1)
    end = reference_date.replace(day=monthrange(reference_date.year, reference_date.month)[1])
    return start, end


# =====================================================
# CÁLCULO
# =====================================================
def format_pct_br(value: Optional[float]) -> str:
    if value is None or pd.isna(value):
        return "Sem dados"
    return f"{value:.2f}".replace(".", ",") + "%"


def format_date_br(d: Optional[date]) -> str:
    if d is None:
        return "-"
    return d.strftime("%d/%m/%Y")


def compare_text(current: Optional[float], previous: Optional[float]) -> str:
    if current is None or previous is None or pd.isna(current) or pd.isna(previous):
        return "Sem comparação"
    diff = round(current - previous, 2)
    prefix = "+" if diff > 0 else ""
    return f"{prefix}{str(diff).replace('.', ',')} p.p."


def status_class(value: Optional[float], target: float) -> str:
    if value is None or pd.isna(value):
        return "card-warn"
    if value >= target:
        return "card-ok"
    if value >= target - 2:
        return "card-warn"
    return "card-crit"


def alert_box_html(title: str, message: str, level: str = "ok") -> str:
    css = {"ok": "status-box-ok", "warn": "status-box-warn", "crit": "status-box-crit"}.get(level, "status-box-ok")
    return f"<div class='{css}'><strong>{title}</strong><br>{message}</div>"


def metric_card(title: str, value: str, subtitle: str = "", css_class: str = "") -> str:
    classes = f"card {css_class}".strip()
    return f"""
    <div class='{classes}'>
        <div class='card-title'>{title}</div>
        <div class='card-value'>{value}</div>
        <div class='card-sub'>{subtitle}</div>
    </div>
    """


def compute_rft(df: pd.DataFrame, start_date: date, end_date: date) -> Dict[str, Any]:
    start_dt = datetime.combine(start_date, time(0, 0, 0))
    end_dt = datetime.combine(end_date, time(23, 59, 59))
    filtered = df[(df["DT_HR_INSPECAO"] >= start_dt) & (df["DT_HR_INSPECAO"] <= end_dt)].copy()
    if filtered.empty:
        return {
            "rft_pct": None,
            "total_wos": 0,
            "good_wos": 0,
            "bad_wos": 0,
            "table_wo": pd.DataFrame(columns=["NR_WO", "SOMA_C_DPU_QG_AMARELO", "RFT"]),
            "raw": filtered,
        }

    grouped = (
        filtered.groupby("NR_WO", as_index=False)["C_DPU_QG_AMARELO"]
        .sum()
        .rename(columns={"C_DPU_QG_AMARELO": "SOMA_C_DPU_QG_AMARELO"})
    )
    grouped["RFT"] = (grouped["SOMA_C_DPU_QG_AMARELO"] == 0).astype(int)
    total_wos = int(len(grouped))
    good_wos = int(grouped["RFT"].sum())
    bad_wos = int(total_wos - good_wos)
    rft_pct = round((good_wos / total_wos) * 100, 2) if total_wos else None
    return {
        "rft_pct": rft_pct,
        "total_wos": total_wos,
        "good_wos": good_wos,
        "bad_wos": bad_wos,
        "table_wo": grouped.sort_values(["RFT", "NR_WO"], ascending=[False, True]).reset_index(drop=True),
        "raw": filtered,
    }


def build_snapshot(conn: sqlite3.Connection, upload_id: int, df: pd.DataFrame, reference_date: date) -> Dict[str, Any]:
    daily_effective_date, note_daily = resolve_daily_effective_date(conn, reference_date)
    weekly_start, weekly_end = resolve_weekly_s1(reference_date)
    monthly_start, monthly_end = resolve_monthly_period(reference_date)

    daily = compute_rft(df, daily_effective_date, daily_effective_date)
    weekly = compute_rft(df, weekly_start, weekly_end)
    monthly = compute_rft(df, monthly_start, monthly_end)
    ytd = compute_rft(df, date(reference_date.year, 1, 1), daily_effective_date)
    prev_2025 = compute_rft(df, date(2025, 1, 1), date(2025, 12, 31))

    conn.execute(
        """
        INSERT INTO kpi_snapshots (
            upload_id, created_at, reference_date, daily_effective_date,
            weekly_start, weekly_end, monthly_start, monthly_end,
            daily_rft_pct, weekly_rft_pct, monthly_rft_pct, ytd_rft_pct, prev_2025_rft_pct,
            note_daily,
            total_wos_daily, total_wos_weekly, total_wos_monthly,
            good_wos_daily, good_wos_weekly, good_wos_monthly,
            bad_wos_daily, bad_wos_weekly, bad_wos_monthly
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            upload_id,
            datetime.now().isoformat(timespec="seconds"),
            reference_date.isoformat(),
            daily_effective_date.isoformat(),
            weekly_start.isoformat(),
            weekly_end.isoformat(),
            monthly_start.isoformat(),
            monthly_end.isoformat(),
            daily["rft_pct"], weekly["rft_pct"], monthly["rft_pct"], ytd["rft_pct"], prev_2025["rft_pct"],
            note_daily,
            daily["total_wos"], weekly["total_wos"], monthly["total_wos"],
            daily["good_wos"], weekly["good_wos"], monthly["good_wos"],
            daily["bad_wos"], weekly["bad_wos"], monthly["bad_wos"],
        )
    )
    conn.commit()

    return {
        "reference_date": reference_date,
        "daily_effective_date": daily_effective_date,
        "weekly_start": weekly_start,
        "weekly_end": weekly_end,
        "monthly_start": monthly_start,
        "monthly_end": monthly_end,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "ytd": ytd,
        "prev_2025": prev_2025,
        "note_daily": note_daily,
    }


# =====================================================
# PERSISTÊNCIA
# =====================================================
def create_upload_log(conn: sqlite3.Connection, file_name: str, total_rows: int, status: str, message: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)",
        (file_name, datetime.now().isoformat(timespec="seconds"), int(total_rows), status, message),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_upload_status(conn: sqlite3.Connection, upload_id: int, status: str, message: str = "") -> None:
    conn.execute("UPDATE upload_log SET status = ?, message = ? WHERE id = ?", (status, message, upload_id))
    conn.commit()


def save_raw_data(conn: sqlite3.Connection, upload_id: int, df: pd.DataFrame) -> None:
    records = []
    for _, row in df.iterrows():
        records.append(
            (
                upload_id,
                row.get("NR_WO"),
                row.get("DT_HR_INSPECAO").isoformat(sep=" ", timespec="seconds") if pd.notna(row.get("DT_HR_INSPECAO")) else None,
                float(row.get("C_DPU_QG_AMARELO", 0)) if pd.notna(row.get("C_DPU_QG_AMARELO")) else 0.0,
                row.get("CD_MODELO"),
                row.get("CD_POSTO_CN"),
                row.get("ANOMALIA_FALHA"),
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_inspections (
            upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_modelo, cd_posto_cn, anomalia_falha
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        records,
    )
    conn.commit()


def get_latest_upload(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM upload_log WHERE status = 'PROCESSADO' ORDER BY id DESC LIMIT 1").fetchone()


def get_latest_snapshot(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM kpi_snapshots ORDER BY id DESC LIMIT 1").fetchone()


def get_previous_snapshot(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM kpi_snapshots ORDER BY id DESC LIMIT 2").fetchall()
    if len(rows) < 2:
        return None
    return rows[1]


def get_dataset_by_upload(conn: sqlite3.Connection, upload_id: int) -> pd.DataFrame:
    q = """
        SELECT nr_wo AS NR_WO,
               dt_hr_inspecao AS DT_HR_INSPECAO,
               c_dpu_qg_amarelo AS C_DPU_QG_AMARELO,
               cd_modelo AS CD_MODELO,
               cd_posto_cn AS CD_POSTO_CN,
               anomalia_falha AS ANOMALIA_FALHA
        FROM raw_inspections WHERE upload_id = ?
    """
    df = pd.read_sql_query(q, conn, params=[upload_id])
    if not df.empty:
        df["DT_HR_INSPECAO"] = pd.to_datetime(df["DT_HR_INSPECAO"], errors="coerce")
        df["C_DPU_QG_AMARELO"] = pd.to_numeric(df["C_DPU_QG_AMARELO"], errors="coerce").fillna(0)
    return df


def get_snapshot_history(conn: sqlite3.Connection) -> pd.DataFrame:
    q = """
        SELECT s.created_at AS calculado_em,
               u.file_name AS arquivo,
               s.reference_date AS data_referencia,
               s.daily_effective_date AS diario_efetivo,
               s.daily_rft_pct AS rft_diario,
               s.weekly_rft_pct AS rft_semanal,
               s.monthly_rft_pct AS rft_mensal,
               s.ytd_rft_pct AS rft_ytd,
               s.prev_2025_rft_pct AS rft_2025,
               u.total_rows AS linhas_importadas,
               u.status AS status
        FROM kpi_snapshots s
        JOIN upload_log u ON u.id = s.upload_id
        ORDER BY s.id DESC LIMIT 300
    """
    return pd.read_sql_query(q, conn)


def get_upload_history(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC LIMIT 300",
        conn,
    )


def recalculate_latest(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    latest_upload = get_latest_upload(conn)
    if latest_upload is None:
        return None
    df = get_dataset_by_upload(conn, latest_upload["id"])
    if df.empty:
        return None
    return build_snapshot(conn, latest_upload["id"], df, date.today())


def create_snapshot_export(snapshot: sqlite3.Row, latest_upload: sqlite3.Row, previous_snapshot: Optional[sqlite3.Row]) -> bytes:
    output = io.BytesIO()
    resumo = pd.DataFrame([
        ["Arquivo", latest_upload["file_name"]],
        ["Última atualização", snapshot["created_at"]],
        ["Data de referência", snapshot["reference_date"]],
        ["Diário efetivo", snapshot["daily_effective_date"]],
        ["RFT Diário (%)", snapshot["daily_rft_pct"]],
        ["RFT Semanal S-1 (%)", snapshot["weekly_rft_pct"]],
        ["RFT Mensal (%)", snapshot["monthly_rft_pct"]],
        ["RFT YTD (%)", snapshot["ytd_rft_pct"]],
        ["RFT 2025 (%)", snapshot["prev_2025_rft_pct"]],
        ["Meta (%)", st.session_state.get("target_rft", 95.0)],
        ["Comparação Diário", compare_text(snapshot["daily_rft_pct"], previous_snapshot["daily_rft_pct"] if previous_snapshot else None)],
        ["Comparação Semanal", compare_text(snapshot["weekly_rft_pct"], previous_snapshot["weekly_rft_pct"] if previous_snapshot else None)],
        ["Comparação Mensal", compare_text(snapshot["monthly_rft_pct"], previous_snapshot["monthly_rft_pct"] if previous_snapshot else None)],
        ["Observação diária", snapshot["note_daily"]],
    ], columns=["Campo", "Valor"])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        resumo.to_excel(writer, index=False, sheet_name="Resumo_Snapshot")
    return output.getvalue()


# =====================================================
# UI
# =====================================================
def render_hero():
    st.markdown(
        """
        <div class='hero'>
            <h1>RFT Automático — V3.3</h1>
            <p>Visão de gestão com meta configurável, alertas visuais, comparação entre cargas, exportação do snapshot e evolução histórica.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_controls(conn: sqlite3.Connection):
    st.sidebar.header("Configurações e calendário")
    target = st.sidebar.number_input("Meta de RFT (%)", min_value=0.0, max_value=100.0, value=float(st.session_state.get("target_rft", 95.0)), step=0.5)
    st.session_state["target_rft"] = target

    st.sidebar.caption("Domingo = não trabalhado. Sábado = não trabalhado por padrão e pode ser habilitado manualmente.")
    d = st.sidebar.date_input("Marcar dia no calendário", value=date.today(), format="DD/MM/YYYY")
    current = is_working_day(conn, d)
    worked = st.sidebar.checkbox("Dia trabalhado", value=current)
    note = st.sidebar.text_input("Observação do dia")
    if st.sidebar.button("Salvar calendário", use_container_width=True):
        set_workday(conn, d, worked, note)
        st.sidebar.success("Calendário atualizado.")
        st.rerun()

    with st.sidebar.expander("Sábados e domingos", expanded=False):
        rows = []
        base = date.today()
        for i in range(-14, 45):
            dd = base + timedelta(days=i)
            if dd.weekday() in (5, 6):
                rows.append({
                    "Data": format_date_br(dd),
                    "Dia": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][dd.weekday()],
                    "Trabalhado": "Sim" if is_working_day(conn, dd) else "Não",
                })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_alerts(snapshot: sqlite3.Row, target: float):
    daily = snapshot["daily_rft_pct"]
    weekly = snapshot["weekly_rft_pct"]
    monthly = snapshot["monthly_rft_pct"]

    if daily is not None and daily < target:
        st.markdown(alert_box_html("Alerta diário", f"O RFT diário está abaixo da meta de {format_pct_br(target)}. Resultado atual: {format_pct_br(daily)}.", "crit" if daily < target - 2 else "warn"), unsafe_allow_html=True)
    else:
        st.markdown(alert_box_html("Status diário", f"O RFT diário está em linha com a meta de {format_pct_br(target)}.", "ok"), unsafe_allow_html=True)

    if weekly is not None and weekly < target:
        st.markdown(alert_box_html("Alerta semanal S-1", f"O RFT semanal está abaixo da meta de {format_pct_br(target)}. Resultado atual: {format_pct_br(weekly)}.", "warn"), unsafe_allow_html=True)

    if monthly is not None and monthly < target:
        st.markdown(alert_box_html("Alerta mensal", f"O RFT mensal está abaixo da meta. Resultado atual: {format_pct_br(monthly)}.", "warn"), unsafe_allow_html=True)


def render_home(snapshot: sqlite3.Row, latest_upload: sqlite3.Row, previous_snapshot: Optional[sqlite3.Row], target: float):
    reference_date = datetime.fromisoformat(snapshot["reference_date"]).date()
    daily_effective_date = datetime.fromisoformat(snapshot["daily_effective_date"]).date() if snapshot["daily_effective_date"] else None
    weekly_start = datetime.fromisoformat(snapshot["weekly_start"]).date() if snapshot["weekly_start"] else None
    weekly_end = datetime.fromisoformat(snapshot["weekly_end"]).date() if snapshot["weekly_end"] else None
    monthly_start = datetime.fromisoformat(snapshot["monthly_start"]).date() if snapshot["monthly_start"] else None
    monthly_end = datetime.fromisoformat(snapshot["monthly_end"]).date() if snapshot["monthly_end"] else None

    render_alerts(snapshot, target)

    st.markdown("<div class='section-title'>Painel executivo</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(metric_card("RFT Diário", format_pct_br(snapshot["daily_rft_pct"]), f"Meta: {format_pct_br(target)} | {compare_text(snapshot['daily_rft_pct'], previous_snapshot['daily_rft_pct'] if previous_snapshot else None)}", status_class(snapshot["daily_rft_pct"], target)), unsafe_allow_html=True)
    c2.markdown(metric_card("RFT Semanal S-1", format_pct_br(snapshot["weekly_rft_pct"]), compare_text(snapshot['weekly_rft_pct'], previous_snapshot['weekly_rft_pct'] if previous_snapshot else None), status_class(snapshot["weekly_rft_pct"], target)), unsafe_allow_html=True)
    c3.markdown(metric_card("RFT Mensal", format_pct_br(snapshot["monthly_rft_pct"]), compare_text(snapshot['monthly_rft_pct'], previous_snapshot['monthly_rft_pct'] if previous_snapshot else None), status_class(snapshot["monthly_rft_pct"], target)), unsafe_allow_html=True)
    c4.markdown(metric_card("RFT YTD", format_pct_br(snapshot["ytd_rft_pct"]), "Acumulado anual", status_class(snapshot["ytd_rft_pct"], target)), unsafe_allow_html=True)

    c5, c6, c7, c8 = st.columns(4)
    c5.markdown(metric_card("RFT 2025", format_pct_br(snapshot["prev_2025_rft_pct"]), "Ano completo de 2025"), unsafe_allow_html=True)
    c6.markdown(metric_card("WOs boas (Diário)", str(int(snapshot["good_wos_daily"] or 0)), "Sem defeito"), unsafe_allow_html=True)
    c7.markdown(metric_card("WOs ruins (Diário)", str(int(snapshot["bad_wos_daily"] or 0)), "Com defeito"), unsafe_allow_html=True)
    c8.markdown(metric_card("Total WOs (Diário)", str(int(snapshot["total_wos_daily"] or 0)), "Base do cálculo diário"), unsafe_allow_html=True)

    st.markdown("<div class='section-title'>Última atualização</div>", unsafe_allow_html=True)
    st.markdown(
        f"<span class='chip'><strong>Arquivo:</strong> {latest_upload['file_name']}</span>"
        f"<span class='chip'><strong>Atualizado em:</strong> {snapshot['created_at']}</span>"
        f"<span class='chip'><strong>Referência:</strong> {format_date_br(reference_date)}</span>"
        f"<span class='chip'><strong>Diário efetivo:</strong> {format_date_br(daily_effective_date)}</span>"
        f"<span class='chip'><strong>S-1:</strong> {format_date_br(weekly_start)} a {format_date_br(weekly_end)}</span>"
        f"<span class='chip'><strong>Mensal:</strong> {format_date_br(monthly_start)} a {format_date_br(monthly_end)}</span>"
        f"<span class='chip'><strong>Regra diária:</strong> {snapshot['note_daily']}</span>",
        unsafe_allow_html=True,
    )

    export_bytes = create_snapshot_export(snapshot, latest_upload, previous_snapshot)
    st.download_button(
        "⬇️ Baixar snapshot executivo em Excel",
        data=export_bytes,
        file_name=f"snapshot_rft_{reference_date.isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


def render_import_section(conn: sqlite3.Connection):
    st.markdown("<div class='section-title'>Atualizar a base do site</div>", unsafe_allow_html=True)
    st.caption("Envie uma nova planilha para atualizar automaticamente o banco e recalcular os indicadores principais.")

    uploaded_file = st.file_uploader("Enviar planilha (.xlsx, .xls ou .csv)", type=["xlsx", "xls", "csv"])
    b1, b2 = st.columns([1.7, 1])
    process = b1.button("🔄 Processar nova planilha e atualizar o painel", type="primary", use_container_width=True)
    recalc = b2.button("♻️ Recalcular último upload", use_container_width=True)

    if process:
        if uploaded_file is None:
            st.error("Selecione uma planilha antes de processar.")
            st.stop()
        try:
            raw_df = load_uploaded_file(uploaded_file)
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")
            st.stop()
        ok, msg = validate_dataframe(raw_df)
        if not ok:
            st.error(msg)
            st.stop()
        prepared_df = prepare_dataframe(raw_df)
        upload_id = create_upload_log(conn, uploaded_file.name, len(prepared_df), "RECEBIDO", "Arquivo recebido com sucesso.")
        try:
            save_raw_data(conn, upload_id, prepared_df)
            build_snapshot(conn, upload_id, prepared_df, date.today())
            update_upload_status(conn, upload_id, "PROCESSADO", "Cálculo automático executado com sucesso.")
            st.success("Planilha processada com sucesso. O painel principal já foi atualizado.")
            st.rerun()
        except Exception as e:
            update_upload_status(conn, upload_id, "ERRO", str(e))
            st.error(f"Erro ao processar a planilha: {e}")

    if recalc:
        snapshot = recalculate_latest(conn)
        if snapshot is None:
            st.warning("Não existe upload processado para recalcular.")
        else:
            st.success("Indicadores recalculados com base no último upload processado.")
            st.rerun()


def render_analysis_section(conn: sqlite3.Connection, latest_upload: Optional[sqlite3.Row]):
    st.markdown("<div class='section-title'>Análises e filtros da última carga</div>", unsafe_allow_html=True)
    if latest_upload is None:
        st.info("Ainda não existe base carregada para explorar.")
        return

    df = get_dataset_by_upload(conn, latest_upload["id"])
    if df.empty:
        st.info("A última carga não possui linhas válidas após tratamento.")
        return

    f1, f2, f3, f4 = st.columns(4)
    modelos = sorted([m for m in df["CD_MODELO"].dropna().astype(str).unique().tolist() if m not in ["None", "nan", ""]])
    postos = sorted([p for p in df["CD_POSTO_CN"].dropna().astype(str).unique().tolist() if p not in ["None", "nan", ""]])
    anomalias = sorted([a for a in df["ANOMALIA_FALHA"].dropna().astype(str).unique().tolist() if a not in ["None", "nan", ""]])

    with f1:
        modelo_sel = st.multiselect("Modelo", modelos)
    with f2:
        posto_sel = st.multiselect("Posto", postos)
    with f3:
        anomalia_sel = st.multiselect("Anomalia", anomalias)
    with f4:
        wo_status = st.selectbox("WOs", ["Todas", "Somente zeradas", "Somente com defeito"])

    view_df = df.copy()
    if modelo_sel:
        view_df = view_df[view_df["CD_MODELO"].astype(str).isin(modelo_sel)]
    if posto_sel:
        view_df = view_df[view_df["CD_POSTO_CN"].astype(str).isin(posto_sel)]
    if anomalia_sel:
        view_df = view_df[view_df["ANOMALIA_FALHA"].astype(str).isin(anomalia_sel)]

    grouped = (
        view_df.groupby("NR_WO", as_index=False)["C_DPU_QG_AMARELO"]
        .sum()
        .rename(columns={"C_DPU_QG_AMARELO": "SOMA_C_DPU_QG_AMARELO"})
    )
    grouped["RFT"] = (grouped["SOMA_C_DPU_QG_AMARELO"] == 0).astype(int)

    if wo_status == "Somente zeradas":
        grouped = grouped[grouped["RFT"] == 1]
    elif wo_status == "Somente com defeito":
        grouped = grouped[grouped["RFT"] == 0]

    k1, k2, k3 = st.columns(3)
    total_wos = len(grouped)
    rft_local = round((grouped["RFT"].sum() / total_wos) * 100, 2) if total_wos else None
    k1.markdown(metric_card("RFT do recorte", format_pct_br(rft_local), "Calculado com os filtros aplicados"), unsafe_allow_html=True)
    k2.markdown(metric_card("WOs no recorte", str(total_wos), "Após filtros"), unsafe_allow_html=True)
    k3.markdown(metric_card("WOs com defeito", str(int((grouped['RFT'] == 0).sum()) if total_wos else 0), "Após filtros"), unsafe_allow_html=True)

    tabs = st.tabs(["Tabela por WO", "Top anomalias", "Top modelos"])
    with tabs[0]:
        st.dataframe(grouped.sort_values(["RFT", "NR_WO"], ascending=[False, True]), use_container_width=True, hide_index=True)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            grouped.to_excel(writer, index=False, sheet_name="WOs_Filtradas")
        st.download_button(
            "⬇️ Baixar WOs filtradas em Excel",
            data=buffer.getvalue(),
            file_name="WOs_filtradas_v3_3.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with tabs[1]:
        anom = (
            view_df[view_df["ANOMALIA_FALHA"].notna()]
            .groupby("ANOMALIA_FALHA")
            .size()
            .reset_index(name="Quantidade")
            .sort_values("Quantidade", ascending=False)
            .head(10)
        )
        if anom.empty:
            st.info("Sem anomalias disponíveis para o recorte atual.")
        else:
            st.dataframe(anom, use_container_width=True, hide_index=True)
            st.bar_chart(anom.set_index("ANOMALIA_FALHA"))

    with tabs[2]:
        mod = (
            view_df[view_df["CD_MODELO"].notna()]
            .groupby("CD_MODELO")
            .size()
            .reset_index(name="Quantidade")
            .sort_values("Quantidade", ascending=False)
            .head(10)
        )
        if mod.empty:
            st.info("Sem modelos disponíveis para o recorte atual.")
        else:
            st.dataframe(mod, use_container_width=True, hide_index=True)
            st.bar_chart(mod.set_index("CD_MODELO"))


def render_history_section(conn: sqlite3.Connection):
    st.markdown("<div class='section-title'>Histórico, uploads e tendência</div>", unsafe_allow_html=True)
    hist = get_snapshot_history(conn)
    uploads = get_upload_history(conn)

    tabs = st.tabs(["Histórico de cálculos", "Histórico de uploads", "Tendência"])
    with tabs[0]:
        if hist.empty:
            st.info("Ainda não existe histórico salvo.")
        else:
            arquivo_filtro = st.text_input("Filtrar histórico por arquivo")
            max_rows = st.selectbox("Quantidade de linhas do histórico", [25, 50, 100, 200, 300], index=1)
            view = hist.copy()
            if arquivo_filtro:
                view = view[view["arquivo"].astype(str).str.contains(arquivo_filtro, case=False, na=False)]
            show = view.head(max_rows).copy()
            for c in ["rft_diario", "rft_semanal", "rft_mensal", "rft_ytd", "rft_2025"]:
                show[c] = show[c].apply(format_pct_br)
            st.dataframe(show, use_container_width=True, hide_index=True)

    with tabs[1]:
        if uploads.empty:
            st.info("Ainda não existe upload salvo.")
        else:
            statuses = sorted(uploads["status"].dropna().unique().tolist())
            status_filtro = st.multiselect("Filtrar status dos uploads", statuses, default=statuses)
            file_filtro = st.text_input("Filtrar uploads por arquivo")
            max_rows_u = st.selectbox("Quantidade de linhas dos uploads", [25, 50, 100, 200, 300], index=1)
            upload_view = uploads.copy()
            if status_filtro:
                upload_view = upload_view[upload_view["status"].isin(status_filtro)]
            if file_filtro:
                upload_view = upload_view[upload_view["file_name"].astype(str).str.contains(file_filtro, case=False, na=False)]
            st.dataframe(upload_view.head(max_rows_u), use_container_width=True, hide_index=True)

    with tabs[2]:
        if hist.empty:
            st.info("Ainda não há dados suficientes para tendência.")
        else:
            trend = hist.copy()
            trend["calculado_em"] = pd.to_datetime(trend["calculado_em"], errors="coerce")
            trend = trend.sort_values("calculado_em")
            trend_line = trend[["calculado_em", "rft_diario", "rft_semanal", "rft_mensal", "rft_ytd"]].dropna(how="all")
            if trend_line.empty:
                st.info("Ainda não há série temporal suficiente para exibir tendência.")
            else:
                st.line_chart(trend_line.set_index("calculado_em"))
                st.caption("Tendência histórica dos principais KPIs salvos.")


def render_help_section():
    with st.expander("O que mudou na V3.3", expanded=False):
        st.markdown(
            """
            **Novidades da V3.3:**
            - meta configurável no site
            - alertas visuais quando o RFT fica abaixo da meta
            - comparação entre a carga atual e a anterior (diário, semanal e mensal)
            - exportação do snapshot executivo em Excel
            - manutenção dos recursos da V3.2 (análises, filtros, exportação e tendência)
            """
        )


def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    conn = get_conn()
    init_db(conn)

    render_hero()
    sidebar_controls(conn)

    latest_upload = get_latest_upload(conn)
    latest_snapshot = get_latest_snapshot(conn)
    previous_snapshot = get_previous_snapshot(conn)
    target = float(st.session_state.get("target_rft", 95.0))

    if latest_upload and latest_snapshot:
        render_home(latest_snapshot, latest_upload, previous_snapshot, target)
    else:
        st.info("Ainda não existe cálculo salvo. Faça o primeiro upload para inicializar o sistema.")

    st.divider()
    render_import_section(conn)
    st.divider()
    render_analysis_section(conn, latest_upload)
    st.divider()
    render_history_section(conn)
    st.divider()
    render_help_section()


if __name__ == "__main__":
    main()
