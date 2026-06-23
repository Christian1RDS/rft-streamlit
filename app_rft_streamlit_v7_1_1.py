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

st.set_page_config(page_title='RFT Qualidade - V7.1.1', page_icon='Q', layout='wide', initial_sidebar_state='expanded')

DB = 'rft_v61_local.db'
REQ = ['NR_WO', 'DT_HR_INSPECAO', 'C_DPU_QG_AMARELO', 'CD_POSTO_CN']
POSTOS = ['QG09', 'QG07']
POSTO_PADRAO = 'QG09'
LS_PREFIX = 'rft_v711_'
DEFAULT_META_RFT = 95.0
CUTOFF_MONTH = 12
CUTOFF_DAY = 12

CSS = """
<style>
:root {
  --bg:#0f172a; --border:rgba(148,163,184,.18); --text:#e5e7eb; --muted:#94a3b8;
  --green:#22c55e; --red:#ef4444; --amber:#f59e0b; --blue:#3b82f6;
}
html, body, [data-testid="stAppViewContainer"], .stApp { background: linear-gradient(180deg,#0b1220 0%,#0f172a 100%); color: var(--text); }
[data-testid="stHeader"] { background: rgba(15,23,42,.78); border-bottom: 1px solid var(--border); }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#0c1527 0%,#121d31 100%); border-right: 1px solid var(--border); }
[data-testid="stSidebar"] * { color: var(--text) !important; }
.block-container { padding-top: 1rem; padding-bottom: 2rem; }
h1,h2,h3,h4,h5,h6,p,label,div,span { color: var(--text); }
.hero { background: linear-gradient(135deg, rgba(24,34,53,.96), rgba(16,24,40,.98)); border:1px solid var(--border); border-radius:20px; padding:1rem 1.1rem; margin-bottom:1rem; }
.section { background: linear-gradient(180deg, rgba(28,37,55,.96), rgba(18,27,41,.98)); border:1px solid var(--border); border-radius:18px; padding:1rem; margin-bottom:1rem; }
.metric-card { border:1px solid var(--border); background: linear-gradient(180deg, rgba(31,42,61,.96), rgba(22,31,47,.98)); border-radius:18px; padding:1rem; min-height:150px; }
.muted { color: var(--muted); }
.ok { color: var(--green); } .bad { color: var(--red); } .neutral { color: var(--text); }
.kv { display:flex; justify-content:space-between; gap:1rem; padding:.55rem .7rem; background: rgba(255,255,255,.03); border:1px solid rgba(148,163,184,.09); border-radius:14px; margin-bottom:.45rem; }
.pill { display:inline-flex; align-items:center; gap:.35rem; padding:.42rem .72rem; border-radius:999px; border:1px solid var(--border); background: rgba(255,255,255,.04); margin-right:.35rem; margin-bottom:.35rem; }
.pill-blue { background: rgba(59,130,246,.12); border-color: rgba(59,130,246,.28); }
.pill-green { background: rgba(34,197,94,.12); border-color: rgba(34,197,94,.28); }
.pill-red { background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.28); }
.pill-amber { background: rgba(245,158,11,.12); border-color: rgba(245,158,11,.28); }
[data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:18px; overflow:hidden; }
</style>
"""

# -----------------------------
# Persistência local
# -----------------------------
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
        val = ls.getItem(LS_PREFIX + key, key=f'get_{key}')
        return default if val in (None, '', 'null', 'None') else val
    except Exception:
        return default


def ls_set(key, value):
    ls = get_local_storage()
    if ls is None:
        return
    try:
        ls.setItem(LS_PREFIX + key, str(value), key=f'set_{key}')
    except Exception:
        pass


def current_meta():
    return float(st.session_state.get('meta_rft', DEFAULT_META_RFT))

# -----------------------------
# Banco local
# -----------------------------
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)


def init_db(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS upload_log (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL, uploaded_at TEXT NOT NULL, total_rows INTEGER NOT NULL, status TEXT NOT NULL, message TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS raw_inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, nr_wo TEXT, dt_hr_inspecao TEXT, c_dpu_qg_amarelo REAL, cd_posto_cn TEXT)')
    conn.commit()


def create_upload(conn, file_name, total_rows, status='RECEBIDO', message=''):
    cur = conn.execute(
        'INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)',
        (file_name, datetime.now().isoformat(timespec='seconds'), int(total_rows), status, message),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_upload(conn, upload_id, status, message=''):
    conn.execute('UPDATE upload_log SET status=?, message=? WHERE id=?', (status, message, int(upload_id)))
    conn.commit()


def save_raw(conn, upload_id, df):
    rows = []
    for _, r in df.iterrows():
        rows.append((
            int(upload_id),
            r['NR_WO'],
            r['DT_HR_INSPECAO'].isoformat(sep=' ', timespec='seconds'),
            float(r['C_DPU_QG_AMARELO']),
            r['CD_POSTO_CN'],
        ))
    conn.executemany(
        'INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn) VALUES (?, ?, ?, ?, ?)',
        rows,
    )
    conn.commit()


def uploads_table(conn):
    return pd.read_sql_query('SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC LIMIT 500', conn)


def upload_info(conn, upload_id):
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM upload_log WHERE id=?', (int(upload_id),)).fetchone()
    conn.row_factory = None
    return row


def delete_upload(conn, upload_id):
    conn.execute('DELETE FROM raw_inspections WHERE upload_id=?', (int(upload_id),))
    conn.execute('DELETE FROM upload_log WHERE id=?', (int(upload_id),))
    conn.commit()


def detail_upload_df(conn, upload_id):
    df = pd.read_sql_query(
        'SELECT nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE upload_id=? ORDER BY dt_hr_inspecao, nr_wo',
        conn,
        params=[int(upload_id)],
    )
    if not df.empty:
        df['DT_HR_INSPECAO'] = pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
    return df


def reprocess_upload(conn, upload_id):
    df = detail_upload_df(conn, upload_id)
    if df.empty:
        update_upload(conn, upload_id, 'ERRO', 'Upload sem linhas brutas para reprocessar.')
        return None
    info = upload_info(conn, upload_id)
    new_name = f"REPROCESSADO_{info['file_name']}" if info else f'REPROCESSADO_{upload_id}'
    new_id = create_upload(conn, new_name, len(df), message=f'Reprocessado a partir do upload {upload_id}.')
    save_raw(conn, new_id, df[['NR_WO', 'DT_HR_INSPECAO', 'C_DPU_QG_AMARELO', 'CD_POSTO_CN']])
    update_upload(conn, new_id, 'PROCESSADO', f'Upload {upload_id} reprocessado com sucesso.')
    return new_id

# -----------------------------
# Leitura e preparo
# -----------------------------
def normalize_columns(df):
    out = df.copy()
    out.columns = [str(x).strip().replace('\ufeff', '') for x in out.columns]
    return out


def read_file(uploaded_file):
    ext = uploaded_file.name.lower().split('.')[-1]
    content = uploaded_file.getvalue()
    if ext == 'csv':
        last_err = None
        for enc in ['utf-8-sig', 'utf-16', 'latin1']:
            for sep in [None, ';', ',', '\t']:
                try:
                    if sep is None:
                        df = pd.read_csv(io.BytesIO(content), encoding=enc, sep=None, engine='python')
                    else:
                        df = pd.read_csv(io.BytesIO(content), encoding=enc, sep=sep)
                    return normalize_columns(df)
                except Exception as err:
                    last_err = err
        raise ValueError(f'Nao foi possivel ler o CSV. Detalhe: {last_err}')
    if ext in ['xlsx', 'xls']:
        engine = 'openpyxl' if ext == 'xlsx' else 'xlrd'
        return normalize_columns(pd.read_excel(io.BytesIO(content), engine=engine))
    raise ValueError('Formato nao suportado. Use .xlsx, .xls ou .csv')


def validate_df(df):
    missing = [c for c in REQ if c not in df.columns]
    return len(missing) == 0, missing


def parse_dt(series):
    dt = pd.to_datetime(series, errors='coerce')
    mask = dt.isna() & series.notna()
    if mask.any():
        dt.loc[mask] = pd.to_datetime(series[mask], errors='coerce', dayfirst=True)
    return dt


def norm_posto(value):
    txt = str(value).upper().strip()
    if 'QG09' in txt:
        return 'QG09'
    if 'QG07' in txt:
        return 'QG07'
    return txt


def prepare(df):
    w = df.copy()
    w['DT_HR_INSPECAO'] = parse_dt(w['DT_HR_INSPECAO'])
    w['C_DPU_QG_AMARELO'] = pd.to_numeric(w['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    w['NR_WO'] = w['NR_WO'].astype(str).str.strip()
    w['CD_POSTO_CN'] = w['CD_POSTO_CN'].astype(str).map(norm_posto)
    return w[w['DT_HR_INSPECAO'].notna()].copy()

# -----------------------------
# Consolidação / importação
# -----------------------------
def available_years(conn, posto):
    df = pd.read_sql_query(
        "SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano FROM raw_inspections WHERE cd_posto_cn=? ORDER BY ano",
        conn,
        params=[posto],
    )
    return [int(x) for x in df['ano'].dropna().tolist()] if not df.empty else []


def latest_upload_id_for_year(conn, posto, year):
    df = pd.read_sql_query(
        "SELECT MAX(upload_id) AS upload_id FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?",
        conn,
        params=[posto, str(year)],
    )
    if df.empty or pd.isna(df.loc[0, 'upload_id']):
        return None
    return int(df.loc[0, 'upload_id'])


def existing_range_for_posto_year(conn, posto, year):
    df = pd.read_sql_query(
        "SELECT MIN(date(dt_hr_inspecao)) AS min_d, MAX(date(dt_hr_inspecao)) AS max_d FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?",
        conn,
        params=[posto, str(year)],
    )
    if df.empty or pd.isna(df.loc[0, 'min_d']):
        return None, None
    return pd.to_datetime(df.loc[0, 'min_d']).date(), pd.to_datetime(df.loc[0, 'max_d']).date()


def count_uploads_for_posto_year(conn, posto, year):
    df = pd.read_sql_query(
        "SELECT COUNT(DISTINCT upload_id) AS qtd FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?",
        conn,
        params=[posto, str(year)],
    )
    return int(df.loc[0, 'qtd']) if not df.empty and not pd.isna(df.loc[0, 'qtd']) else 0


def delete_overlapped_period(conn, posto, start_date, end_date):
    conn.execute(
        "DELETE FROM raw_inspections WHERE cd_posto_cn=? AND datetime(dt_hr_inspecao) BETWEEN datetime(?) AND datetime(?)",
        (posto, datetime.combine(start_date, time(0,0,0)).isoformat(sep=' '), datetime.combine(end_date, time(23,59,59)).isoformat(sep=' ')),
    )
    conn.commit()


def delete_year_for_posto(conn, posto, year):
    conn.execute(
        "DELETE FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?",
        (posto, str(year)),
    )
    conn.commit()


def upload_overlap_warning(conn, df):
    warnings = []
    if df is None or df.empty:
        return warnings
    for posto in sorted(df['CD_POSTO_CN'].dropna().unique().tolist()):
        sdf = df[df['CD_POSTO_CN'] == posto]
        for ano in sorted(sdf['DT_HR_INSPECAO'].dt.year.unique().tolist()):
            ydf = sdf[sdf['DT_HR_INSPECAO'].dt.year == ano]
            if ydf.empty:
                continue
            new_min = ydf['DT_HR_INSPECAO'].dt.date.min()
            new_max = ydf['DT_HR_INSPECAO'].dt.date.max()
            old_min, old_max = existing_range_for_posto_year(conn, posto, ano)
            if old_min is None:
                continue
            overlap_start = max(new_min, old_min)
            overlap_end = min(new_max, old_max)
            if overlap_start <= overlap_end:
                warnings.append({'texto': f'Este arquivo cobre datas ja existentes entre {overlap_start.strftime("%d/%m")} e {overlap_end.strftime("%d/%m")}.', 'posto': posto, 'ano': int(ano)})
    return warnings


def preview_file_impact(conn, df):
    if df is None or df.empty:
        return pd.DataFrame(), []
    overlaps = upload_overlap_warning(conn, df)
    overlap_keys = {(x['posto'], x['ano']) for x in overlaps}
    rows = []
    for posto in sorted(df['CD_POSTO_CN'].dropna().unique().tolist()):
        sdf = df[df['CD_POSTO_CN'] == posto]
        for ano in sorted(sdf['DT_HR_INSPECAO'].dt.year.unique().tolist()):
            ydf = sdf[sdf['DT_HR_INSPECAO'].dt.year == ano]
            rows.append({
                'Posto': posto,
                'Ano': int(ano),
                'Data minima do arquivo': ydf['DT_HR_INSPECAO'].dt.date.min().strftime('%d/%m/%Y'),
                'Data maxima do arquivo': ydf['DT_HR_INSPECAO'].dt.date.max().strftime('%d/%m/%Y'),
                'Linhas do arquivo': int(len(ydf)),
                'Sobreposicao': 'Sim' if (posto, int(ano)) in overlap_keys else 'Nao',
            })
    return pd.DataFrame(rows), overlaps


def apply_import_mode(conn, df, mode):
    affected = []
    if df is None or df.empty or mode == 'Somar ao historico':
        return affected
    for posto in sorted(df['CD_POSTO_CN'].dropna().unique().tolist()):
        sdf = df[df['CD_POSTO_CN'] == posto]
        if mode == 'Substituir periodo sobreposto':
            start_date = sdf['DT_HR_INSPECAO'].dt.date.min()
            end_date = sdf['DT_HR_INSPECAO'].dt.date.max()
            delete_overlapped_period(conn, posto, start_date, end_date)
            affected.append(f'{posto}: substituido periodo {start_date.strftime("%d/%m/%Y")} a {end_date.strftime("%d/%m/%Y")}')
        elif mode == 'Reprocessar o ano inteiro':
            for ano in sorted(sdf['DT_HR_INSPECAO'].dt.year.unique().tolist()):
                delete_year_for_posto(conn, posto, int(ano))
                affected.append(f'{posto}: reprocessado ano {ano}')
    return affected


def load_merged_year_df(conn, posto, year):
    df = pd.read_sql_query(
        "SELECT id, upload_id, nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=? ORDER BY upload_id ASC, id ASC",
        conn,
        params=[posto, str(year)],
    )
    if df.empty:
        return df
    df['DT_HR_INSPECAO'] = pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
    df['C_DPU_QG_AMARELO'] = pd.to_numeric(df['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    df['CD_POSTO_CN'] = df['CD_POSTO_CN'].astype(str).map(norm_posto)
    df['NR_WO'] = df['NR_WO'].astype(str).str.strip()
    df = df[df['DT_HR_INSPECAO'].notna()].copy()
    return df.drop_duplicates(subset=['NR_WO', 'DT_HR_INSPECAO', 'CD_POSTO_CN'], keep='last').reset_index(drop=True)

# -----------------------------
# Cálculos de RFT / Rolling 12
# -----------------------------
def calc_rft(df, start_date, end_date):
    sdt = datetime.combine(start_date, time(0,0,0)); edt = datetime.combine(end_date, time(23,59,59))
    f = df[(df['DT_HR_INSPECAO'] >= sdt) & (df['DT_HR_INSPECAO'] <= edt)].copy()
    if f.empty:
        return {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0}
    grp = f.groupby('NR_WO', as_index=False)['C_DPU_QG_AMARELO'].sum().rename(columns={'C_DPU_QG_AMARELO': 'SOMA'})
    grp['RFT'] = (grp['SOMA'] == 0).astype(int)
    total = int(len(grp)); good = int(grp['RFT'].sum()); bad = int(total - good)
    pct = round((good / total) * 100, 2) if total else None
    return {'rft_pct': pct, 'total': total, 'good': good, 'bad': bad}


def compute_roll12_from_monthly(df, anchor_date=None):
    if df.empty:
        empty = pd.DataFrame(columns=['Mes', 'Produzidos', 'Nao_Defeituosos', 'RFT'])
        return {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0}, empty
    if anchor_date is None:
        anchor_date = df['DT_HR_INSPECAO'].dt.date.max()
    first = date(anchor_date.year, anchor_date.month, 1)
    months = []
    y, m = first.year, first.month
    for _ in range(12):
        months.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m = 12; y -= 1
    months = sorted(months)
    rows = []; total_prod = 0; total_good = 0
    for ms in months:
        me = date(ms.year, ms.month, monthrange(ms.year, ms.month)[1])
        res = calc_rft(df, ms, me)
        rows.append({'Mes': ms.strftime('%m/%Y'), 'Produzidos': res['total'], 'Nao_Defeituosos': res['good'], 'RFT': res['rft_pct']})
        total_prod += res['total']; total_good += res['good']
    bad = total_prod - total_good
    pct = round((total_good / total_prod) * 100, 2) if total_prod else None
    return {'rft_pct': pct, 'total': total_prod, 'good': total_good, 'bad': bad}, pd.DataFrame(rows)


def compute_weekly_monthly_ytd(df, anchor_date):
    week_start = anchor_date - timedelta(days=anchor_date.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = date(anchor_date.year, anchor_date.month, 1)
    month_end = date(anchor_date.year, anchor_date.month, monthrange(anchor_date.year, anchor_date.month)[1])
    ytd_start = date(anchor_date.year, 1, 1)
    return {
        'Semanal': calc_rft(df, week_start, week_end),
        'Mensal': calc_rft(df, month_start, month_end),
        'YTD': calc_rft(df, ytd_start, anchor_date),
        'week_label': f'{week_start.strftime("%d/%m/%Y")} a {week_end.strftime("%d/%m/%Y")}',
        'month_label': month_start.strftime('%m/%Y'),
    }


def monthly_trend(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return pd.DataFrame(columns=['Mes', 'RFT'])
    rows = []
    for month in sorted(ydf['DT_HR_INSPECAO'].dt.month.unique().tolist()):
        start = date(year, int(month), 1)
        end = date(year, int(month), monthrange(year, int(month))[1])
        rows.append({'Mes': start.strftime('%m/%Y'), 'RFT': calc_rft(ydf, start, end)['rft_pct'] or 0})
    return pd.DataFrame(rows)


def weekly_trend(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return pd.DataFrame(columns=['Semana', 'RFT'])
    dates = sorted(ydf['DT_HR_INSPECAO'].dt.date.unique().tolist())
    mondays = sorted({d - timedelta(days=d.weekday()) for d in dates})
    rows = []
    for i, m in enumerate(mondays, start=1):
        we = m + timedelta(days=6)
        rows.append({'Semana': f'Semana {i:02d}', 'RFT': calc_rft(ydf, m, we)['rft_pct'] or 0})
    return pd.DataFrame(rows)


def base_health_status(last_date, selected_year):
    today = date.today()
    if last_date is None:
        return 'Sem dados', 'pill-red'
    if selected_year < today.year:
        return ('Atualizada', 'pill-green') if last_date >= date(selected_year, CUTOFF_MONTH, CUTOFF_DAY) else ('Parcial', 'pill-amber')
    gap = (today - last_date).days
    if gap <= 1:
        return 'Atualizada', 'pill-green'
    if gap <= 7:
        return 'Parcial', 'pill-amber'
    return 'Defasada', 'pill-red'


def summarize_base(df, conn, posto, ano):
    min_d = df['DT_HR_INSPECAO'].dt.date.min() if not df.empty else None
    max_d = df['DT_HR_INSPECAO'].dt.date.max() if not df.empty else None
    status, status_cls = base_health_status(max_d, ano)
    uploads_count = count_uploads_for_posto_year(conn, posto, ano)
    return {
        'min_date': min_d,
        'max_date': max_d,
        'last_date': max_d,
        'days_covered': int(df['DT_HR_INSPECAO'].dt.date.nunique()) if not df.empty else 0,
        'uploads_count': uploads_count,
        'status': status,
        'status_cls': status_cls,
    }

# -----------------------------
# UI helpers
# -----------------------------
def format_pct(v):
    return 'Sem dados' if v is None or pd.isna(v) else f'{v:.2f}'.replace('.', ',') + '%'


def status_class(v):
    if v is None or pd.isna(v):
        return 'neutral'
    return 'ok' if v <= current_meta() else 'bad'


def metric_card_html(title, result, subtitle=''):
    if result is None:
        value, css, meta_text = 'Sem dados', 'neutral', subtitle
    else:
        value = format_pct(result['rft_pct'])
        css = status_class(result['rft_pct'])
        meta_text = f"{subtitle}<br>Frames bons: {result['good']} | defeituosos: {result['bad']} | produzidos: {result['total']}"
    return f'<div class="metric-card"><div class="muted">{title}</div><div style="font-size:1.9rem;font-weight:800;" class="{css}">{value}</div><div class="muted">{meta_text}</div></div>'


def kv_html(label, value):
    return f'<div class="kv"><div class="muted">{label}</div><div><strong>{value}</strong></div></div>'

# -----------------------------
# Main
# -----------------------------
def main():
    conn = get_conn()
    init_db(conn)
    st.title('Qualidade | RFT Automatico - V7.1.1')

    with st.sidebar:
        default_posto = ls_get('posto', POSTO_PADRAO)
        posto = st.radio('Posto', POSTOS, index=POSTOS.index(default_posto) if default_posto in POSTOS else 0, horizontal=True)
        ls_set('posto', posto)

        years = available_years(conn, posto)
        if years:
            prev_year = ls_get('ano', None)
            try:
                prev_year = int(prev_year) if prev_year is not None else None
            except Exception:
                prev_year = None
            ano = st.selectbox('Ano', years, index=years.index(prev_year) if prev_year in years else len(years)-1)
            ls_set('ano', ano)
        else:
            ano = None
            st.info('Sem dados salvos para este posto.')

        selected_period = st.radio('Indicador principal', ['Semanal', 'Mensal', 'YTD'], index=1)

        saved_meta = ls_get('meta_rft', DEFAULT_META_RFT)
        try:
            saved_meta = float(str(saved_meta).replace(',', '.'))
        except Exception:
            saved_meta = DEFAULT_META_RFT
        meta = st.number_input('Meta RFT (%)', min_value=0.0, max_value=100.0, value=float(saved_meta), step=0.1)
        st.session_state['meta_rft'] = float(meta)
        ls_set('meta_rft', meta)
        st.caption('Regra visual: RFT <= meta = verde | RFT > meta = vermelho')

    if ano is not None:
        latest = latest_upload_id_for_year(conn, posto, ano)
    else:
        latest = None

    if latest is not None:
        info = upload_info(conn, latest)
        df = load_merged_year_df(conn, posto, ano)
        if not df.empty:
            base_summary = summarize_base(df, conn, posto, ano)
            anchor = df['DT_HR_INSPECAO'].dt.date.max()
            rolling12, rolling12_table = compute_roll12_from_monthly(df, anchor)
            selected = compute_weekly_monthly_ytd(df, anchor)
            st.caption(f"Ano: {ano} | Último arquivo: {info['file_name'] if info else '-'} | Último upload: {info['uploaded_at'] if info else '-'} | Status da base: {base_summary['status']}")
            st.markdown(
                f"<div class='pill pill-blue'>Posto: <strong>{posto}</strong></div>"
                f"<div class='pill {base_summary['status_cls']}'>Status da base: <strong>{base_summary['status']}</strong></div>"
                f"<div class='pill pill-blue'>Meta: <strong>{str(meta).replace('.', ',')}%</strong></div>"
                f"<div class='pill pill-blue'>Uploads consolidados: <strong>{base_summary['uploads_count']}</strong></div>",
                unsafe_allow_html=True,
            )
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(metric_card_html('Rolling 12', rolling12, 'Soma dos bons ÷ soma dos produzidos dos últimos 12 meses'), unsafe_allow_html=True)
            with c2:
                st.markdown(metric_card_html(selected_period, selected[selected_period], 'Indicador selecionado'), unsafe_allow_html=True)
            with c3:
                st.markdown(metric_card_html('Mensal', selected['Mensal'], f"Mês atual: {selected['month_label']}"), unsafe_allow_html=True)
            with c4:
                st.markdown(metric_card_html('YTD', selected['YTD'], 'Acumulado do ano até hoje'), unsafe_allow_html=True)

            l, r = st.columns([1.2, 1])
            with l:
                st.subheader('Resumo executivo da base')
                for label, value in [
                    ('Data mínima da base', base_summary['min_date'].strftime('%d/%m/%Y') if base_summary['min_date'] else '-'),
                    ('Data máxima da base', base_summary['max_date'].strftime('%d/%m/%Y') if base_summary['max_date'] else '-'),
                    ('Última data com dado', base_summary['last_date'].strftime('%d/%m/%Y') if base_summary['last_date'] else '-'),
                    ('Dias cobertos', str(base_summary['days_covered'])),
                    ('Uploads consolidados', str(base_summary['uploads_count'])),
                    ('Status da base', base_summary['status']),
                ]:
                    st.markdown(kv_html(label, value), unsafe_allow_html=True)
            with r:
                diff = 'Sem dados' if rolling12['rft_pct'] is None else f"{(rolling12['rft_pct'] - meta):+.2f}".replace('.', ',') + ' p.p.'
                st.markdown(
                    '<div class="section">'
                    '<div class="muted">Meta x resultado (Rolling 12)</div>'
                    f'<div style="font-size:1.9rem;font-weight:800;" class="{status_class(rolling12["rft_pct"])}">{format_pct(rolling12["rft_pct"])} </div>'
                    f'<div class="muted">Meta configurada: {str(meta).replace(".", ",")}%<br>Diferença: {diff}</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

            st.subheader('Tabela Rolling 12 Months')
            chart = rolling12_table[['Mes', 'RFT']].copy().set_index('Mes')
            chart['Meta'] = meta
            st.line_chart(chart, use_container_width=True)
            table_show = rolling12_table.copy()
            table_show['RFT'] = table_show['RFT'].map(lambda x: '' if pd.isna(x) else f'{x:.2f}'.replace('.', ',') + '%')
            st.dataframe(table_show, use_container_width=True, hide_index=True)

            st.subheader('Tendência')
            mt = monthly_trend(df, ano)
            wt = weekly_trend(df, ano)
            c5, c6 = st.columns(2)
            with c5:
                st.markdown('<div class="section"><div class="muted">Tendência mensal</div></div>', unsafe_allow_html=True)
                if mt.empty:
                    st.info('Sem dados mensais.')
                else:
                    st.line_chart(mt.set_index('Mes'), use_container_width=True)
                    st.dataframe(mt, use_container_width=True, hide_index=True)
            with c6:
                st.markdown('<div class="section"><div class="muted">Tendência semanal</div></div>', unsafe_allow_html=True)
                if wt.empty:
                    st.info('Sem dados semanais.')
                else:
                    st.bar_chart(wt.set_index('Semana'), use_container_width=True)
                    st.dataframe(wt, use_container_width=True, hide_index=True)
        else:
            st.warning('Sem linhas válidas para esse posto/ano.')
    else:
        st.info('Sem histórico para esse ano/posto. Faça upload de uma base.')

    st.divider()
    st.subheader('Base & Upload')
    import_mode = st.radio('Modo de importação', ['Somar ao historico', 'Substituir periodo sobreposto', 'Reprocessar o ano inteiro'])
    uploaded = st.file_uploader('Base operacional atual (.xlsx, .xls ou .csv)', type=['xlsx', 'xls', 'csv'])
    prepared = None
    if uploaded is not None:
        try:
            raw = read_file(uploaded)
            ok, miss = validate_df(raw)
            if not ok:
                st.error('Base operacional inválida: ' + ', '.join(miss))
            else:
                prepared = prepare(raw)
                impact, overlaps = preview_file_impact(conn, prepared)
                if not impact.empty:
                    st.dataframe(impact, use_container_width=True, hide_index=True)
                for item in overlaps:
                    st.warning(item['texto'])
        except Exception as err:
            st.error(f'Erro ao analisar a base: {err}')

    if st.button('Salvar arquivo localmente', type='primary', use_container_width=True):
        if uploaded is None or prepared is None:
            st.error('Selecione um arquivo válido antes de salvar.')
        elif prepared.empty:
            st.error('A base foi lida, mas não restaram linhas válidas após o tratamento.')
        else:
            affected = apply_import_mode(conn, prepared, import_mode)
            uid = create_upload(conn, uploaded.name, len(prepared), message=f'Modo de importacao: {import_mode}.')
            save_raw(conn, uid, prepared)
            msg = 'Base salva com sucesso.' + (' ' + ' | '.join(affected) if affected else '')
            update_upload(conn, uid, 'PROCESSADO', msg)
            st.success(msg)
            st.rerun()

    st.divider()
    st.subheader('Histórico local')
    hist = uploads_table(conn)
    if hist.empty:
        st.info('Os uploads processados aparecerão aqui.')
    else:
        st.dataframe(hist, use_container_width=True, hide_index=True)
        selected_id = st.selectbox('Selecionar upload', hist['id'].tolist(), format_func=lambda x: f'Upload {x}')
        c7, c8, c9 = st.columns(3)
        with c7:
            if st.button('Ver detalhes do upload', use_container_width=True):
                detail = detail_upload_df(conn, selected_id)
                if detail.empty:
                    st.warning('Upload sem detalhes disponíveis.')
                else:
                    sel_info = upload_info(conn, selected_id)
                    file_name = sel_info['file_name'] if sel_info else '-'
                    uploaded_at = sel_info['uploaded_at'] if sel_info else '-'
                    st.info(f'Arquivo: {file_name} | Upload: {uploaded_at} | Linhas: {len(detail)}')
                    detail_show = detail.copy()
                    detail_show['DT_HR_INSPECAO'] = detail_show['DT_HR_INSPECAO'].dt.strftime('%d/%m/%Y %H:%M:%S')
                    st.dataframe(detail_show.head(200), use_container_width=True, hide_index=True)
        with c8:
            if st.button('Reprocessar upload', use_container_width=True):
                new_id = reprocess_upload(conn, selected_id)
                st.success(f'Upload reprocessado com sucesso. Novo upload: {new_id}.' if new_id else 'Não foi possível reprocessar o upload.')
                st.rerun()
        with c9:
            if st.button('Excluir upload específico', use_container_width=True):
                delete_upload(conn, selected_id)
                st.success('Upload excluído com sucesso.')
                st.rerun()

if __name__ == '__main__':
    main()
