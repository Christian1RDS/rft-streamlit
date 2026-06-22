
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

st.set_page_config(page_title='RFT Automatico - V6.2', page_icon='R', layout='wide', initial_sidebar_state='expanded')

DB = 'rft_v61_local.db'
REQ = ['NR_WO', 'DT_HR_INSPECAO', 'C_DPU_QG_AMARELO', 'CD_POSTO_CN']
POSTOS = ['QG09', 'QG07']
POSTO_PADRAO = 'QG09'
LS_PREFIX = 'rft_v62_'
DEFAULT_META_RFT = 95.0
CUTOFF_MONTH = 12
CUTOFF_DAY = 12

CUSTOM_CSS = '''
<style>
:root {
  --bg:#0f172a; --bg2:#111827; --panel:#182235; --card:#1f2a3d; --border:rgba(148,163,184,.18);
  --text:#e5e7eb; --muted:#94a3b8; --green:#22c55e; --red:#ef4444;
}
html, body, [data-testid="stAppViewContainer"], .stApp { background: linear-gradient(180deg,#0b1220 0%,#0f172a 100%); color:var(--text); }
[data-testid="stHeader"] { background: rgba(15,23,42,.75); border-bottom:1px solid var(--border); }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#0c1527 0%,#121d31 100%); border-right:1px solid var(--border); }
[data-testid="stSidebar"] * { color: var(--text) !important; }
.block-container { padding-top:1.2rem; padding-bottom:2rem; }
h1,h2,h3,h4,h5,h6,label,p,div,span { color:var(--text); }
.hero { background:linear-gradient(135deg,rgba(24,34,53,.95),rgba(16,24,40,.98)); border:1px solid var(--border); border-radius:22px; padding:1.2rem 1.3rem; margin-bottom:1rem; }
.hero-title { font-size:1.7rem; font-weight:700; margin-bottom:.2rem; }
.hero-sub { color:var(--muted); font-size:.95rem; }
.section { background:linear-gradient(180deg,rgba(28,37,55,.96),rgba(18,27,41,.98)); border:1px solid var(--border); border-radius:18px; padding:1rem; margin-bottom:1rem; }
.metric-card { border:1px solid var(--border); background:linear-gradient(180deg,rgba(31,42,61,.96),rgba(22,31,47,.98)); border-radius:18px; padding:1rem; min-height:150px; }
.metric-title { color:var(--muted); font-size:.9rem; margin-bottom:.5rem; }
.metric-value { font-size:1.9rem; font-weight:800; margin-bottom:.35rem; }
.metric-meta { color:var(--muted); font-size:.82rem; line-height:1.35; }
.ok { color:var(--green); } .bad { color:var(--red); } .neutral { color:var(--text); }
.note { background:rgba(59,130,246,.08); border:1px dashed rgba(59,130,246,.35); border-radius:16px; padding:.9rem 1rem; }
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
    conn.execute('UPDATE upload_log SET status=?, message=? WHERE id=?', (status, message, upload_id))
    conn.commit()


def save_raw(conn, upload_id, df):
    rows = []
    for _, row in df.iterrows():
        rows.append((int(upload_id), row['NR_WO'], row['DT_HR_INSPECAO'].isoformat(sep=' ', timespec='seconds'), float(row['C_DPU_QG_AMARELO']), row['CD_POSTO_CN']))
    conn.executemany('INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn) VALUES (?, ?, ?, ?, ?)', rows)
    conn.commit()


def uploads_table(conn):
    return pd.read_sql_query('SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC LIMIT 300', conn)


def latest_upload_id_for_year(conn, posto, year):
    df = pd.read_sql_query("SELECT MAX(upload_id) AS upload_id FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", conn, params=[posto, str(year)])
    if df.empty or pd.isna(df.loc[0, 'upload_id']):
        return None
    return int(df.loc[0, 'upload_id'])


def upload_info(conn, upload_id):
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM upload_log WHERE id=?', (upload_id,)).fetchone()
    conn.row_factory = None
    return row


def available_years(conn, posto):
    df = pd.read_sql_query("SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano FROM raw_inspections WHERE cd_posto_cn=? ORDER BY ano", conn, params=[posto])
    return [int(x) for x in df['ano'].dropna().tolist()] if not df.empty else []


def normalize_columns(df):
    df = df.copy()
    df.columns = [str(x).strip().replace('﻿', '') for x in df.columns]
    return df


def read_file(uploaded_file):
    ext = uploaded_file.name.lower().split('.')[-1]
    content = uploaded_file.getvalue()
    if ext == 'csv':
        last_err = None
        for enc in ['utf-8-sig', 'utf-16', 'latin1']:
            for sep in [None, ';', ',', '	']:
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
    missing = [col for col in REQ if col not in df.columns]
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
    work = df.copy()
    work['DT_HR_INSPECAO'] = parse_dt(work['DT_HR_INSPECAO'])
    work['C_DPU_QG_AMARELO'] = pd.to_numeric(work['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    work['NR_WO'] = work['NR_WO'].astype(str).str.strip()
    work['CD_POSTO_CN'] = work['CD_POSTO_CN'].astype(str).map(norm_posto)
    return work[work['DT_HR_INSPECAO'].notna()].copy()


def load_merged_year_df(conn, posto, year):
    df = pd.read_sql_query("SELECT upload_id, nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=? ORDER BY upload_id ASC, id ASC", conn, params=[posto, str(year)])
    if df.empty:
        return df
    df['DT_HR_INSPECAO'] = pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
    df['C_DPU_QG_AMARELO'] = pd.to_numeric(df['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    df['CD_POSTO_CN'] = df['CD_POSTO_CN'].astype(str).map(norm_posto)
    df['NR_WO'] = df['NR_WO'].astype(str).str.strip()
    df = df[df['DT_HR_INSPECAO'].notna()].copy()
    return df.drop_duplicates(subset=['NR_WO', 'DT_HR_INSPECAO', 'CD_POSTO_CN'], keep='last').reset_index(drop=True)


def calc_rft(df, start_date, end_date):
    sdt = datetime.combine(start_date, time(0, 0, 0))
    edt = datetime.combine(end_date, time(23, 59, 59))
    filt = df[(df['DT_HR_INSPECAO'] >= sdt) & (df['DT_HR_INSPECAO'] <= edt)].copy()
    if filt.empty:
        return {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0}
    grp = filt.groupby('NR_WO', as_index=False)['C_DPU_QG_AMARELO'].sum().rename(columns={'C_DPU_QG_AMARELO': 'SOMA'})
    grp['RFT'] = (grp['SOMA'] == 0).astype(int)
    total = int(len(grp))
    good = int(grp['RFT'].sum())
    bad = int(total - good)
    pct = round((good / total) * 100, 2) if total else None
    return {'rft_pct': pct, 'total': total, 'good': good, 'bad': bad}


def year_status(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year]
    if ydf.empty:
        return False, 'Sem dados'
    max_d = ydf['DT_HR_INSPECAO'].dt.date.max()
    cutoff = date(year, CUTOFF_MONTH, CUTOFF_DAY)
    return (max_d >= cutoff), ('Fechado em 12/12' if max_d >= cutoff else 'Ate ' + max_d.strftime('%d/%m/%Y'))


def week_options(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return []
    dates = sorted(ydf['DT_HR_INSPECAO'].dt.date.unique().tolist())
    mondays = sorted({d - timedelta(days=d.weekday()) for d in dates})
    opts = []
    for idx, monday in enumerate(mondays, start=1):
        sunday = monday + timedelta(days=6)
        opts.append((f'Semana {idx:02d} - {monday.strftime("%d/%m/%Y")} a {sunday.strftime("%d/%m/%Y")}', monday, sunday))
    return opts


def month_options(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return []
    opts = []
    for month in sorted(ydf['DT_HR_INSPECAO'].dt.month.unique().tolist()):
        start = date(year, int(month), 1)
        end = date(year, int(month), monthrange(year, int(month))[1])
        opts.append((f'{start.strftime("%m/%Y")} - {start.strftime("%d/%m/%Y")} a {end.strftime("%d/%m/%Y")}', start, end))
    return opts


def status_class(value):
    meta = current_meta()
    if value is None or pd.isna(value):
        return 'neutral'
    return 'ok' if value <= meta else 'bad'


def metric_card(title, result, subtitle=''):
    if result is None:
        value = 'Sem dados'
        css = 'neutral'
        meta_text = subtitle
    else:
        value = f"{result['rft_pct']:.2f}".replace('.', ',') + '%'
        css = status_class(result['rft_pct'])
        meta_text = f"{subtitle}<br>WOs boas: {result['good']} | ruins: {result['bad']} | total: {result['total']}"
    return f'<div class="metric-card"><div class="metric-title">{title}</div><div class="metric-value {css}">{value}</div><div class="metric-meta">{meta_text}</div></div>'


def render_empty_state(message, subtitle='Adicione um arquivo na aba Base & Upload para iniciar o historico visual.'):
    st.markdown(f'<div class="section"><div style="font-weight:700;margin-bottom:.35rem;">{message}</div><div style="color:#94a3b8;">{subtitle}</div></div>', unsafe_allow_html=True)


def build_sidebar(conn):
    with st.sidebar:
        st.markdown('### Controles de analise')
        st.caption('Filtros persistidos localmente.')
        default_posto = ls_get('posto', POSTO_PADRAO)
        posto_idx = POSTOS.index(default_posto) if default_posto in POSTOS else 0
        posto = st.radio('Posto', POSTOS, index=posto_idx, horizontal=True)
        ls_set('posto', posto)
        anos = available_years(conn, posto)
        if anos:
            prev_year = ls_get('ano', None)
            try:
                prev_year = int(prev_year) if prev_year is not None else None
            except Exception:
                prev_year = None
            ano_idx = anos.index(prev_year) if prev_year in anos else len(anos) - 1
            ano = st.selectbox('Ano', anos, index=ano_idx)
            ls_set('ano', ano)
        else:
            ano = None
            st.info('Sem dados salvos para este posto.')
        modes = ['Diario', 'Semanal', 'Mensal', 'Anual']
        default_mode = ls_get('modo', 'Diario')
        mode_idx = modes.index(default_mode) if default_mode in modes else 0
        mode = st.radio('Modo', modes, index=mode_idx)
        ls_set('modo', mode)
        st.markdown('---')
        saved_meta = ls_get('meta_rft', DEFAULT_META_RFT)
        try:
            saved_meta = float(str(saved_meta).replace(',', '.'))
        except Exception:
            saved_meta = DEFAULT_META_RFT
        meta = st.number_input('Meta RFT (%)', min_value=0.0, max_value=100.0, value=float(saved_meta), step=0.1)
        st.session_state['meta_rft'] = float(meta)
        ls_set('meta_rft', meta)
        st.caption('Regra visual')
        st.write('RFT <= meta = verde')
        st.write('RFT > meta = vermelho')
    return posto, ano, mode, float(meta)


def resolve_period_selection(df, ano, mode):
    min_date = df['DT_HR_INSPECAO'].dt.date.min()
    max_date = df['DT_HR_INSPECAO'].dt.date.max()
    selected_label = f'Ano {ano}'
    selected_range = (date(ano, 1, 1), min(max_date, date(ano, 12, 12)))
    if mode == 'Diario':
        saved_day = ls_get('dia', '')
        try:
            default_day = datetime.fromisoformat(saved_day).date() if saved_day else max_date
        except Exception:
            default_day = max_date
        if default_day < min_date or default_day > max_date:
            default_day = max_date
        selected = st.sidebar.date_input('Dia', value=default_day, min_value=min_date, max_value=max_date, format='DD/MM/YYYY')
        ls_set('dia', selected.isoformat())
        selected_label = selected.strftime('%d/%m/%Y')
        selected_range = (selected, selected)
    elif mode == 'Semanal':
        opts = week_options(df, ano)
        labels = [x[0] for x in opts]
        if not labels:
            return min_date, max_date, selected_label, selected_range, False
        saved = ls_get('semana_label', '')
        idx = labels.index(saved) if saved in labels else len(labels) - 1
        label = st.sidebar.selectbox('Semana do ano', labels, index=idx)
        ls_set('semana_label', label)
        found = next(x for x in opts if x[0] == label)
        selected_label = label
        selected_range = (found[1], found[2])
    elif mode == 'Mensal':
        opts = month_options(df, ano)
        labels = [x[0] for x in opts]
        if not labels:
            return min_date, max_date, selected_label, selected_range, False
        saved = ls_get('mes_label', '')
        idx = labels.index(saved) if saved in labels else len(labels) - 1
        label = st.sidebar.selectbox('Mes do ano', labels, index=idx)
        ls_set('mes_label', label)
        found = next(x for x in opts if x[0] == label)
        selected_label = label
        selected_range = (found[1], found[2])
    return min_date, max_date, selected_label, selected_range, True


def compute_selected_metrics(df, ano, mode, selected_range, ok_ano, max_date):
    daily = weekly = monthly = yearly = ytd = None
    start, end = selected_range
    if mode == 'Diario':
        selected = start
        daily = calc_rft(df, selected, selected)
        ws = selected - timedelta(days=selected.weekday())
        we = ws + timedelta(days=6)
        weekly = calc_rft(df, ws, we)
        ms = date(ano, selected.month, 1)
        me = date(ano, selected.month, monthrange(ano, selected.month)[1])
        monthly = calc_rft(df, ms, me)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok_ano else None
        ytd = calc_rft(df, date(ano, 1, 1), selected)
    elif mode == 'Semanal':
        ws, we = start, end
        weekly = calc_rft(df, ws, we)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok_ano else None
        ytd = calc_rft(df, date(ano, 1, 1), min(we, max_date))
    elif mode == 'Mensal':
        ms, me = start, end
        monthly = calc_rft(df, ms, me)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok_ano else None
        ytd = calc_rft(df, date(ano, 1, 1), min(me, max_date))
    else:
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok_ano else None
        ytd = calc_rft(df, date(ano, 1, 1), min(max_date, date(ano, 12, 12)))
    return {'daily': daily, 'weekly': weekly, 'monthly': monthly, 'yearly': yearly, 'ytd': ytd}


def monthly_trend(df, year, meta):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return pd.DataFrame(columns=['Mes', 'RFT', 'Meta'])
    rows = []
    for month in sorted(ydf['DT_HR_INSPECAO'].dt.month.unique().tolist()):
        start = date(year, int(month), 1)
        end = date(year, int(month), monthrange(year, int(month))[1])
        res = calc_rft(ydf, start, end)
        rows.append({'Mes': start.strftime('%m/%Y'), 'RFT': res['rft_pct'] or 0, 'Meta': meta})
    return pd.DataFrame(rows)


def weekly_trend(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return pd.DataFrame(columns=['Semana', 'RFT'])
    rows = []
    for label, ws, we in week_options(ydf, year):
        res = calc_rft(ydf, ws, we)
        rows.append({'Semana': label.split('-')[0].strip(), 'RFT': res['rft_pct'] or 0})
    return pd.DataFrame(rows)


def day_trend_table(df):
    if df.empty:
        return pd.DataFrame(columns=['Dia', 'RFT'])
    rows = []
    for d in sorted(df['DT_HR_INSPECAO'].dt.date.unique().tolist()):
        res = calc_rft(df, d, d)
        rows.append({'Dia': d.strftime('%d/%m/%Y'), 'RFT': res['rft_pct'] or 0})
    return pd.DataFrame(rows)


def render_dashboard(df, metrics, selected_label, info, posto, ano, min_date, max_date, status_label, meta):
    file_name = info['file_name'] if info else '-'
    uploaded_at = info['uploaded_at'] if info else '-'
    st.markdown(f'<div class="hero"><div class="hero-title">RFT Automatico - V6.2</div><div class="hero-sub">Painel corporativo com meta configuravel, tendencia e consolidacao de multiplos uploads sem perder o historico anterior.</div><div style="margin-top:.85rem;color:#94a3b8;">Posto: <b>{posto}</b> | Ano: <b>{ano}</b> | Meta: <b>{str(meta).replace(".", ",")}%</b> | Fechamento: <b>{status_label}</b><br>Ultimo arquivo: <b>{file_name}</b> | Ultimo upload: <b>{uploaded_at}</b> | Janela consolidada: <b>{min_date.strftime("%d/%m/%Y")} ate {max_date.strftime("%d/%m/%Y")}</b> | Linhas consolidadas: <b>{len(df)}</b></div></div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(metric_card('RFT Diario', metrics['daily'], 'Leitura do dia selecionado'), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card('RFT Semanal', metrics['weekly'], 'Consolidacao semanal'), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card('RFT Mensal', metrics['monthly'], 'Consolidacao mensal'), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card('RFT Anual', metrics['yearly'], 'Ano ate 12/12'), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card('RFT YTD', metrics['ytd'], 'Acumulado ate o recorte'), unsafe_allow_html=True)
    left, right = st.columns([1.25, 1])
    with left:
        st.markdown(f'<div class="section"><div style="font-weight:700;margin-bottom:.35rem;">Resumo executivo do recorte</div><div style="color:#94a3b8;">Recorte: {selected_label}<br>Ultimo arquivo salvo: {file_name}<br>Ultimo upload: {uploaded_at}<br>Posto: {posto}<br>Ano: {ano}<br>Janela consolidada: {min_date.strftime("%d/%m/%Y")} ate {max_date.strftime("%d/%m/%Y")}<br>Meta ativa: {str(meta).replace(".", ",")}%</div></div>', unsafe_allow_html=True)
    with right:
        current = metrics['ytd'] if metrics['ytd'] is not None else metrics['monthly']
        current_pct = None if current is None else current['rft_pct']
        diff = 'Sem dados' if current_pct is None else f"{(current_pct - meta):+.2f}".replace('.', ',') + ' p.p.'
        color = 'ok' if (current_pct is not None and current_pct <= meta) else ('bad' if current_pct is not None else 'neutral')
        current_text = 'Sem dados' if current_pct is None else f"{current_pct:.2f}".replace('.', ',') + '%'
        st.markdown(f'<div class="section"><div style="font-weight:700;margin-bottom:.35rem;">Meta x resultado</div><div style="color:#94a3b8;margin-bottom:.8rem;">Regra visual aplicada conforme sua configuracao.</div><div class="metric-value {color}">{current_text}</div><div style="color:#94a3b8;">Meta: {str(meta).replace(".", ",")}%<br>Diferenca: {diff}<br>Regra: RFT <= meta fica verde | RFT > meta fica vermelho</div></div>', unsafe_allow_html=True)
    day_df = day_trend_table(df)
    if not day_df.empty:
        st.markdown('<div class="section"><div style="font-weight:700;margin-bottom:.35rem;">Leitura diaria do RFT</div><div style="color:#94a3b8;margin-bottom:.8rem;">Historico dia a dia dentro da base consolidada.</div>', unsafe_allow_html=True)
        st.line_chart(day_df.set_index('Dia'))
        st.markdown('</div>', unsafe_allow_html=True)


def render_tendencia(df, ano, meta):
    c1, c2 = st.columns(2)
    monthly_df = monthly_trend(df, ano, meta)
    weekly_df = weekly_trend(df, ano)
    with c1:
        st.markdown('<div class="section"><div style="font-weight:700;margin-bottom:.35rem;">Tendencia mensal</div><div style="color:#94a3b8;margin-bottom:.8rem;">Consolidacao do RFT por mes com a meta ativa em paralelo.</div>', unsafe_allow_html=True)
        if monthly_df.empty:
            st.info('Sem dados mensais disponiveis.')
        else:
            st.line_chart(monthly_df.set_index('Mes')[['RFT', 'Meta']])
            st.dataframe(monthly_df, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="section"><div style="font-weight:700;margin-bottom:.35rem;">Tendencia semanal</div><div style="color:#94a3b8;margin-bottom:.8rem;">Leitura do desempenho por semana do ano.</div>', unsafe_allow_html=True)
        if weekly_df.empty:
            st.info('Sem dados semanais disponiveis.')
        else:
            st.bar_chart(weekly_df.set_index('Semana'))
            st.dataframe(weekly_df, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)


def render_upload(conn):
    st.markdown('<div class="section"><div style="font-weight:700;margin-bottom:.35rem;">Atualizar base do sistema</div><div style="color:#94a3b8;margin-bottom:.8rem;">Carregue uma base operacional para salvar o historico local e consolidar os dados sem apagar os uploads anteriores.</div><div class="note">Arquivos sobrepostos sao preservados. Quando existirem registros repetidos pela mesma WO + data/hora + posto, o sistema mantem o registro mais recente.</div><div style="height:10px"></div>', unsafe_allow_html=True)
    uploaded = st.file_uploader('Base operacional atual (.xlsx, .xls ou .csv)', type=['xlsx', 'xls', 'csv'])
    if st.button('Salvar arquivo localmente', type='primary', use_container_width=True):
        if uploaded is None:
            st.error('Selecione um arquivo antes de salvar.')
            st.stop()
        try:
            raw = read_file(uploaded)
            ok, miss = validate_df(raw)
            if not ok:
                st.error('Base operacional invalida: ' + ', '.join(miss))
                st.stop()
            df = prepare(raw)
            if df.empty:
                st.error('A base foi lida, mas nao restaram linhas validas apos o tratamento.')
                st.stop()
        except Exception as err:
            st.error(f'Erro ao ler a base operacional: {err}')
            st.stop()
        uid = create_upload(conn, uploaded.name, len(df), message='Base recebida e salva localmente.')
        try:
            save_raw(conn, uid, df)
            update_upload(conn, uid, 'PROCESSADO', 'Base salva com sucesso.')
            st.success('Arquivo salvo com sucesso. O historico foi preservado e a consolidacao sera atualizada automaticamente.')
            st.rerun()
        except Exception as err:
            update_upload(conn, uid, 'ERRO', str(err))
            st.error(f'Erro ao salvar a base: {err}')
    st.markdown('</div>', unsafe_allow_html=True)


def render_history(conn):
    df = uploads_table(conn)
    st.markdown('<div class="section"><div style="font-weight:700;margin-bottom:.35rem;">Historico local</div><div style="color:#94a3b8;margin-bottom:.8rem;">Uploads processados e status de tratamento da base.</div>', unsafe_allow_html=True)
    if df.empty:
        st.info('Os uploads processados aparecerao aqui.')
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


def render_about(meta):
    st.markdown(f'<div class="section"><div style="font-weight:700;margin-bottom:.35rem;">Sobre a V6.2</div><div style="color:#94a3b8;margin-bottom:.8rem;">Refinamento da versao com foco em meta configuravel, preservacao do historico e layout mais orientado a gestao.</div><div class="note">Visual corporativo escuro. Meta de RFT configuravel diretamente na sidebar. Regra visual aplicada conforme solicitado: valores iguais ou menores que <b>{str(meta).replace(".", ",")}%</b> ficam verdes; valores acima da meta ficam vermelhos. A aba Operacional foi removida e a aba Tendencia foi mantida.</div></div>', unsafe_allow_html=True)


def main():
    conn = get_conn()
    init_db(conn)
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    posto, ano, mode, meta = build_sidebar(conn)
    if ano is None:
        render_empty_state('Base vazia')
        tabs = st.tabs(['Base & Upload', 'Historico', 'Sobre'])
        with tabs[0]:
            render_upload(conn)
        with tabs[1]:
            render_history(conn)
        with tabs[2]:
            render_about(meta)
        return
    latest_upload_id = latest_upload_id_for_year(conn, posto, ano)
    if latest_upload_id is None:
        render_empty_state('Sem historico para esse ano/posto', 'Faca um upload na aba Base & Upload para iniciar a analise.')
        tabs = st.tabs(['Base & Upload', 'Historico', 'Sobre'])
        with tabs[0]:
            render_upload(conn)
        with tabs[1]:
            render_history(conn)
        with tabs[2]:
            render_about(meta)
        return
    info = upload_info(conn, latest_upload_id)
    df = load_merged_year_df(conn, posto, ano)
    if df.empty:
        render_empty_state('Sem linhas validas para o filtro atual', 'Os arquivos salvos nao possuem linhas validas para esse posto/ano.')
        tabs = st.tabs(['Base & Upload', 'Historico', 'Sobre'])
        with tabs[0]:
            render_upload(conn)
        with tabs[1]:
            render_history(conn)
        with tabs[2]:
            render_about(meta)
        return
    ok_ano, status_label = year_status(df, ano)
    min_date, max_date, selected_label, selected_range, valid_selection = resolve_period_selection(df, ano, mode)
    if not valid_selection:
        render_empty_state('Nenhum periodo disponivel para o modo selecionado', 'Altere o modo de visualizacao ou recarregue a base.')
        tabs = st.tabs(['Base & Upload', 'Historico', 'Sobre'])
        with tabs[0]:
            render_upload(conn)
        with tabs[1]:
            render_history(conn)
        with tabs[2]:
            render_about(meta)
        return
    metrics = compute_selected_metrics(df, ano, mode, selected_range, ok_ano, max_date)
    tabs = st.tabs(['Dashboard', 'Tendencia', 'Base & Upload', 'Historico', 'Sobre'])
    with tabs[0]:
        render_dashboard(df, metrics, selected_label, info, posto, ano, min_date, max_date, status_label, meta)
    with tabs[1]:
        render_tendencia(df, ano, meta)
    with tabs[2]:
        render_upload(conn)
    with tabs[3]:
        render_history(conn)
    with tabs[4]:
        render_about(meta)

if __name__ == '__main__':
    main()
