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

st.set_page_config(page_title='RFT Qualidade - V7.0', page_icon='Q', layout='wide', initial_sidebar_state='expanded')

DB = 'rft_v61_local.db'
REQ = ['NR_WO', 'DT_HR_INSPECAO', 'C_DPU_QG_AMARELO', 'CD_POSTO_CN']
POSTOS = ['QG09', 'QG07']
POSTO_PADRAO = 'QG09'
LS_PREFIX = 'rft_v70_'
DEFAULT_META_RFT = 95.0
CUTOFF_MONTH = 12
CUTOFF_DAY = 12

CUSTOM_CSS = '''
<style>
:root { --bg:#0f172a; --border:rgba(148,163,184,.18); --text:#e5e7eb; --muted:#94a3b8; --green:#22c55e; --red:#ef4444; --amber:#f59e0b; --blue:#3b82f6; }
html, body, [data-testid="stAppViewContainer"], .stApp { background: linear-gradient(180deg, #0b1220 0%, #0f172a 100%); color: var(--text); }
[data-testid="stHeader"] { background: rgba(15,23,42,.78); border-bottom: 1px solid var(--border); }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0c1527 0%, #121d31 100%); border-right: 1px solid var(--border); }
[data-testid="stSidebar"] * { color: var(--text) !important; }
.block-container { padding-top: 1.0rem; padding-bottom: 2rem; }
h1,h2,h3,h4,h5,h6,label,p,div,span { color: var(--text); }
.hero { background:linear-gradient(135deg,rgba(24,34,53,.96),rgba(16,24,40,.98)); border:1px solid var(--border); border-radius:22px; padding:1.2rem 1.3rem; margin-bottom:1rem; }
.hero-logo { width:58px; height:58px; border-radius:18px; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg,rgba(59,130,246,.18),rgba(37,99,235,.40)); border:1px solid rgba(59,130,246,.30); font-weight:800; letter-spacing:.04em; }
.section { background:linear-gradient(180deg,rgba(28,37,55,.96),rgba(18,27,41,.98)); border:1px solid var(--border); border-radius:18px; padding:1rem; margin-bottom:1rem; }
.metric-card { border:1px solid var(--border); background:linear-gradient(180deg,rgba(31,42,61,.96),rgba(22,31,47,.98)); border-radius:18px; padding:1rem; min-height:145px; }
.muted { color: var(--muted); } .ok{color:var(--green);} .bad{color:var(--red);} .neutral{color:var(--text);} .pill{display:inline-flex;align-items:center;gap:.35rem;padding:.45rem .75rem;border-radius:999px;border:1px solid var(--border);background:rgba(255,255,255,.04);font-size:.84rem;margin-right:.35rem;margin-bottom:.35rem;} .pill-green{background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.28);} .pill-red{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.28);} .pill-amber{background:rgba(245,158,11,.12);border-color:rgba(245,158,11,.28);} .pill-blue{background:rgba(59,130,246,.12);border-color:rgba(59,130,246,.28);} 
[data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:18px; overflow:hidden; }
</style>
'''

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

def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS upload_log (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL, uploaded_at TEXT NOT NULL, total_rows INTEGER NOT NULL, status TEXT NOT NULL, message TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS raw_inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, nr_wo TEXT, dt_hr_inspecao TEXT, c_dpu_qg_amarelo REAL, cd_posto_cn TEXT)')
    conn.commit()

def create_upload(conn, file_name, total_rows, status='RECEBIDO', message=''):
    cur = conn.execute('INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)', (file_name, datetime.now().isoformat(timespec='seconds'), int(total_rows), status, message))
    conn.commit()
    return int(cur.lastrowid)

def update_upload(conn, upload_id, status, message=''):
    conn.execute('UPDATE upload_log SET status=?, message=? WHERE id=?', (status, message, int(upload_id)))
    conn.commit()

def save_raw(conn, upload_id, df):
    rows = [(int(upload_id), r['NR_WO'], r['DT_HR_INSPECAO'].isoformat(sep=' ', timespec='seconds'), float(r['C_DPU_QG_AMARELO']), r['CD_POSTO_CN']) for _, r in df.iterrows()]
    conn.executemany('INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn) VALUES (?, ?, ?, ?, ?)', rows)
    conn.commit()

def uploads_table(conn):
    return pd.read_sql_query('SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC LIMIT 500', conn)

def delete_upload(conn, upload_id):
    conn.execute('DELETE FROM raw_inspections WHERE upload_id=?', (int(upload_id),))
    conn.execute('DELETE FROM upload_log WHERE id=?', (int(upload_id),))
    conn.commit()

def reprocess_upload(conn, upload_id):
    cur = conn.execute('SELECT COUNT(*) FROM raw_inspections WHERE upload_id=?', (int(upload_id),))
    qtd = cur.fetchone()[0]
    if qtd == 0:
        update_upload(conn, upload_id, 'ERRO', 'Upload sem linhas brutas para reprocessar.')
        return False
    update_upload(conn, upload_id, 'REPROCESSADO', f'Reprocessado manualmente em {datetime.now().isoformat(timespec="seconds")} com {qtd} linhas preservadas.')
    return True

def available_years(conn, posto):
    df = pd.read_sql_query("SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano FROM raw_inspections WHERE cd_posto_cn=? ORDER BY ano", conn, params=[posto])
    return [int(x) for x in df['ano'].dropna().tolist()] if not df.empty else []

def latest_upload_id_for_year(conn, posto, year):
    df = pd.read_sql_query("SELECT MAX(upload_id) AS upload_id FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", conn, params=[posto, str(year)])
    if df.empty or pd.isna(df.loc[0, 'upload_id']):
        return None
    return int(df.loc[0, 'upload_id'])

def upload_info(conn, upload_id):
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM upload_log WHERE id=?', (int(upload_id),)).fetchone()
    conn.row_factory = None
    return row

def upload_detail_df(conn, upload_id):
    df = pd.read_sql_query("SELECT nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE upload_id=? ORDER BY dt_hr_inspecao, nr_wo", conn, params=[int(upload_id)])
    if not df.empty:
        df['DT_HR_INSPECAO'] = pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
    return df

def existing_range_for_posto_year(conn, posto, year):
    df = pd.read_sql_query("SELECT MIN(date(dt_hr_inspecao)) AS min_d, MAX(date(dt_hr_inspecao)) AS max_d FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", conn, params=[posto, str(year)])
    if df.empty or pd.isna(df.loc[0, 'min_d']):
        return None, None
    return pd.to_datetime(df.loc[0, 'min_d']).date(), pd.to_datetime(df.loc[0, 'max_d']).date()

def count_uploads_for_posto_year(conn, posto, year):
    df = pd.read_sql_query("SELECT COUNT(DISTINCT upload_id) AS qtd FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", conn, params=[posto, str(year)])
    return int(df.loc[0, 'qtd']) if not df.empty and not pd.isna(df.loc[0, 'qtd']) else 0

def delete_overlapped_period(conn, posto, start_date, end_date):
    conn.execute("DELETE FROM raw_inspections WHERE cd_posto_cn=? AND datetime(dt_hr_inspecao) BETWEEN datetime(?) AND datetime(?)", (posto, datetime.combine(start_date, time(0,0,0)).isoformat(sep=' '), datetime.combine(end_date, time(23,59,59)).isoformat(sep=' ')))
    conn.commit()

def delete_year_for_posto(conn, posto, year):
    conn.execute("DELETE FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", (posto, str(year)))
    conn.commit()

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
    if 'QG09' in txt: return 'QG09'
    if 'QG07' in txt: return 'QG07'
    return txt

def prepare(df):
    w = df.copy()
    w['DT_HR_INSPECAO'] = parse_dt(w['DT_HR_INSPECAO'])
    w['C_DPU_QG_AMARELO'] = pd.to_numeric(w['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    w['NR_WO'] = w['NR_WO'].astype(str).str.strip()
    w['CD_POSTO_CN'] = w['CD_POSTO_CN'].astype(str).map(norm_posto)
    return w[w['DT_HR_INSPECAO'].notna()].copy()

def load_merged_year_df(conn, posto, year):
    df = pd.read_sql_query("SELECT id, upload_id, nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=? ORDER BY upload_id ASC, id ASC", conn, params=[posto, str(year)])
    if df.empty:
        return df
    df['DT_HR_INSPECAO'] = pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
    df['C_DPU_QG_AMARELO'] = pd.to_numeric(df['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    df['CD_POSTO_CN'] = df['CD_POSTO_CN'].astype(str).map(norm_posto)
    df['NR_WO'] = df['NR_WO'].astype(str).str.strip()
    df = df[df['DT_HR_INSPECAO'].notna()].copy()
    return df.drop_duplicates(subset=['NR_WO', 'DT_HR_INSPECAO', 'CD_POSTO_CN'], keep='last').reset_index(drop=True)

def calc_rft(df, start_date, end_date):
    sdt = datetime.combine(start_date, time(0,0,0)); edt = datetime.combine(end_date, time(23,59,59))
    f = df[(df['DT_HR_INSPECAO'] >= sdt) & (df['DT_HR_INSPECAO'] <= edt)].copy()
    if f.empty:
        return {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0}
    grp = f.groupby('NR_WO', as_index=False)['C_DPU_QG_AMARELO'].sum().rename(columns={'C_DPU_QG_AMARELO':'SOMA'})
    grp['RFT'] = (grp['SOMA'] == 0).astype(int)
    total = int(len(grp)); good = int(grp['RFT'].sum()); bad = int(total - good)
    pct = round((good / total) * 100, 2) if total else None
    return {'rft_pct': pct, 'total': total, 'good': good, 'bad': bad}

def year_status(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year]
    if ydf.empty:
        return False, 'Sem dados'
    max_d = ydf['DT_HR_INSPECAO'].dt.date.max(); cutoff = date(year, CUTOFF_MONTH, CUTOFF_DAY)
    return (max_d >= cutoff), ('Fechado em 12/12' if max_d >= cutoff else 'Ate ' + max_d.strftime('%d/%m/%Y'))

def week_options(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty: return []
    dates = sorted(ydf['DT_HR_INSPECAO'].dt.date.unique().tolist())
    mondays = sorted({d - timedelta(days=d.weekday()) for d in dates})
    return [(f'Semana {i:02d} - {m.strftime("%d/%m/%Y")} a {(m + timedelta(days=6)).strftime("%d/%m/%Y")}', m, m + timedelta(days=6)) for i, m in enumerate(mondays, start=1)]

def month_options(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty: return []
    opts = []
    for month in sorted(ydf['DT_HR_INSPECAO'].dt.month.unique().tolist()):
        start = date(year, int(month), 1); end = date(year, int(month), monthrange(year, int(month))[1])
        opts.append((f'{start.strftime("%m/%Y")} - {start.strftime("%d/%m/%Y")} a {end.strftime("%d/%m/%Y")}', start, end))
    return opts

def compute_selected_metrics(df, ano, mode, selected_range, ok_ano, max_date):
    daily = weekly = monthly = yearly = ytd = None
    start, end = selected_range
    if mode == 'Diario':
        sel = start; daily = calc_rft(df, sel, sel)
        ws = sel - timedelta(days=sel.weekday()); weekly = calc_rft(df, ws, ws + timedelta(days=6))
        ms = date(ano, sel.month, 1); monthly = calc_rft(df, ms, date(ano, sel.month, monthrange(ano, sel.month)[1]))
        yearly = calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None
        ytd = calc_rft(df, date(ano,1,1), sel)
    elif mode == 'Semanal':
        ws, we = start, end; weekly = calc_rft(df, ws, we); yearly = calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None; ytd = calc_rft(df, date(ano,1,1), min(we, max_date))
    elif mode == 'Mensal':
        ms, me = start, end; monthly = calc_rft(df, ms, me); yearly = calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None; ytd = calc_rft(df, date(ano,1,1), min(me, max_date))
    else:
        yearly = calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None; ytd = calc_rft(df, date(ano,1,1), min(max_date, date(ano,12,12)))
    return {'daily': daily, 'weekly': weekly, 'monthly': monthly, 'yearly': yearly, 'ytd': ytd}

def monthly_trend(df, year, meta):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return pd.DataFrame(columns=['Mes','RFT','Meta','Delta_pp','Acumulado_Ano','Arrow','Status'])
    rows = []; prev = None
    for month in sorted(ydf['DT_HR_INSPECAO'].dt.month.unique().tolist()):
        start = date(year, int(month), 1); end = date(year, int(month), monthrange(year, int(month))[1])
        rft = calc_rft(ydf, start, end)['rft_pct'] or 0
        delta = None if prev is None else round(rft - prev, 2)
        rows.append({'Mes': start.strftime('%m/%Y'), 'RFT': rft, 'Meta': meta, 'Delta_pp': delta})
        prev = rft
    out = pd.DataFrame(rows)
    out['Acumulado_Ano'] = out['RFT'].expanding().mean().round(2)
    out['Arrow'] = out['Delta_pp'].apply(lambda x: '->' if pd.isna(x) or abs(x) < 0.01 else ('↑' if x > 0 else '↓'))
    out['Status'] = out['Delta_pp'].apply(lambda x: 'estavel' if pd.isna(x) or abs(x) < 0.01 else ('melhorou' if x > 0 else 'piorou'))
    return out

def weekly_trend(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty: return pd.DataFrame(columns=['Semana','RFT'])
    rows = []
    for label, ws, we in week_options(ydf, year):
        rows.append({'Semana': label.split('-')[0].strip(), 'RFT': calc_rft(ydf, ws, we)['rft_pct'] or 0})
    return pd.DataFrame(rows)

def base_health_status(last_date, selected_year):
    today = date.today()
    if last_date is None: return 'Sem dados', 'pill-red'
    if selected_year < today.year:
        return ('Atualizada', 'pill-green') if last_date >= date(selected_year, CUTOFF_MONTH, CUTOFF_DAY) else ('Parcial', 'pill-amber')
    gap = (today - last_date).days
    if gap <= 1: return 'Atualizada', 'pill-green'
    if gap <= 7: return 'Parcial', 'pill-amber'
    return 'Defasada', 'pill-red'

def summarize_base(df, conn, posto, ano):
    min_d = df['DT_HR_INSPECAO'].dt.date.min() if not df.empty else None
    max_d = df['DT_HR_INSPECAO'].dt.date.max() if not df.empty else None
    status, status_cls = base_health_status(max_d, ano)
    return {'min_date': min_d, 'max_date': max_d, 'last_date': max_d, 'days_covered': int(df['DT_HR_INSPECAO'].dt.date.nunique()) if not df.empty else 0, 'uploads_count': count_uploads_for_posto_year(conn, posto, ano), 'status': status, 'status_cls': status_cls}

def format_pct(value):
    return 'Sem dados' if value is None or pd.isna(value) else f'{value:.2f}'.replace('.', ',') + '%'

def format_date(value):
    return '-' if value is None else value.strftime('%d/%m/%Y')

def status_class(value):
    meta = current_meta()
    if value is None or pd.isna(value): return 'neutral'
    return 'ok' if value <= meta else 'bad'

def metric_card(title, result, subtitle=''):
    if result is None:
        value, css, meta_text = 'Sem dados', 'neutral', subtitle
    else:
        value = format_pct(result['rft_pct']); css = status_class(result['rft_pct']); meta_text = f"{subtitle}<br>WOs boas: {result['good']} | ruins: {result['bad']} | total: {result['total']}"
    return f'<div class="metric-card"><div class="metric-title">{title}</div><div class="metric-value {css}">{value}</div><div class="metric-meta">{meta_text}</div></div>'

def info_row(label, value):
    return f'<div style="display:flex;justify-content:space-between;gap:1rem;padding:.6rem .75rem;border-radius:14px;background:rgba(255,255,255,.03);border:1px solid rgba(148,163,184,.09);margin-bottom:.5rem;"><div style="color:#94a3b8;font-size:.88rem;">{label}</div><div style="font-weight:600;text-align:right;">{value}</div></div>'

def render_empty_state(message, subtitle='Adicione um arquivo na aba Base & Upload para iniciar o historico visual.'):
    st.markdown(f'<div class="section"><div class="section-title">{message}</div><div class="section-sub">{subtitle}</div></div>', unsafe_allow_html=True)

def build_sidebar(conn):
    with st.sidebar:
        st.markdown('## Qualidade')
        st.caption('RFT Automatico - V7.0')
        default_posto = ls_get('posto', POSTO_PADRAO)
        posto_idx = POSTOS.index(default_posto) if default_posto in POSTOS else 0
        posto = st.radio('Posto', POSTOS, index=posto_idx, horizontal=True)
        ls_set('posto', posto)
        anos = available_years(conn, posto)
        if anos:
            prev_year = ls_get('ano', None)
            try: prev_year = int(prev_year) if prev_year is not None else None
            except Exception: prev_year = None
            ano_idx = anos.index(prev_year) if prev_year in anos else len(anos) - 1
            ano = st.selectbox('Ano', anos, index=ano_idx)
            ls_set('ano', ano)
        else:
            ano = None; st.info('Sem dados salvos para este posto.')
        mode_options = ['Diario','Semanal','Mensal','Anual']
        default_mode = ls_get('modo', 'Diario')
        mode_idx = mode_options.index(default_mode) if default_mode in mode_options else 0
        mode = st.radio('Modo de visualizacao', mode_options, index=mode_idx)
        ls_set('modo', mode)
        st.markdown('---')
        saved_meta = ls_get('meta_rft', DEFAULT_META_RFT)
        try: saved_meta = float(str(saved_meta).replace(',', '.'))
        except Exception: saved_meta = DEFAULT_META_RFT
        meta = st.number_input('Meta RFT (%)', min_value=0.0, max_value=100.0, value=float(saved_meta), step=0.1)
        st.session_state['meta_rft'] = float(meta)
        ls_set('meta_rft', meta)
        st.caption('Regra visual ativa'); st.write('RFT <= meta = verde'); st.write('RFT > meta = vermelho')
    return posto, ano, mode, float(meta)

def resolve_period_selection(df, ano, mode):
    min_date = df['DT_HR_INSPECAO'].dt.date.min(); max_date = df['DT_HR_INSPECAO'].dt.date.max()
    selected_label = f'Ano {ano}'; selected_range = (date(ano,1,1), min(max_date, date(ano,12,12)))
    if mode == 'Diario':
        saved_day = ls_get('dia', '')
        try: default_day = datetime.fromisoformat(saved_day).date() if saved_day else max_date
        except Exception: default_day = max_date
        if default_day < min_date or default_day > max_date: default_day = max_date
        selected = st.sidebar.date_input('Dia', value=default_day, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='day_v70')
        ls_set('dia', selected.isoformat())
        selected_label = selected.strftime('%d/%m/%Y'); selected_range = (selected, selected)
    elif mode == 'Semanal':
        opts = week_options(df, ano); labels = [x[0] for x in opts]
        if not labels: return min_date, max_date, selected_label, selected_range, False
        saved = ls_get('semana_label', ''); idx = labels.index(saved) if saved in labels else len(labels) - 1
        label = st.sidebar.selectbox('Semana do ano', labels, index=idx)
        ls_set('semana_label', label); found = next(x for x in opts if x[0] == label)
        selected_label = label; selected_range = (found[1], found[2])
    elif mode == 'Mensal':
        opts = month_options(df, ano); labels = [x[0] for x in opts]
        if not labels: return min_date, max_date, selected_label, selected_range, False
        saved = ls_get('mes_label', ''); idx = labels.index(saved) if saved in labels else len(labels) - 1
        label = st.sidebar.selectbox('Mes do ano', labels, index=idx)
        ls_set('mes_label', label); found = next(x for x in opts if x[0] == label)
        selected_label = label; selected_range = (found[1], found[2])
    return min_date, max_date, selected_label, selected_range, True

def render_hero(info, posto, ano, status_label, base_summary, meta):
    file_name = info['file_name'] if info else '-'
    uploaded_at = info['uploaded_at'] if info else '-'
    html = f'''<div class="hero"><div style="display:grid;grid-template-columns:1.6fr 1fr;gap:1rem;align-items:center;"><div style="display:flex;gap:1rem;align-items:center;"><div class="hero-logo">Q</div><div><div class="hero-title">Qualidade | RFT Automatico - V7.0</div><div class="hero-sub">Painel corporativo com consolidacao inteligente de uploads, meta configuravel e leitura executiva da base.</div></div></div><div style="display:flex;flex-wrap:wrap;gap:.5rem;justify-content:flex-end;"><div class="pill pill-blue">Posto: <strong>{posto}</strong></div><div class="pill {base_summary['status_cls']}">Status da base: <strong>{base_summary['status']}</strong></div><div class="pill pill-blue">Meta: <strong>{str(meta).replace('.', ',')}%</strong></div><div class="pill pill-blue">Uploads consolidados: <strong>{base_summary['uploads_count']}</strong></div></div></div><div style="height:10px"></div><div class="muted">Ano: <b>{ano}</b> | Fechamento: <b>{status_label}</b> | Ultimo arquivo: <b>{file_name}</b> | Ultimo upload: <b>{uploaded_at}</b> | Janela consolidada: <b>{format_date(base_summary['min_date'])} ate {format_date(base_summary['max_date'])}</b></div></div>'''
    st.markdown(html, unsafe_allow_html=True)

def render_dashboard(df, metrics, selected_label, info, posto, ano, status_label, meta, base_summary):
    render_hero(info, posto, ano, status_label, base_summary, meta)
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: st.markdown(metric_card('RFT Diario', metrics['daily'], 'Leitura do dia selecionado'), unsafe_allow_html=True)
    with c2: st.markdown(metric_card('RFT Semanal', metrics['weekly'], 'Consolidacao semanal'), unsafe_allow_html=True)
    with c3: st.markdown(metric_card('RFT Mensal', metrics['monthly'], 'Consolidacao mensal'), unsafe_allow_html=True)
    with c4: st.markdown(metric_card('RFT Anual', metrics['yearly'], 'Ano ate 12/12'), unsafe_allow_html=True)
    with c5: st.markdown(metric_card('RFT YTD', metrics['ytd'], 'Acumulado ate o recorte'), unsafe_allow_html=True)
    left, right = st.columns([1.25, 1])
    with left:
        st.markdown('<div class="section"><div class="section-title">Resumo executivo da base</div><div class="section-sub">Cobertura da base consolidada e contexto do recorte.</div>', unsafe_allow_html=True)
        for label, value in [('Recorte atual', selected_label), ('Data minima da base', format_date(base_summary['min_date'])), ('Data maxima da base', format_date(base_summary['max_date'])), ('Ultima data com dado', format_date(base_summary['last_date'])), ('Dias cobertos', str(base_summary['days_covered'])), ('Uploads consolidados', str(base_summary['uploads_count'])), ('Status da base', base_summary['status'])]:
            st.markdown(info_row(label, value), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        current = metrics['ytd'] if metrics['ytd'] is not None else metrics['monthly']
        current_pct = None if current is None else current['rft_pct']
        diff = 'Sem dados' if current_pct is None else f'{(current_pct - meta):+.2f}'.replace('.', ',') + ' p.p.'
        color = status_class(current_pct)
        st.markdown(f'<div class="section"><div class="section-title">Meta x resultado</div><div class="section-sub">Regra visual aplicada conforme sua configuracao.</div><div class="metric-value {color}">{format_pct(current_pct)}</div><div class="muted">Meta configurada: {str(meta).replace(".", ",")}%<br>Diferenca: {diff}<br>Regra: RFT <= meta fica verde | RFT > meta fica vermelho</div></div>', unsafe_allow_html=True)

def render_tendencia(df, ano, meta):
    monthly_df = monthly_trend(df, ano, meta); weekly_df = weekly_trend(df, ano)
    st.markdown('<div class="section"><div class="section-title">Tendencia mensal</div><div class="section-sub">Linha de meta destacada, melhor e pior periodo, comparacao mes atual vs anterior e acumulado do ano.</div>', unsafe_allow_html=True)
    if monthly_df.empty:
        st.info('Sem dados mensais disponiveis.')
    else:
        st.line_chart(monthly_df.set_index('Mes')[['Meta', 'Acumulado_Ano']], use_container_width=True)
        st.bar_chart(monthly_df.set_index('Mes')[['RFT']], use_container_width=True)
        best_idx = monthly_df['RFT'].idxmax(); worst_idx = monthly_df['RFT'].idxmin()
        a,b = st.columns(2)
        with a: st.markdown(info_row('Melhor periodo', f"{monthly_df.loc[best_idx, 'Mes']} | {format_pct(monthly_df.loc[best_idx, 'RFT'])}"), unsafe_allow_html=True)
        with b: st.markdown(info_row('Pior periodo', f"{monthly_df.loc[worst_idx, 'Mes']} | {format_pct(monthly_df.loc[worst_idx, 'RFT'])}"), unsafe_allow_html=True)
        latest = monthly_df.iloc[-1]; prev = monthly_df.iloc[-2] if len(monthly_df) > 1 else None
        c1,c2,c3 = st.columns(3)
        with c1: st.markdown(info_row('Mes atual', f"{latest['Mes']} | {format_pct(latest['RFT'])}"), unsafe_allow_html=True)
        with c2:
            txt = 'Sem comparacao disponivel' if prev is None else f"{prev['Mes']} | {format_pct(prev['RFT'])}"
            st.markdown(info_row('Mes anterior', txt), unsafe_allow_html=True)
        with c3:
            delta = latest['Delta_pp']
            if pd.isna(delta) or abs(delta) < 0.01:
                txt, cls = '-> estavel 0,00 p.p.', 'status-estavel'
            elif delta > 0:
                txt, cls = f"↑ melhorou {delta:.2f} p.p.".replace('.', ','), 'status-melhorou'
            else:
                txt, cls = f"↓ piorou {abs(delta):.2f} p.p.".replace('.', ','), 'status-piorou'
            st.markdown(f'<div class="section" style="padding:.8rem;"><div style="font-size:.82rem;color:#94a3b8;margin-bottom:.4rem;">Comparacao mes atual vs anterior</div><span class="status-chip {cls}">{txt}</span></div>', unsafe_allow_html=True)
        show_df = monthly_df[['Mes','RFT','Meta','Delta_pp','Acumulado_Ano','Arrow','Status']].copy()
        show_df['RFT'] = show_df['RFT'].map(lambda x: f'{x:.2f}'.replace('.', ',') + '%')
        show_df['Meta'] = show_df['Meta'].map(lambda x: f'{x:.2f}'.replace('.', ',') + '%')
        show_df['Delta_pp'] = show_df['Delta_pp'].map(lambda x: '' if pd.isna(x) else f'{x:+.2f}'.replace('.', ',') + ' p.p.')
        show_df['Acumulado_Ano'] = show_df['Acumulado_Ano'].map(lambda x: f'{x:.2f}'.replace('.', ',') + '%')
        st.dataframe(show_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="section"><div class="section-title">Tendencia semanal</div><div class="section-sub">Leitura do desempenho por semana do ano.</div>', unsafe_allow_html=True)
    if weekly_df.empty:
        st.info('Sem dados semanais disponiveis.')
    else:
        st.bar_chart(weekly_df.set_index('Semana'), use_container_width=True)
        st.dataframe(weekly_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

def upload_overlap_warning(conn, df):
    warnings = []
    if df is None or df.empty: return warnings
    for posto in sorted(df['CD_POSTO_CN'].dropna().unique().tolist()):
        sdf = df[df['CD_POSTO_CN'] == posto]
        for ano in sorted(sdf['DT_HR_INSPECAO'].dt.year.unique().tolist()):
            ydf = sdf[sdf['DT_HR_INSPECAO'].dt.year == ano]
            if ydf.empty: continue
            new_min = ydf['DT_HR_INSPECAO'].dt.date.min(); new_max = ydf['DT_HR_INSPECAO'].dt.date.max()
            old_min, old_max = existing_range_for_posto_year(conn, posto, ano)
            if old_min is None: continue
            overlap_start = max(new_min, old_min); overlap_end = min(new_max, old_max)
            if overlap_start <= overlap_end:
                warnings.append({'posto': posto, 'ano': int(ano), 'texto': f'Este arquivo cobre datas ja existentes entre {overlap_start.strftime("%d/%m")} e {overlap_end.strftime("%d/%m")}.', 'overlap_start': overlap_start, 'overlap_end': overlap_end})
    return warnings

def preview_file_impact(conn, df):
    if df is None or df.empty: return pd.DataFrame(), []
    overlaps = upload_overlap_warning(conn, df); overlap_keys = {(x['posto'], x['ano']) for x in overlaps}; rows = []
    for posto in sorted(df['CD_POSTO_CN'].dropna().unique().tolist()):
        sdf = df[df['CD_POSTO_CN'] == posto]
        for ano in sorted(sdf['DT_HR_INSPECAO'].dt.year.unique().tolist()):
            ydf = sdf[sdf['DT_HR_INSPECAO'].dt.year == ano]
            rows.append({'Posto': posto, 'Ano': int(ano), 'Data minima do arquivo': ydf['DT_HR_INSPECAO'].dt.date.min().strftime('%d/%m/%Y'), 'Data maxima do arquivo': ydf['DT_HR_INSPECAO'].dt.date.max().strftime('%d/%m/%Y'), 'Linhas do arquivo': int(len(ydf)), 'Sobreposicao': 'Sim' if (posto, int(ano)) in overlap_keys else 'Nao'})
    return pd.DataFrame(rows), overlaps

def apply_import_mode(conn, df, mode):
    affected = []
    if df is None or df.empty or mode == 'Somar ao historico': return affected
    for posto in sorted(df['CD_POSTO_CN'].dropna().unique().tolist()):
        sdf = df[df['CD_POSTO_CN'] == posto]
        if mode == 'Substituir periodo sobreposto':
            start_date = sdf['DT_HR_INSPECAO'].dt.date.min(); end_date = sdf['DT_HR_INSPECAO'].dt.date.max()
            delete_overlapped_period(conn, posto, start_date, end_date)
            affected.append(f'{posto}: substituido periodo {start_date.strftime("%d/%m/%Y")} a {end_date.strftime("%d/%m/%Y")}')
        elif mode == 'Reprocessar o ano inteiro':
            for ano in sorted(sdf['DT_HR_INSPECAO'].dt.year.unique().tolist()):
                delete_year_for_posto(conn, posto, int(ano))
                affected.append(f'{posto}: reprocessado ano {ano}')
    return affected

def render_upload(conn):
    st.markdown('<div class="section"><div class="section-title">Atualizar base do sistema</div><div class="section-sub">Modos de importacao e consolidacao para tratar sobreposicao sem perder o historico.</div>', unsafe_allow_html=True)
    import_mode = st.radio('Modo de importacao', ['Somar ao historico', 'Substituir periodo sobreposto', 'Reprocessar o ano inteiro'])
    uploaded = st.file_uploader('Base operacional atual (.xlsx, .xls ou .csv)', type=['xlsx', 'xls', 'csv'])
    prepared = None
    if uploaded is not None:
        try:
            raw = read_file(uploaded)
            ok, miss = validate_df(raw)
            if not ok:
                st.error('Base operacional invalida: ' + ', '.join(miss))
            else:
                prepared = prepare(raw)
                impact_df, overlaps = preview_file_impact(conn, prepared)
                if not impact_df.empty: st.dataframe(impact_df, use_container_width=True, hide_index=True)
                for item in overlaps: st.warning(item['texto'])
        except Exception as err:
            st.error(f'Erro ao analisar a base: {err}')
    if st.button('Salvar arquivo localmente', type='primary', use_container_width=True):
        if uploaded is None or prepared is None:
            st.error('Selecione um arquivo valido antes de salvar.')
            st.stop()
        if prepared.empty:
            st.error('A base foi lida, mas nao restaram linhas validas apos o tratamento.')
            st.stop()
        affected = apply_import_mode(conn, prepared, import_mode)
        uid = create_upload(conn, uploaded.name, len(prepared), message=f'Modo de importacao: {import_mode}.')
        save_raw(conn, uid, prepared)
        final_message = 'Base salva com sucesso.' + (' ' + ' | '.join(affected) if affected else '')
        update_upload(conn, uid, 'PROCESSADO', final_message)
        st.success(final_message)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

def render_history(conn):
    df = uploads_table(conn)
    st.markdown('<div class="section"><div class="section-title">Historico local</div><div class="section-sub">Exclusao, reprocessamento e detalhes do upload selecionado.</div>', unsafe_allow_html=True)
    if df.empty:
        st.info('Os uploads processados aparecerao aqui.')
        st.markdown('</div>', unsafe_allow_html=True)
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    selected_id = st.selectbox('Selecionar upload', df['id'].tolist(), format_func=lambda x: f'Upload {x}')
    selected_info = upload_info(conn, selected_id)
    cols = st.columns(3)
    with cols[0]:
        if st.button('Ver detalhes do upload', use_container_width=True):
            detail = upload_detail_df(conn, selected_id)
            if detail.empty:
                st.warning('Upload sem detalhes disponiveis.')
            else:
                st.markdown(f'<div class="info-box"><b>Arquivo:</b> {selected_info["file_name"] if selected_info else "-"}<br><b>Upload:</b> {selected_info["uploaded_at"] if selected_info else "-"}<br><b>Linhas:</b> {len(detail)}</div>', unsafe_allow_html=True)
                detail_show = detail.copy(); detail_show['DT_HR_INSPECAO'] = detail_show['DT_HR_INSPECAO'].dt.strftime('%d/%m/%Y %H:%M:%S')
                st.dataframe(detail_show.head(200), use_container_width=True, hide_index=True)
    with cols[1]:
        if st.button('Reprocessar upload', use_container_width=True):
            ok = reprocess_upload(conn, selected_id)
            st.success('Upload reprocessado com sucesso.' if ok else 'Nao foi possivel reprocessar o upload.')
            st.rerun()
    with cols[2]:
        if st.button('Excluir upload especifico', use_container_width=True):
            delete_upload(conn, selected_id)
            st.success('Upload excluido com sucesso.')
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

def render_about(meta):
    st.markdown(f'<div class="section"><div class="section-title">Sobre a V7.0</div><div class="section-sub">Versao cloud-safe sem matplotlib, focada em governanca da base e analise gerencial da Qualidade.</div><div class="info-box">Inclui modos de importacao, aviso de sobreposicao, status da base, quantidade de uploads consolidados, acoes de historico, comparacao entre mes anterior e atual, tendencia acumulada no ano e status visual de melhora/piora/estabilidade. Regra visual ativa: valores iguais ou menores que <b>{str(meta).replace(".", ",")}%</b> ficam verdes; valores acima da meta ficam vermelhos.</div></div>', unsafe_allow_html=True)

def main():
    conn = get_conn(); init_db(conn)
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    posto, ano, mode, meta = build_sidebar(conn)
    if ano is None:
        render_empty_state('Base vazia')
        tabs = st.tabs(['Base & Upload', 'Historico', 'Sobre'])
        with tabs[0]: render_upload(conn)
        with tabs[1]: render_history(conn)
        with tabs[2]: render_about(meta)
        return
    latest_upload = latest_upload_id_for_year(conn, posto, ano)
    if latest_upload is None:
        render_empty_state('Sem historico para esse ano/posto', 'Faca um upload na aba Base & Upload para iniciar a analise.')
        tabs = st.tabs(['Base & Upload', 'Historico', 'Sobre'])
        with tabs[0]: render_upload(conn)
        with tabs[1]: render_history(conn)
        with tabs[2]: render_about(meta)
        return
    info = upload_info(conn, latest_upload)
    df = load_merged_year_df(conn, posto, ano)
    if df.empty:
        render_empty_state('Sem linhas validas para o filtro atual', 'Os arquivos salvos nao possuem linhas validas para esse posto/ano.')
        tabs = st.tabs(['Base & Upload', 'Historico', 'Sobre'])
        with tabs[0]: render_upload(conn)
        with tabs[1]: render_history(conn)
        with tabs[2]: render_about(meta)
        return
    ok_ano, status_label = year_status(df, ano)
    min_date, max_date, selected_label, selected_range, valid = resolve_period_selection(df, ano, mode)
    if not valid:
        render_empty_state('Nenhum periodo disponivel para o modo selecionado', 'Altere o modo de visualizacao ou recarregue a base.')
        tabs = st.tabs(['Base & Upload', 'Historico', 'Sobre'])
        with tabs[0]: render_upload(conn)
        with tabs[1]: render_history(conn)
        with tabs[2]: render_about(meta)
        return
    metrics = compute_selected_metrics(df, ano, mode, selected_range, ok_ano, max_date)
    base_summary = summarize_base(df, conn, posto, ano)
    tabs = st.tabs(['Dashboard', 'Tendencia', 'Base & Upload', 'Historico', 'Sobre'])
    with tabs[0]: render_dashboard(df, metrics, selected_label, info, posto, ano, status_label, meta, base_summary)
    with tabs[1]: render_tendencia(df, ano, meta)
    with tabs[2]: render_upload(conn)
    with tabs[3]: render_history(conn)
    with tabs[4]: render_about(meta)

if __name__ == '__main__':
    main()
