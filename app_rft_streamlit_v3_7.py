
import io
import sqlite3
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from typing import Optional

import pandas as pd
import streamlit as st

st.set_page_config(page_title="RFT Automático — V3.7", page_icon="📈", layout="wide")

DB = "rft_v37.db"
REQ = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO"]

st.markdown(
    """
    <style>
    .block-container{max-width:1450px;padding-top:1rem;padding-bottom:2rem}
    .hero{background:linear-gradient(135deg,#0f2747 0%,#1f6fb2 100%);color:#fff;padding:1.2rem 1.4rem;border-radius:18px;margin-bottom:1rem}
    .card{background:#fff;border:1px solid #e6eef7;border-left:6px solid #1f6fb2;border-radius:16px;padding:1rem;min-height:120px;box-shadow:0 6px 18px rgba(10,35,66,.06)}
    .card-ok{border-left-color:#2c8f4e}.card-bad{border-left-color:#c2410c}.card-neutral{border-left-color:#1f6fb2}
    .card-title{color:#5d6b78;font-size:.9rem;font-weight:600}.card-value{color:#12355b;font-size:1.95rem;font-weight:800}.card-sub{color:#6f7f8d;font-size:.82rem}
    .alert-ok,.alert-bad,.alert-info{border-radius:14px;padding:.9rem 1rem;font-weight:600;margin:.35rem 0}
    .alert-ok{background:#edf8f1;color:#166534;border:1px solid #b7dfc2}.alert-bad{background:#fff1f2;color:#9f1239;border:1px solid #fecdd3}.alert-info{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
    .chip{display:inline-block;background:#eef5fb;color:#12355b;border:1px solid #d7e7f5;border-radius:999px;padding:.35rem .8rem;margin:0 .35rem .35rem 0;font-size:.9rem}
    div.stButton > button[kind="primary"]{border-radius:12px;height:3rem;font-weight:700;border:none}
    div.stButton > button{border-radius:12px;height:2.85rem;font-weight:600}
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# DB
# =========================
def get_conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB, check_same_thread=False)
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init_db(c: sqlite3.Connection) -> None:
    stmts = [
        "CREATE TABLE IF NOT EXISTS upload_log (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL, uploaded_at TEXT NOT NULL, total_rows INTEGER NOT NULL, status TEXT NOT NULL, message TEXT, dataset_role TEXT NOT NULL, year_tag INTEGER)",
        "CREATE TABLE IF NOT EXISTS raw_inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, nr_wo TEXT, dt_hr_inspecao TEXT, c_dpu_qg_amarelo REAL, cd_modelo TEXT, cd_posto_cn TEXT, anomalia_falha TEXT, FOREIGN KEY (upload_id) REFERENCES upload_log(id) ON DELETE CASCADE)",
        "CREATE TABLE IF NOT EXISTS work_calendar (work_date TEXT PRIMARY KEY, is_working INTEGER NOT NULL, note TEXT, updated_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS metric_daily (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, reference_date TEXT NOT NULL, effective_date TEXT NOT NULL, rule_note TEXT NOT NULL, rft_pct REAL, total_wos INTEGER, good_wos INTEGER, bad_wos INTEGER)",
        "CREATE TABLE IF NOT EXISTS metric_weekly (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, week_start TEXT NOT NULL, week_end TEXT NOT NULL, rft_pct REAL, total_wos INTEGER, good_wos INTEGER, bad_wos INTEGER)",
        "CREATE TABLE IF NOT EXISTS metric_monthly (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, month_key TEXT NOT NULL, month_start TEXT NOT NULL, month_end TEXT NOT NULL, rft_pct REAL, total_wos INTEGER, good_wos INTEGER, bad_wos INTEGER)",
        "CREATE TABLE IF NOT EXISTS metric_yearly (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, metric_year INTEGER NOT NULL, rft_pct REAL, total_wos INTEGER, good_wos INTEGER, bad_wos INTEGER)",
        "CREATE TABLE IF NOT EXISTS metric_ytd (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, reference_date TEXT NOT NULL, metric_year INTEGER NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL, rft_pct REAL, total_wos INTEGER, good_wos INTEGER, bad_wos INTEGER)"
    ]
    for s in stmts:
        c.execute(s)
    c.commit()

# =========================
# File read / prep
# =========================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(x).strip().replace("﻿", "") for x in df.columns]
    return df


def read_file(uploaded_file) -> pd.DataFrame:
    ext = uploaded_file.name.lower().split('.')[-1]
    b = uploaded_file.getvalue()
    if ext == 'csv':
        last_err = None
        for enc in ['utf-8-sig', 'utf-16', 'latin1']:
            for sep in [None, ';', ',', '	']:
                try:
                    if sep is None:
                        df = pd.read_csv(io.BytesIO(b), encoding=enc, sep=None, engine='python')
                    else:
                        df = pd.read_csv(io.BytesIO(b), encoding=enc, sep=sep)
                    return normalize_columns(df)
                except Exception as e:
                    last_err = e
        raise ValueError(f'Não foi possível ler o CSV. Detalhe: {last_err}')
    if ext in ['xlsx', 'xls']:
        engine = 'openpyxl' if ext == 'xlsx' else 'xlrd'
        return normalize_columns(pd.read_excel(io.BytesIO(b), engine=engine))
    raise ValueError('Formato não suportado. Use .xlsx, .xls ou .csv')


def validate_df(df: pd.DataFrame):
    missing = [c for c in REQ if c not in df.columns]
    return len(missing) == 0, missing


def parse_dt(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors='coerce')
    mask = dt.isna() & s.notna()
    if mask.any():
        dt.loc[mask] = pd.to_datetime(s[mask], errors='coerce', dayfirst=True)
    return dt


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    w = df.copy()
    w['DT_HR_INSPECAO'] = parse_dt(w['DT_HR_INSPECAO'])
    w['C_DPU_QG_AMARELO'] = pd.to_numeric(w['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    w['NR_WO'] = w['NR_WO'].astype(str).str.strip()
    for col in ['CD_MODELO', 'CD_POSTO_CN', 'ANOMALIA_FALHA']:
        if col not in w.columns:
            w[col] = None
    return w[w['DT_HR_INSPECAO'].notna()].copy()

# =========================
# Calendar
# =========================
def get_override(c: sqlite3.Connection, d: date) -> Optional[bool]:
    row = c.execute('SELECT is_working FROM work_calendar WHERE work_date=?', (d.isoformat(),)).fetchone()
    return None if row is None else bool(row[0])


def is_working_day(c: sqlite3.Connection, d: date) -> bool:
    ov = get_override(c, d)
    if ov is not None:
        return ov
    return d.weekday() not in (5, 6)


def save_calendar(c: sqlite3.Connection, d: date, is_working: bool, note: str = '') -> None:
    c.execute(
        "INSERT INTO work_calendar (work_date, is_working, note, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(work_date) DO UPDATE SET is_working=excluded.is_working, note=excluded.note, updated_at=excluded.updated_at",
        (d.isoformat(), 1 if is_working else 0, note, datetime.now().isoformat(timespec='seconds')),
    )
    c.commit()


def prev_working_day(c: sqlite3.Connection, ref: date) -> date:
    d = ref - timedelta(days=1)
    for _ in range(31):
        if is_working_day(c, d):
            return d
        d -= timedelta(days=1)
    return d


def resolve_daily_effective(c: sqlite3.Connection, ref: date):
    if ref.weekday() == 0:
        saturday = ref - timedelta(days=2)
        if is_working_day(c, saturday):
            return saturday, 'Segunda usando D-2 (sábado marcado como trabalhado).'
        p = prev_working_day(c, ref)
        return p, 'Segunda usando o último dia útil anterior, pois sábado não está marcado como trabalhado.'
    p = prev_working_day(c, ref)
    return p, 'Terça a sábado usando D-1 (último dia útil anterior).'

# =========================
# Metrics
# =========================
def calc_rft(df: pd.DataFrame, start_date: date, end_date: date):
    sdt = datetime.combine(start_date, time(0, 0, 0))
    edt = datetime.combine(end_date, time(23, 59, 59))
    f = df[(df['DT_HR_INSPECAO'] >= sdt) & (df['DT_HR_INSPECAO'] <= edt)].copy()
    if f.empty:
        return {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0}
    grp = f.groupby('NR_WO', as_index=False)['C_DPU_QG_AMARELO'].sum().rename(columns={'C_DPU_QG_AMARELO': 'SOMA'})
    grp['RFT'] = (grp['SOMA'] == 0).astype(int)
    total = int(len(grp))
    good = int(grp['RFT'].sum())
    bad = int(total - good)
    pct = round((good / total) * 100, 2) if total else None
    return {'rft_pct': pct, 'total': total, 'good': good, 'bad': bad}


def clear_metrics(c: sqlite3.Connection, upload_id: int):
    for t in ['metric_daily', 'metric_weekly', 'metric_monthly', 'metric_yearly', 'metric_ytd']:
        c.execute(f'DELETE FROM {t} WHERE upload_id=?', (upload_id,))
    c.commit()


def generate_metrics(c: sqlite3.Connection, upload_id: int, df: pd.DataFrame):
    clear_metrics(c, upload_id)
    if df.empty:
        return
    unique_dates = sorted(df['DT_HR_INSPECAO'].dt.date.dropna().unique().tolist())
    min_date, max_date = min(unique_dates), max(unique_dates)

    daily_rows, ytd_rows = [], []
    for ts in pd.date_range(min_date, max_date + timedelta(days=1), freq='D'):
        ref = ts.date()
        eff, note = resolve_daily_effective(c, ref)
        day = calc_rft(df, eff, eff)
        daily_rows.append((upload_id, ref.isoformat(), eff.isoformat(), note, day['rft_pct'], day['total'], day['good'], day['bad']))
        y = calc_rft(df, date(eff.year, 1, 1), eff)
        ytd_rows.append((upload_id, ref.isoformat(), eff.year, date(eff.year, 1, 1).isoformat(), eff.isoformat(), y['rft_pct'], y['total'], y['good'], y['bad']))
    c.executemany('INSERT INTO metric_daily (upload_id, reference_date, effective_date, rule_note, rft_pct, total_wos, good_wos, bad_wos) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', daily_rows)
    c.executemany('INSERT INTO metric_ytd (upload_id, reference_date, metric_year, period_start, period_end, rft_pct, total_wos, good_wos, bad_wos) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', ytd_rows)

    weekly_rows = []
    for monday in sorted({d - timedelta(days=d.weekday()) for d in unique_dates}):
        saturday = monday + timedelta(days=5)
        w = calc_rft(df, monday, saturday)
        weekly_rows.append((upload_id, monday.isoformat(), saturday.isoformat(), w['rft_pct'], w['total'], w['good'], w['bad']))
    c.executemany('INSERT INTO metric_weekly (upload_id, week_start, week_end, rft_pct, total_wos, good_wos, bad_wos) VALUES (?, ?, ?, ?, ?, ?, ?)', weekly_rows)

    monthly_rows = []
    for y, m in sorted({(d.year, d.month) for d in unique_dates}):
        start = date(y, m, 1)
        end = date(y, m, monthrange(y, m)[1])
        r = calc_rft(df, start, end)
        monthly_rows.append((upload_id, f'{y}-{m:02d}', start.isoformat(), end.isoformat(), r['rft_pct'], r['total'], r['good'], r['bad']))
    c.executemany('INSERT INTO metric_monthly (upload_id, month_key, month_start, month_end, rft_pct, total_wos, good_wos, bad_wos) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', monthly_rows)

    yearly_rows = []
    for y in sorted({d.year for d in unique_dates}):
        r = calc_rft(df, date(y, 1, 1), date(y, 12, 31))
        yearly_rows.append((upload_id, y, r['rft_pct'], r['total'], r['good'], r['bad']))
    c.executemany('INSERT INTO metric_yearly (upload_id, metric_year, rft_pct, total_wos, good_wos, bad_wos) VALUES (?, ?, ?, ?, ?, ?)', yearly_rows)
    c.commit()

# =========================
# Upload/query helpers
# =========================
def create_upload(c, file_name, total_rows, role='current', year_tag=None, status='RECEBIDO', message=''):
    cur = c.execute('INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message, dataset_role, year_tag) VALUES (?, ?, ?, ?, ?, ?, ?)', (file_name, datetime.now().isoformat(timespec='seconds'), int(total_rows), status, message, role, year_tag))
    c.commit()
    return int(cur.lastrowid)


def update_upload(c, upload_id, status, message=''):
    c.execute('UPDATE upload_log SET status=?, message=? WHERE id=?', (status, message, upload_id))
    c.commit()


def save_raw(c, upload_id, df: pd.DataFrame):
    rows = []
    for _, r in df.iterrows():
        rows.append((upload_id, r.get('NR_WO'), r.get('DT_HR_INSPECAO').isoformat(sep=' ', timespec='seconds') if pd.notna(r.get('DT_HR_INSPECAO')) else None, float(r.get('C_DPU_QG_AMARELO', 0)) if pd.notna(r.get('C_DPU_QG_AMARELO')) else 0.0, r.get('CD_MODELO'), r.get('CD_POSTO_CN'), r.get('ANOMALIA_FALHA')))
    c.executemany('INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_modelo, cd_posto_cn, anomalia_falha) VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
    c.commit()


def latest_upload(c, role='current'):
    c.row_factory = sqlite3.Row
    return c.execute('SELECT * FROM upload_log WHERE status=? AND dataset_role=? ORDER BY id DESC LIMIT 1', ('PROCESSADO', role)).fetchone()


def hist_upload_for_year(c, year_tag):
    c.row_factory = sqlite3.Row
    return c.execute('SELECT * FROM upload_log WHERE status=? AND dataset_role=? AND year_tag=? ORDER BY id DESC LIMIT 1', ('PROCESSADO', 'historical', year_tag)).fetchone()


def load_upload_df(c, upload_id):
    sql = 'SELECT nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_modelo AS CD_MODELO, cd_posto_cn AS CD_POSTO_CN, anomalia_falha AS ANOMALIA_FALHA FROM raw_inspections WHERE upload_id=?'
    df = pd.read_sql_query(sql, c, params=[upload_id])
    if not df.empty:
        df['DT_HR_INSPECAO'] = pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
        df['C_DPU_QG_AMARELO'] = pd.to_numeric(df['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    return df


def fetch_metric(c, table, upload_id, **filters):
    c.row_factory = sqlite3.Row
    sql = f'SELECT * FROM {table} WHERE upload_id=?'
    params = [upload_id]
    for k, v in filters.items():
        sql += f' AND {k}=?'
        params.append(v)
    sql += ' LIMIT 1'
    return c.execute(sql, params).fetchone()


def metric_table(c, table, upload_id):
    return pd.read_sql_query(f'SELECT * FROM {table} WHERE upload_id=? ORDER BY 1', c, params=[upload_id])


def uploads_table(c):
    return pd.read_sql_query('SELECT id, file_name, uploaded_at, total_rows, status, message, dataset_role, year_tag FROM upload_log ORDER BY id DESC LIMIT 300', c)

# =========================
# UI helpers
# =========================
def format_pct(v):
    return 'Sem dados' if v is None or pd.isna(v) else f"{v:.2f}".replace('.', ',') + '%'


def format_date(d):
    return '-' if d is None else d.strftime('%d/%m/%Y')


def card(title, value, subtitle='', status='card-neutral'):
    return f"<div class='card {status}'><div class='card-title'>{title}</div><div class='card-value'>{value}</div><div class='card-sub'>{subtitle}</div></div>"


def status_class(v, target):
    if v is None or pd.isna(v):
        return 'card-neutral'
    return 'card-ok' if v <= target else 'card-bad'


def alert_box(title, message, level='info'):
    css = {'ok': 'alert-ok', 'bad': 'alert-bad', 'info': 'alert-info'}[level]
    st.markdown(f"<div class='{css}'><strong>{title}</strong><br>{message}</div>", unsafe_allow_html=True)


def summary_export(c, current, comparison_year):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        pd.DataFrame([
            ['Arquivo operacional', current['file_name']],
            ['Último upload', current['uploaded_at']],
            ['Ano de comparação', comparison_year]
        ], columns=['Campo', 'Valor']).to_excel(writer, index=False, sheet_name='Resumo')
        for name, table in [('Daily', 'metric_daily'), ('Weekly', 'metric_weekly'), ('Monthly', 'metric_monthly'), ('Yearly', 'metric_yearly'), ('YTD', 'metric_ytd')]:
            metric_table(c, table, current['id']).to_excel(writer, index=False, sheet_name=name)
    return out.getvalue()

# =========================
# Sections
# =========================
def sidebar_controls(c):
    st.sidebar.header('Configurações')
    st.session_state['target_rft'] = st.sidebar.number_input('Meta de RFT (%)', min_value=0.0, max_value=100.0, value=float(st.session_state.get('target_rft', 95.0)), step=0.5)
    st.session_state['comparison_year'] = int(st.sidebar.number_input('Ano de comparação', min_value=2015, max_value=2100, value=int(st.session_state.get('comparison_year', 2025)), step=1))
    st.sidebar.header('Calendário de trabalho')
    st.sidebar.caption('Domingo = não trabalhado. Sábado = não trabalhado por padrão e pode ser habilitado manualmente.')
    chosen = st.sidebar.date_input('Marcar dia no calendário', value=date.today(), format='DD/MM/YYYY')
    worked = st.sidebar.checkbox('Dia trabalhado', value=is_working_day(c, chosen))
    note = st.sidebar.text_input('Observação do dia')
    if st.sidebar.button('Salvar calendário', use_container_width=True):
        save_calendar(c, chosen, worked, note)
        st.sidebar.success(f'Calendário atualizado para {format_date(chosen)}.')
    cur = latest_upload(c, 'current')
    if cur and st.sidebar.button('Reprocessar métricas da base atual com o calendário', use_container_width=True):
        generate_metrics(c, cur['id'], load_upload_df(c, cur['id']))
        st.sidebar.success('Métricas da base atual reprocessadas com o calendário atualizado.')


def render_dashboard(c):
    cur = latest_upload(c, 'current')
    if cur is None:
        st.info('Ainda não existe base operacional processada. Faça o primeiro upload para inicializar o sistema.')
        return
    target = float(st.session_state.get('target_rft', 95.0))
    comp_year = int(st.session_state.get('comparison_year', 2025))
    df = load_upload_df(c, cur['id'])
    max_date = df['DT_HR_INSPECAO'].dt.date.max()
    ref = st.date_input('Data de referência do painel', value=max_date + timedelta(days=1) if pd.notna(max_date) else date.today(), format='DD/MM/YYYY')
    eff, note = resolve_daily_effective(c, ref)
    week_start = ref - timedelta(days=ref.weekday()) - timedelta(days=7)
    week_end = week_start + timedelta(days=5)
    month_key = f'{ref.year}-{ref.month:02d}'

    daily = fetch_metric(c, 'metric_daily', cur['id'], reference_date=ref.isoformat())
    weekly = fetch_metric(c, 'metric_weekly', cur['id'], week_start=week_start.isoformat())
    monthly = fetch_metric(c, 'metric_monthly', cur['id'], month_key=month_key)
    ytd = fetch_metric(c, 'metric_ytd', cur['id'], reference_date=ref.isoformat())

    h = hist_upload_for_year(c, comp_year)
    year_metric = fetch_metric(c, 'metric_yearly', h['id'], metric_year=comp_year) if h else fetch_metric(c, 'metric_yearly', cur['id'], metric_year=comp_year)
    year_note = f'Usando base histórica dedicada de {comp_year}.' if h else (f'Usando a base operacional para {comp_year}.' if year_metric else f'Sem dados de {comp_year}; envie uma base histórica opcional.')

    daily_v = daily['rft_pct'] if daily else None
    weekly_v = weekly['rft_pct'] if weekly else None
    monthly_v = monthly['rft_pct'] if monthly else None

    if daily_v is None:
        alert_box('Status diário', 'Sem dados para a data de referência selecionada.', 'info')
    elif daily_v <= target:
        alert_box('Status diário', f'RFT diário dentro da meta. Meta = {format_pct(target)} | Atual = {format_pct(daily_v)}.', 'ok')
    else:
        alert_box('Alerta diário', f'RFT diário acima da meta. Meta = {format_pct(target)} | Atual = {format_pct(daily_v)}.', 'bad')
    if weekly_v is not None and weekly_v > target:
        alert_box('Alerta semanal S-1', f'RFT semanal acima da meta. Atual = {format_pct(weekly_v)}.', 'bad')
    if monthly_v is not None and monthly_v > target:
        alert_box('Alerta mensal', f'RFT mensal acima da meta. Atual = {format_pct(monthly_v)}.', 'bad')

    st.markdown("<div class='section-title'>Painel executivo</div>", unsafe_allow_html=True)
    cols = st.columns(4)
    cols[0].markdown(card('RFT Diário', format_pct(daily_v), f'Data efetiva: {format_date(eff)}', status_class(daily_v, target)), unsafe_allow_html=True)
    cols[1].markdown(card('RFT Semanal S-1', format_pct(weekly_v), f'{format_date(week_start)} a {format_date(week_end)}', status_class(weekly_v, target)), unsafe_allow_html=True)
    cols[2].markdown(card('RFT Mensal', format_pct(monthly_v), month_key, status_class(monthly_v, target)), unsafe_allow_html=True)
    cols[3].markdown(card('RFT YTD', format_pct(ytd['rft_pct'] if ytd else None), f'Ano {ref.year}', status_class(ytd['rft_pct'] if ytd else None, target)), unsafe_allow_html=True)
    cols2 = st.columns(4)
    cols2[0].markdown(card(f'RFT {comp_year}', format_pct(year_metric['rft_pct'] if year_metric else None), year_note), unsafe_allow_html=True)
    cols2[1].markdown(card('WOs boas (Diário)', str(int(daily['good_wos']) if daily else 0), 'Sem defeito'), unsafe_allow_html=True)
    cols2[2].markdown(card('WOs ruins (Diário)', str(int(daily['bad_wos']) if daily else 0), 'Com defeito'), unsafe_allow_html=True)
    cols2[3].markdown(card('Total WOs (Diário)', str(int(daily['total_wos']) if daily else 0), 'Base do cálculo diário'), unsafe_allow_html=True)

    st.markdown("<div class='section-title'>Contexto da consulta</div>", unsafe_allow_html=True)
    st.markdown(
        f"<span class='chip'><strong>Arquivo operacional:</strong> {cur['file_name']}</span>"
        f"<span class='chip'><strong>Último upload:</strong> {cur['uploaded_at']}</span>"
        f"<span class='chip'><strong>Data de referência:</strong> {format_date(ref)}</span>"
        f"<span class='chip'><strong>Regra diária:</strong> {note}</span>"
        f"<span class='chip'><strong>Ano de comparação:</strong> {comp_year}</span>"
        f"<span class='chip'><strong>Meta:</strong> {format_pct(target)}</span>",
        unsafe_allow_html=True,
    )

    st.download_button('⬇️ Baixar métricas calculadas em Excel', data=summary_export(c, cur, comp_year), file_name=f'metricas_rft_{ref.isoformat()}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)


def render_imports(c):
    st.markdown("<div class='section-title'>Atualizar as bases</div>", unsafe_allow_html=True)
    st.caption('Envie a base operacional atual e, opcionalmente, uma base histórica dedicada ao ano de comparação.')
    cy = int(st.session_state.get('comparison_year', 2025))
    current_file = st.file_uploader('Base operacional atual (.xlsx, .xls ou .csv)', type=['xlsx', 'xls', 'csv'], key='current_import_v36')
    hist_file = st.file_uploader(f'Base histórica opcional para {cy} (.xlsx, .xls ou .csv)', type=['xlsx', 'xls', 'csv'], key='hist_import_v36')
    c1, c2 = st.columns([1.7, 1])
    if c1.button('🔄 Processar bases e recalcular todos os períodos', type='primary', use_container_width=True):
        if current_file is None:
            st.error('Selecione a base operacional atual antes de processar.')
            st.stop()
        try:
            cur_raw = read_file(current_file)
            ok, miss = validate_df(cur_raw)
            if not ok:
                st.error('Base operacional inválida: ' + ', '.join(miss))
                st.stop()
            cur_df = prepare(cur_raw)
        except Exception as e:
            st.error(f'Erro ao ler a base operacional: {e}')
            st.stop()

        cur_id = create_upload(c, current_file.name, len(cur_df), role='current', message='Base operacional recebida.')
        h_id, h_df = None, None
        if hist_file is not None:
            try:
                h_raw = read_file(hist_file)
                ok2, miss2 = validate_df(h_raw)
                if not ok2:
                    st.error('Base histórica inválida: ' + ', '.join(miss2))
                    st.stop()
                h_df = prepare(h_raw)
            except Exception as e:
                st.error(f'Erro ao ler a base histórica: {e}')
                st.stop()
            h_id = create_upload(c, hist_file.name, len(h_df), role='historical', year_tag=cy, message=f'Base histórica {cy} recebida.')

        try:
            save_raw(c, cur_id, cur_df)
            generate_metrics(c, cur_id, cur_df)
            update_upload(c, cur_id, 'PROCESSADO', 'Base operacional processada com sucesso.')
            if h_df is not None and h_id is not None:
                save_raw(c, h_id, h_df)
                generate_metrics(c, h_id, h_df)
                update_upload(c, h_id, 'PROCESSADO', f'Base histórica {cy} processada com sucesso.')
            st.success('Bases processadas com sucesso. Foram gerados automaticamente todos os períodos: diário, semanal, mensal, anual e YTD.')
            st.rerun()
        except Exception as e:
            update_upload(c, cur_id, 'ERRO', str(e))
            if h_id is not None:
                update_upload(c, h_id, 'ERRO', str(e))
            st.error(f'Erro ao processar as bases: {e}')

    if c2.button('♻️ Reprocessar base atual com o calendário', use_container_width=True):
        cur = latest_upload(c, 'current')
        if cur is None:
            st.warning('Não existe base atual processada para reprocessar.')
        else:
            generate_metrics(c, cur['id'], load_upload_df(c, cur['id']))
            st.success('Métricas da base atual reprocessadas com o calendário atualizado.')
            st.rerun()


def render_metric_tabs(c):
    st.markdown("<div class='section-title'>Tabelas automáticas por período</div>", unsafe_allow_html=True)
    cur = latest_upload(c, 'current')
    if cur is None:
        st.info('Ainda não existe base operacional processada.')
        return
    tabs = st.tabs(['Diário', 'Semanal', 'Mensal', 'Anual', 'YTD'])
    mapping = {
        'Diário': ('metric_daily', ['reference_date', 'effective_date', 'rule_note', 'rft_pct', 'total_wos', 'good_wos', 'bad_wos']),
        'Semanal': ('metric_weekly', ['week_start', 'week_end', 'rft_pct', 'total_wos', 'good_wos', 'bad_wos']),
        'Mensal': ('metric_monthly', ['month_key', 'month_start', 'month_end', 'rft_pct', 'total_wos', 'good_wos', 'bad_wos']),
        'Anual': ('metric_yearly', ['metric_year', 'rft_pct', 'total_wos', 'good_wos', 'bad_wos']),
        'YTD': ('metric_ytd', ['reference_date', 'metric_year', 'period_start', 'period_end', 'rft_pct', 'total_wos', 'good_wos', 'bad_wos'])
    }
    for t in tabs:
        with t:
            table, cols = mapping[t.name]
            df = pd.read_sql_query(f"SELECT {', '.join(cols)} FROM {table} WHERE upload_id=? ORDER BY 1", c, params=[cur['id']])
            if df.empty:
                st.info(f'Sem dados para {t.name.lower()}.')
            else:
                if 'rft_pct' in df.columns:
                    df['rft_pct'] = df['rft_pct'].apply(format_pct)
                st.dataframe(df, use_container_width=True, hide_index=True)


def render_upload_history(c):
    st.markdown("<div class='section-title'>Histórico de uploads</div>", unsafe_allow_html=True)
    up = uploads_table(c)
    if up.empty:
        st.info('Ainda não existe upload salvo.')
    else:
        st.dataframe(up, use_container_width=True, hide_index=True)


def render_help():
    with st.expander('O que mudou na V3.7', expanded=False):
        st.markdown(
            """
- Corrige o erro de sintaxe da versão anterior.
- Mantém a meta visual corrigida: **menor ou igual à meta = verde** e **acima da meta = vermelho**.
- Calendário funcional com botão para **reprocessar as métricas da base atual** usando as regras atualizadas.
- Ao importar a planilha, o sistema calcula automaticamente **todos os dias, semanas, meses, anos e YTD** da base atual.
- Mantida a **base histórica separada** e o **ano de comparação configurável**.
            """
        )


def main():
    c = get_conn()
    init_db(c)
    st.markdown("<div class='hero'><h1>RFT Automático — V3.7</h1><p>Versão estável com correção do erro de sintaxe, meta visual corrigida, calendário funcional e processamento completo por dia/semana/mês/ano/YTD.</p></div>", unsafe_allow_html=True)
    sidebar_controls(c)
    render_dashboard(c)
    st.divider()
    render_imports(c)
    st.divider()
    render_metric_tabs(c)
    st.divider()
    render_upload_history(c)
    st.divider()
    render_help()


if __name__ == '__main__':
    main()
