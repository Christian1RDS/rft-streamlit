
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

st.set_page_config(page_title='RFT Qualidade - V7.6', page_icon='Q', layout='wide', initial_sidebar_state='expanded')

DB = 'rft_v61_local.db'
REQ = ['NR_WO', 'DT_HR_INSPECAO', 'C_DPU_QG_AMARELO', 'CD_POSTO_CN']
POSTOS = ['QG09', 'QG07']
POSTO_PADRAO = 'QG09'
LS_PREFIX = 'rft_v76_'
DEFAULT_META_RFT = 95.0
CUTOFF_MONTH = 12
CUTOFF_DAY = 12

# -------------------- local storage --------------------
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

# -------------------- database --------------------
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


def detail_upload_df(conn, upload_id):
    df = pd.read_sql_query(
        'SELECT nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE upload_id=? ORDER BY dt_hr_inspecao, nr_wo',
        conn,
        params=[int(upload_id)],
    )
    if not df.empty:
        df['DT_HR_INSPECAO'] = pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
    return df


def delete_upload(conn, upload_id):
    conn.execute('DELETE FROM raw_inspections WHERE upload_id=?', (int(upload_id),))
    conn.execute('DELETE FROM upload_log WHERE id=?', (int(upload_id),))
    conn.commit()


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

# -------------------- parse / prepare --------------------
def normalize_columns(df):
    out = df.copy()
    out.columns = [str(x).strip().replace('﻿', '') for x in out.columns]
    return out


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
    missing = [c for c in REQ if c not in df.columns]
    return len(missing) == 0, missing


def parse_dt(series):
    dt = pd.to_datetime(series, errors='coerce')
    mask = dt.isna() & series.notna()
    if mask.any():
        dt.loc[mask] = pd.to_datetime(series[mask], errors='coerce', dayfirst=True)
    return dt


def norm_posto(v):
    txt = str(v).upper().strip()
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

# -------------------- consolidated data helpers --------------------
def available_years(conn, posto):
    df = pd.read_sql_query("SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano FROM raw_inspections WHERE cd_posto_cn=? ORDER BY ano", conn, params=[posto])
    return [int(x) for x in df['ano'].dropna().tolist()] if not df.empty else []


def latest_upload_id_for_year(conn, posto, year):
    df = pd.read_sql_query("SELECT MAX(upload_id) AS upload_id FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", conn, params=[posto, str(year)])
    if df.empty or pd.isna(df.loc[0, 'upload_id']):
        return None
    return int(df.loc[0, 'upload_id'])


def existing_range_for_posto_year(conn, posto, year):
    df = pd.read_sql_query("SELECT MIN(date(dt_hr_inspecao)) AS min_d, MAX(date(dt_hr_inspecao)) AS max_d FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", conn, params=[posto, str(year)])
    if df.empty or pd.isna(df.loc[0, 'min_d']):
        return None, None
    return pd.to_datetime(df.loc[0, 'min_d']).date(), pd.to_datetime(df.loc[0, 'max_d']).date()


def count_uploads_for_posto_year(conn, posto, year):
    df = pd.read_sql_query("SELECT COUNT(DISTINCT upload_id) AS qtd FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", conn, params=[posto, str(year)])
    return int(df.loc[0, 'qtd']) if not df.empty and not pd.isna(df.loc[0, 'qtd']) else 0


def delete_overlapped_period(conn, posto, year, start_date, end_date):
    conn.execute(
        "DELETE FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=? AND datetime(dt_hr_inspecao) BETWEEN datetime(?) AND datetime(?)",
        (posto, str(year), datetime.combine(start_date, time(0,0,0)).isoformat(sep=' '), datetime.combine(end_date, time(23,59,59)).isoformat(sep=' ')),
    )
    conn.commit()


def delete_year_for_posto(conn, posto, year):
    conn.execute("DELETE FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", (posto, str(year)))
    conn.commit()


def upload_overlap_warning(conn, df):
    warnings = []
    if df is None or df.empty:
        return warnings
    for (year, posto), part in df.groupby([df['DT_HR_INSPECAO'].dt.year, 'CD_POSTO_CN']):
        new_min = part['DT_HR_INSPECAO'].dt.date.min()
        new_max = part['DT_HR_INSPECAO'].dt.date.max()
        old_min, old_max = existing_range_for_posto_year(conn, posto, int(year))
        if old_min is None:
            continue
        overlap_start = max(new_min, old_min)
        overlap_end = min(new_max, old_max)
        if overlap_start <= overlap_end:
            warnings.append({'texto': f'Este arquivo cobre datas ja existentes entre {overlap_start.strftime("%d/%m")} e {overlap_end.strftime("%d/%m")}.', 'posto': posto, 'ano': int(year)})
    return warnings


def preview_file_impact(conn, df):
    if df is None or df.empty:
        return pd.DataFrame(), []
    overlaps = upload_overlap_warning(conn, df)
    overlap_keys = {(x['posto'], x['ano']) for x in overlaps}
    rows = []
    for (year, posto), part in df.groupby([df['DT_HR_INSPECAO'].dt.year, 'CD_POSTO_CN']):
        rows.append({
            'Posto': posto,
            'Ano': int(year),
            'Data minima do arquivo': part['DT_HR_INSPECAO'].dt.date.min().strftime('%d/%m/%Y'),
            'Data maxima do arquivo': part['DT_HR_INSPECAO'].dt.date.max().strftime('%d/%m/%Y'),
            'Linhas do arquivo': int(len(part)),
            'Sobreposicao': 'Sim' if (posto, int(year)) in overlap_keys else 'Nao',
        })
    return pd.DataFrame(rows), overlaps


def apply_import_mode(conn, df, mode):
    affected = []
    if df is None or df.empty or mode == 'Somar ao historico':
        return affected
    for (year, posto), part in df.groupby([df['DT_HR_INSPECAO'].dt.year, 'CD_POSTO_CN']):
        if mode == 'Substituir periodo sobreposto':
            start_date = part['DT_HR_INSPECAO'].dt.date.min()
            end_date = part['DT_HR_INSPECAO'].dt.date.max()
            delete_overlapped_period(conn, posto, int(year), start_date, end_date)
            affected.append(f'{posto}/{year}: substituido periodo {start_date.strftime("%d/%m/%Y")} a {end_date.strftime("%d/%m/%Y")}')
        elif mode == 'Reprocessar o ano inteiro':
            delete_year_for_posto(conn, posto, int(year))
            affected.append(f'{posto}/{year}: reprocessado ano inteiro')
    return affected


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


def load_merged_all_df(conn, posto):
    df = pd.read_sql_query("SELECT id, upload_id, nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE cd_posto_cn=? ORDER BY upload_id ASC, id ASC", conn, params=[posto])
    if df.empty:
        return df
    df['DT_HR_INSPECAO'] = pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
    df['C_DPU_QG_AMARELO'] = pd.to_numeric(df['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    df['CD_POSTO_CN'] = df['CD_POSTO_CN'].astype(str).map(norm_posto)
    df['NR_WO'] = df['NR_WO'].astype(str).str.strip()
    df = df[df['DT_HR_INSPECAO'].notna()].copy()
    return df.drop_duplicates(subset=['NR_WO', 'DT_HR_INSPECAO', 'CD_POSTO_CN'], keep='last').reset_index(drop=True)

# -------------------- KPI calculations --------------------
def calc_rft(df, start_date, end_date):
    sdt = datetime.combine(start_date, time(0,0,0))
    edt = datetime.combine(end_date, time(23,59,59))
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
        empty = pd.DataFrame(columns=['Mes','Produzidos','Nao_Defeituosos','RFT'])
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
    rows = []
    total_prod = 0
    total_good = 0
    for ms in months:
        me = date(ms.year, ms.month, monthrange(ms.year, ms.month)[1])
        res = calc_rft(df, ms, me)
        rows.append({'Mes': ms.strftime('%m/%Y'), 'Produzidos': res['total'], 'Nao_Defeituosos': res['good'], 'RFT': res['rft_pct']})
        total_prod += res['total']
        total_good += res['good']
    bad = total_prod - total_good
    pct = round((total_good / total_prod) * 100, 2) if total_prod else None
    return {'rft_pct': pct, 'total': total_prod, 'good': total_good, 'bad': bad}, pd.DataFrame(rows)


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
    return [(f'Semana {i:02d} - {m.strftime("%d/%m/%Y")} a {(m + timedelta(days=6)).strftime("%d/%m/%Y")}', m, m + timedelta(days=6)) for i, m in enumerate(mondays, start=1)]


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
        selected = st.sidebar.date_input('Dia', value=default_day, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='day_v75')
        ls_set('dia', selected.isoformat())
        selected_label = selected.strftime('%d/%m/%Y')
        selected_range = (selected, selected)
    elif mode == 'Semanal':
        opts = week_options(df, ano)
        labels = [x[0] for x in opts]
        if not labels:
            return min_date, max_date, selected_label, selected_range, False
        saved = ls_get('semana_label', '')
        idx = labels.index(saved) if saved in labels else len(labels)-1
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
        idx = labels.index(saved) if saved in labels else len(labels)-1
        label = st.sidebar.selectbox('Mes do ano', labels, index=idx)
        ls_set('mes_label', label)
        found = next(x for x in opts if x[0] == label)
        selected_label = label
        selected_range = (found[1], found[2])
    return min_date, max_date, selected_label, selected_range, True


def compute_rft_cards(df, ano, mode, selected_range, ok_ano, max_date):
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
        yearly = calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None
        ytd = calc_rft(df, date(ano,1,1), selected)
    elif mode == 'Semanal':
        ws, we = start, end
        weekly = calc_rft(df, ws, we)
        yearly = calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None
        ytd = calc_rft(df, date(ano,1,1), min(we, max_date))
    elif mode == 'Mensal':
        ms, me = start, end
        monthly = calc_rft(df, ms, me)
        yearly = calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None
        ytd = calc_rft(df, date(ano,1,1), min(me, max_date))
    else:
        yearly = calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None
        ytd = calc_rft(df, date(ano,1,1), min(max_date, date(ano,12,12)))
    return {'daily': daily, 'weekly': weekly, 'monthly': monthly, 'yearly': yearly, 'ytd': ytd}


def monthly_trend(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return pd.DataFrame(columns=['Mes','RFT'])
    rows = []
    for month in sorted(ydf['DT_HR_INSPECAO'].dt.month.unique().tolist()):
        start = date(year, int(month), 1)
        end = date(year, int(month), monthrange(year, int(month))[1])
        rows.append({'Mes': start.strftime('%m/%Y'), 'RFT': calc_rft(ydf, start, end)['rft_pct'] or 0})
    return pd.DataFrame(rows)


def weekly_trend(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return pd.DataFrame(columns=['Semana','RFT'])
    rows = []
    for label, ws, we in week_options(ydf, year):
        rows.append({'Semana': label.split('-')[0].strip(), 'RFT': calc_rft(ydf, ws, we)['rft_pct'] or 0})
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
    return {'min_date': min_d, 'max_date': max_d, 'last_date': max_d, 'days_covered': int(df['DT_HR_INSPECAO'].dt.date.nunique()) if not df.empty else 0, 'uploads_count': uploads_count, 'status': status, 'status_cls': status_cls}

# -------------------- UI helpers --------------------
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
    return f'<div class="card"><div class="muted">{title}</div><div style="font-size:1.9rem;font-weight:800;" class="{css}">{value}</div><div class="muted">{meta_text}</div></div>'


def kv_html(label, value):
    return f'<div class="kv"><div class="muted">{label}</div><div><strong>{value}</strong></div></div>'

# -------------------- Main app --------------------
def main():
    conn = get_conn()
    init_db(conn)

    st.markdown("### Qualidade | RFT Automatico - V7.5")
    st.caption('RFT completo das versões anteriores + Rolling 12 separado, com calendário e tendências restaurados.')

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

        modes = ['Diario', 'Semanal', 'Mensal', 'Anual']
        default_mode = ls_get('modo', 'Diario')
        mode = st.radio('Modo de visualização', modes, index=modes.index(default_mode) if default_mode in modes else 0)
        ls_set('modo', mode)

        saved_meta = ls_get('meta_rft', DEFAULT_META_RFT)
        try:
            saved_meta = float(str(saved_meta).replace(',', '.'))
        except Exception:
            saved_meta = DEFAULT_META_RFT
        meta = st.number_input('Meta RFT (%)', min_value=0.0, max_value=100.0, value=float(saved_meta), step=0.1)
        st.session_state['meta_rft'] = float(meta)
        ls_set('meta_rft', meta)
        st.caption('Regra visual: RFT <= meta = verde | RFT > meta = vermelho')

    tabs = st.tabs(['Dashboard', 'Tendencias', 'Rolling 12', 'Base & Upload', 'Historico', 'Sobre'])

    latest = latest_upload_id_for_year(conn, posto, ano) if ano is not None else None
    info = upload_info(conn, latest) if latest is not None else None
    year_df = load_merged_year_df(conn, posto, ano) if latest is not None else pd.DataFrame()
    all_df = load_merged_all_df(conn, posto) if latest is not None else pd.DataFrame()

    with tabs[0]:
        if year_df.empty:
            st.info('Sem histórico válido para esse posto/ano.')
        else:
            ok_ano, status_label = year_status(year_df, ano)
            min_date, max_date, selected_label, selected_range, valid = resolve_period_selection(year_df, ano, mode)
            if not valid:
                st.info('Nenhum período disponível para o modo selecionado.')
            else:
                cards = compute_rft_cards(year_df, ano, mode, selected_range, ok_ano, max_date)
                base_summary = summarize_base(year_df, conn, posto, ano)
                st.caption(f"Ano: {ano} | Fechamento: {status_label} | Último arquivo: {info['file_name'] if info else '-'} | Último upload: {info['uploaded_at'] if info else '-'} | Status da base: {base_summary['status']}")
                st.markdown(
                    f"<div class='pill pill-blue'>Posto: <strong>{posto}</strong></div>"
                    f"<div class='pill {base_summary['status_cls']}'>Status da base: <strong>{base_summary['status']}</strong></div>"
                    f"<div class='pill pill-blue'>Meta: <strong>{str(meta).replace('.', ',')}%</strong></div>"
                    f"<div class='pill pill-blue'>Uploads consolidados: <strong>{base_summary['uploads_count']}</strong></div>",
                    unsafe_allow_html=True,
                )
                c1, c2, c3, c4, c5 = st.columns(5)
                with c1:
                    st.markdown(metric_card_html('Diario', cards['daily'], 'Leitura do dia selecionado'), unsafe_allow_html=True)
                with c2:
                    st.markdown(metric_card_html('Semanal', cards['weekly'], 'Consolidado semanal'), unsafe_allow_html=True)
                with c3:
                    st.markdown(metric_card_html('Mensal', cards['monthly'], 'Consolidado mensal'), unsafe_allow_html=True)
                with c4:
                    st.markdown(metric_card_html('Anual', cards['yearly'], 'Ano até 12/12'), unsafe_allow_html=True)
                with c5:
                    st.markdown(metric_card_html('YTD', cards['ytd'], 'Acumulado do ano até o recorte'), unsafe_allow_html=True)
                l, r = st.columns([1.2,1])
                with l:
                    st.subheader('Resumo executivo da base')
                    for label, value in [
                        ('Recorte atual', selected_label),
                        ('Data mínima da base', year_df['DT_HR_INSPECAO'].dt.date.min().strftime('%d/%m/%Y') if not year_df.empty else '-'),
                        ('Data máxima da base', year_df['DT_HR_INSPECAO'].dt.date.max().strftime('%d/%m/%Y') if not year_df.empty else '-'),
                        ('Última data com dado', year_df['DT_HR_INSPECAO'].dt.date.max().strftime('%d/%m/%Y') if not year_df.empty else '-'),
                        ('Dias cobertos', str(int(year_df['DT_HR_INSPECAO'].dt.date.nunique()) if not year_df.empty else 0)),
                        ('Uploads consolidados', str(base_summary['uploads_count'])),
                        ('Status da base', base_summary['status']),
                    ]:
                        st.markdown(kv_html(label, value), unsafe_allow_html=True)
                with r:
                    current = cards['ytd'] if cards['ytd'] is not None else cards['monthly']
                    current_pct = None if current is None else current['rft_pct']
                    diff = 'Sem dados' if current_pct is None else f"{(current_pct - meta):+.2f}".replace('.', ',') + ' p.p.'
                    st.markdown('<div class="section">' + '<div class="muted">Meta x resultado</div>' + f'<div style="font-size:1.9rem;font-weight:800;" class="{status_class(current_pct)}">{format_pct(current_pct)}</div>' + f'<div class="muted">Meta configurada: {str(meta).replace(".", ",")}%<br>Diferença: {diff}</div>' + '</div>', unsafe_allow_html=True)

    with tabs[1]:
        if year_df.empty:
            st.info('Sem histórico válido para tendências.')
        else:
            st.subheader('Tendências')
            st.caption('RFT normal das versões anteriores: gráfico mensal e semanal em colunas.')
            mt = monthly_trend(year_df, ano)
            wt = weekly_trend(year_df, ano)
            c1, c2 = st.columns(2)
            with c1:
                if mt.empty:
                    st.info('Sem dados mensais.')
                else:
                    st.bar_chart(mt.set_index('Mes')[['RFT']], use_container_width=True)
                    mt_show = mt.copy(); mt_show['RFT'] = mt_show['RFT'].map(lambda x: f'{x:.2f}'.replace('.', ',') + '%')
                    st.dataframe(mt_show, use_container_width=True, hide_index=True)
            with c2:
                if wt.empty:
                    st.info('Sem dados semanais.')
                else:
                    st.bar_chart(wt.set_index('Semana')[['RFT']], use_container_width=True)
                    wt_show = wt.copy(); wt_show['RFT'] = wt_show['RFT'].map(lambda x: f'{x:.2f}'.replace('.', ',') + '%')
                    st.dataframe(wt_show, use_container_width=True, hide_index=True)

    with tabs[2]:
        if all_df.empty or year_df.empty:
            st.info('Sem histórico válido para compor o Rolling 12.')
        else:
            rolling12, rolling12_table = compute_roll12_from_monthly(all_df, year_df['DT_HR_INSPECAO'].dt.date.max())
            st.subheader('Rolling 12')
            st.caption('Sistema separado do RFT normal. Método recomendado: soma dos frames não defeituosos dos últimos 12 meses ÷ soma dos frames produzidos dos últimos 12 meses × 100.')
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(metric_card_html('Rolling 12 Consolidado', rolling12, 'Indicador móvel de 12 meses'), unsafe_allow_html=True)
            with c2:
                if rolling12_table.empty:
                    st.markdown(metric_card_html('Melhor mês', None, 'Sem dados'), unsafe_allow_html=True)
                else:
                    best = rolling12_table.loc[rolling12_table['RFT'].fillna(-1).idxmax()]
                    fake = {'rft_pct': best['RFT'], 'good': best['Nao_Defeituosos'], 'bad': best['Produzidos'] - best['Nao_Defeituosos'], 'total': best['Produzidos']}
                    st.markdown(metric_card_html(f"Melhor mês ({best['Mes']})", fake, 'Maior resultado dentro da janela'), unsafe_allow_html=True)
            with c3:
                if rolling12_table.empty:
                    st.markdown(metric_card_html('Pior mês', None, 'Sem dados'), unsafe_allow_html=True)
                else:
                    worst = rolling12_table.loc[rolling12_table['RFT'].fillna(999).idxmin()]
                    fake = {'rft_pct': worst['RFT'], 'good': worst['Nao_Defeituosos'], 'bad': worst['Produzidos'] - worst['Nao_Defeituosos'], 'total': worst['Produzidos']}
                    st.markdown(metric_card_html(f"Pior mês ({worst['Mes']})", fake, 'Menor resultado dentro da janela'), unsafe_allow_html=True)
            if rolling12_table.empty:
                st.info('Sem dados para compor os últimos 12 meses.')
            else:
                st.bar_chart(rolling12_table.set_index('Mes')[['RFT']], use_container_width=True)
                roll_show = rolling12_table.copy(); roll_show['RFT'] = roll_show['RFT'].map(lambda x: '' if pd.isna(x) else f'{x:.2f}'.replace('.', ',') + '%')
                st.dataframe(roll_show, use_container_width=True, hide_index=True)

    with tabs[3]:
        st.subheader('Base & Upload')
        st.caption('Modos de importação e consolidação com correção do bug que removia 2026 ao importar 2025.')
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

    with tabs[4]:
        st.subheader('Historico')
        hist = uploads_table(conn)
        if hist.empty:
            st.info('Os uploads processados aparecerão aqui.')
        else:
            st.dataframe(hist, use_container_width=True, hide_index=True)
            selected_id = st.selectbox('Selecionar upload', hist['id'].tolist(), format_func=lambda x: f'Upload {x}')
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button('Ver detalhes do upload', use_container_width=True):
                    detail = detail_upload_df(conn, selected_id)
                    if detail.empty:
                        st.warning('Upload sem detalhes disponíveis.')
                    else:
                        sel = upload_info(conn, selected_id)
                        file_name = sel['file_name'] if sel else '-'
                        uploaded_at = sel['uploaded_at'] if sel else '-'
                        st.info(f'Arquivo: {file_name} | Upload: {uploaded_at} | Linhas: {len(detail)}')
                        detail_show = detail.copy()
                        detail_show['DT_HR_INSPECAO'] = detail_show['DT_HR_INSPECAO'].dt.strftime('%d/%m/%Y %H:%M:%S')
                        st.dataframe(detail_show.head(200), use_container_width=True, hide_index=True)
            with c2:
                if st.button('Reprocessar upload', use_container_width=True):
                    new_id = reprocess_upload(conn, selected_id)
                    st.success(f'Upload reprocessado com sucesso. Novo upload: {new_id}.' if new_id else 'Não foi possível reprocessar o upload.')
                    st.rerun()
            with c3:
                if st.button('Excluir upload específico', use_container_width=True):
                    delete_upload(conn, selected_id)
                    st.success('Upload excluído com sucesso.')
                    st.rerun()

    with tabs[5]:
        st.subheader('Sobre')
        st.write(f'Versão V7.5 monolítica com RFT completo (Diário, Semanal, Mensal, YTD e Anual), calendário restaurado, aba de Tendências restaurada e Rolling 12 separado em outra aba. Correção do bug de importação por ano. Gráfico mensal em colunas igual ao semanal e gráfico rolling também em colunas. Meta visual ativa: {str(meta).replace(".", ",")}%')

if __name__ == '__main__':
    main()
