
import io
import json
import sqlite3
from datetime import date, datetime, time, timedelta
from calendar import monthrange

import pandas as pd
import streamlit as st

try:
    from streamlit_local_storage import LocalStorage
except Exception:
    LocalStorage = None

st.set_page_config(page_title="RFT Automático — V5.3", page_icon="📊", layout="wide")

DB = "rft_v53_local.db"
REQ = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO", "CD_POSTO_CN"]
POSTOS = ["QG09", "QG07"]
POSTO_PADRAO = "QG09"
CUTOFF_MONTH = 12
CUTOFF_DAY = 12
LS_PREFIX = "rft_v53_"

CUSTOM_CSS = """
<style>
.block-container{max-width:1480px;padding-top:1rem;padding-bottom:2rem}
html, body, [data-testid="stAppViewContainer"] { background: linear-gradient(180deg,#f9fbff 0%, #f4f8fc 100%); }
.hero{background:linear-gradient(135deg,#081a31 0%,#123b67 42%,#1f6fb2 75%,#4db5f5 100%);color:#fff;padding:1.45rem 1.6rem;border-radius:26px;margin-bottom:1rem;box-shadow:0 14px 34px rgba(8,26,49,.22);position:relative;overflow:hidden}
.hero:after{content:'';position:absolute;right:-60px;top:-60px;width:220px;height:220px;background:rgba(255,255,255,.08);border-radius:50%}
.hero h1{margin:0;font-size:2.05rem;letter-spacing:.2px}
.hero p{margin:.35rem 0 0 0;opacity:.96;font-size:1rem;max-width:980px}
.section-title{font-size:1.08rem;font-weight:800;color:#12253f;margin:1rem 0 .55rem 0;letter-spacing:.2px}
.glass{background:rgba(255,255,255,.78);backdrop-filter: blur(10px);border:1px solid rgba(230,237,245,.9);border-radius:20px;padding:1rem 1.1rem;margin-bottom:.85rem;box-shadow:0 8px 24px rgba(18,37,63,.05)}
.panel-wrap{background:#f9fbff;border:1px solid #e6edf5;border-radius:18px;padding:.8rem .9rem;margin-bottom:.75rem}
.small-panel{background:linear-gradient(180deg,#ffffff 0%, #f9fbff 100%);border:1px solid #e6edf5;border-radius:16px;padding:.9rem 1rem}
.small-title{font-size:.83rem;font-weight:700;color:#637487;margin-bottom:.25rem}.small-value{font-size:1rem;font-weight:800;color:#12253f}
.card{background:linear-gradient(180deg,#ffffff 0%, #fbfdff 100%);border:1px solid #e6edf5;border-left:6px solid #1f6fb2;border-radius:20px;padding:1rem 1rem .95rem 1rem;min-height:132px;box-shadow:0 10px 24px rgba(10,35,66,.06)}
.card-ok{border-left-color:#16a34a}.card-warn{border-left-color:#ea580c}.card-neutral{border-left-color:#1f6fb2}
.card-title{color:#637487;font-size:.92rem;font-weight:800;margin-bottom:.25rem}.card-value{color:#12253f;font-size:2rem;font-weight:900;line-height:1.05;margin-bottom:.3rem;letter-spacing:-.4px}.card-sub{color:#6c7d8e;font-size:.8rem;line-height:1.35}
.chip{display:inline-flex;align-items:center;background:#eef5fb;color:#12355b;border:1px solid #d7e7f5;border-radius:999px;padding:.38rem .82rem;margin:0 .35rem .35rem 0;font-size:.9rem;gap:.35rem}
.ribbon{display:flex;align-items:center;gap:.55rem;background:linear-gradient(90deg,#eff7ff 0%, #f8fbff 100%);border:1px solid #d9e9f8;color:#12355b;border-radius:14px;padding:.75rem .95rem;margin-bottom:.85rem}
[data-testid="stDownloadButton"] button { border-radius:12px !important; }
button[kind="primary"] { border-radius:12px !important; }
</style>
"""

# ----------------------------
# SQLite local persistence
# ----------------------------
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)


def init_db(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS upload_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "file_name TEXT NOT NULL, "
        "uploaded_at TEXT NOT NULL, "
        "total_rows INTEGER NOT NULL, "
        "status TEXT NOT NULL, "
        "message TEXT)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS raw_inspections ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "upload_id INTEGER NOT NULL, "
        "nr_wo TEXT, "
        "dt_hr_inspecao TEXT, "
        "c_dpu_qg_amarelo REAL, "
        "cd_posto_cn TEXT)"
    )
    c.commit()

# ----------------------------
# Browser local storage (light state only)
# ----------------------------
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
        if val in (None, "", "null", "None"):
            return default
        return val
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

# ----------------------------
# Read / prep
# ----------------------------
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


def norm_posto(v):
    txt = str(v).upper().strip()
    if 'QG09' in txt:
        return 'QG09'
    if 'QG07' in txt:
        return 'QG07'
    return txt


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    w = df.copy()
    w['DT_HR_INSPECAO'] = parse_dt(w['DT_HR_INSPECAO'])
    w['C_DPU_QG_AMARELO'] = pd.to_numeric(w['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    w['NR_WO'] = w['NR_WO'].astype(str).str.strip()
    w['CD_POSTO_CN'] = w['CD_POSTO_CN'].astype(str).map(norm_posto)
    return w[w['DT_HR_INSPECAO'].notna()].copy()

# ----------------------------
# Local persistence helpers
# ----------------------------
def create_upload(c, file_name, total_rows, status='RECEBIDO', message=''):
    cur = c.execute(
        'INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)',
        (file_name, datetime.now().isoformat(timespec='seconds'), int(total_rows), status, message)
    )
    c.commit()
    return int(cur.lastrowid)


def update_upload(c, upload_id, status, message=''):
    c.execute('UPDATE upload_log SET status=?, message=? WHERE id=?', (status, message, upload_id))
    c.commit()


def save_raw(c, upload_id, df: pd.DataFrame):
    rows = []
    for _, r in df.iterrows():
        rows.append((
            int(upload_id),
            r['NR_WO'],
            r['DT_HR_INSPECAO'].isoformat(sep=' ', timespec='seconds'),
            float(r['C_DPU_QG_AMARELO']),
            r['CD_POSTO_CN']
        ))
    c.executemany(
        'INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn) VALUES (?, ?, ?, ?, ?)',
        rows
    )
    c.commit()


def uploads_table(c):
    return pd.read_sql_query(
        'SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC LIMIT 300',
        c
    )


def available_years(c, posto):
    q = "SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano FROM raw_inspections WHERE cd_posto_cn=? ORDER BY ano"
    df = pd.read_sql_query(q, c, params=[posto])
    return [int(x) for x in df['ano'].dropna().tolist()] if not df.empty else []


def latest_upload_id_for_year(c, posto, year):
    q = "SELECT MAX(upload_id) AS upload_id FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?"
    df = pd.read_sql_query(q, c, params=[posto, str(year)])
    if df.empty or pd.isna(df.loc[0, 'upload_id']):
        return None
    return int(df.loc[0, 'upload_id'])


def upload_info(c, upload_id):
    c.row_factory = sqlite3.Row
    return c.execute('SELECT * FROM upload_log WHERE id=?', (upload_id,)).fetchone()


def load_upload_df(c, upload_id):
    df = pd.read_sql_query(
        'SELECT nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE upload_id=?',
        c, params=[upload_id]
    )
    if not df.empty:
        df['DT_HR_INSPECAO'] = pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
        df['C_DPU_QG_AMARELO'] = pd.to_numeric(df['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
        df['CD_POSTO_CN'] = df['CD_POSTO_CN'].astype(str).map(norm_posto)
    return df

# ----------------------------
# Snapshot export/import
# ----------------------------
def export_snapshot(c):
    uploads = pd.read_sql_query('SELECT * FROM upload_log ORDER BY id', c)
    inspections = pd.read_sql_query('SELECT upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn FROM raw_inspections ORDER BY upload_id, id', c)
    payload = {
        'app_version': 'V5.3',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'uploads': uploads.to_dict(orient='records'),
        'raw_inspections': inspections.to_dict(orient='records'),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')


def import_snapshot(c, uploaded_file):
    content = uploaded_file.getvalue().decode('utf-8')
    payload = json.loads(content)
    uploads = payload.get('uploads', [])
    raws = payload.get('raw_inspections', [])

    c.execute('DELETE FROM raw_inspections')
    c.execute('DELETE FROM upload_log')
    c.commit()

    old_to_new = {}
    for item in uploads:
        old_id = int(item.get('id', 0))
        cur = c.execute(
            'INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)',
            (
                item.get('file_name'),
                item.get('uploaded_at'),
                int(item.get('total_rows', 0)),
                item.get('status', 'PROCESSADO'),
                item.get('message', '')
            )
        )
        new_id = int(cur.lastrowid)
        old_to_new[old_id] = new_id
    c.commit()

    rows = []
    for r in raws:
        rows.append((
            old_to_new.get(int(r.get('upload_id', 0)), 0),
            r.get('nr_wo'),
            r.get('dt_hr_inspecao'),
            float(r.get('c_dpu_qg_amarelo', 0) or 0),
            r.get('cd_posto_cn')
        ))
    if rows:
        c.executemany(
            'INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn) VALUES (?, ?, ?, ?, ?)',
            rows
        )
    c.commit()

# ----------------------------
# Business rules
# ----------------------------
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


def year_status(df: pd.DataFrame, year: int):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year]
    if ydf.empty:
        return False, f'Sem dados de {year}.'
    max_d = ydf['DT_HR_INSPECAO'].dt.date.max()
    cutoff = date(year, CUTOFF_MONTH, CUTOFF_DAY)
    complete = max_d >= cutoff
    if complete:
        return True, f'Ano {year} fechado em 12/12'
    return False, f'Ano {year} em andamento até {max_d.strftime("%d/%m/%Y")}'


def week_options(df: pd.DataFrame, year: int):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return []
    dates = sorted(ydf['DT_HR_INSPECAO'].dt.date.unique().tolist())
    mondays = sorted({d - timedelta(days=d.weekday()) for d in dates})
    opts = []
    for i, monday in enumerate(mondays, start=1):
        sunday = monday + timedelta(days=6)
        label = 'Semana {} — {} a {}'.format(i, monday.strftime('%d/%m/%Y'), sunday.strftime('%d/%m/%Y'))
        opts.append((label, monday, sunday))
    return opts


def month_options(df: pd.DataFrame, year: int):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return []
    opts = []
    for m in sorted(ydf['DT_HR_INSPECAO'].dt.month.unique().tolist()):
        start = date(year, int(m), 1)
        end = date(year, int(m), monthrange(year, int(m))[1])
        label = '{} — {} a {}'.format(start.strftime('%m/%Y'), start.strftime('%d/%m/%Y'), end.strftime('%d/%m/%Y'))
        opts.append((label, start, end))
    return opts

# ----------------------------
# UI helpers
# ----------------------------
def format_pct(v):
    return 'Sem dados' if v is None or pd.isna(v) else f'{v:.2f}'.replace('.', ',') + '%'


def format_date(d):
    return '-' if d is None else d.strftime('%d/%m/%Y')


def status_class(v):
    if v is None or pd.isna(v):
        return 'card-neutral'
    return 'card-ok' if v >= 95 else 'card-warn'


def card_html(title, result, subtitle=''):
    if result is None:
        return "<div class='card card-neutral'><div class='card-title'>{}</div><div class='card-value'>Sem dados</div><div class='card-sub'>{}</div></div>".format(title, subtitle)
    cls = status_class(result['rft_pct'])
    sub = '{} | WOs boas: {} | ruins: {} | total: {}'.format(subtitle, result['good'], result['bad'], result['total'])
    return "<div class='card {}'><div class='card-title'>{}</div><div class='card-value'>{}</div><div class='card-sub'>{}</div></div>".format(cls, title, format_pct(result['rft_pct']), sub)

# ----------------------------
# Main UI
# ----------------------------
def render_dashboard(c):
    default_posto = ls_get('posto', POSTO_PADRAO)
    posto_idx = POSTOS.index(default_posto) if default_posto in POSTOS else 0
    posto = st.radio('Posto', POSTOS, index=posto_idx, horizontal=True)
    ls_set('posto', posto)

    anos = available_years(c, posto)
    if not anos:
        st.markdown("<div class='glass'><div class='small-title'>Base vazia</div><div class='small-value'>Ainda não existem dados salvos</div></div>", unsafe_allow_html=True)
        return

    prev_year = ls_get('ano', None)
    try:
        prev_year = int(prev_year) if prev_year is not None else None
    except Exception:
        prev_year = None
    ano_idx = anos.index(prev_year) if prev_year in anos else (anos.index(2025) if 2025 in anos else len(anos)-1)
    ano = st.selectbox('Ano salvo para consulta', anos, index=ano_idx)
    ls_set('ano', ano)

    upload_id = latest_upload_id_for_year(c, posto, ano)
    if upload_id is None:
        st.markdown("<div class='glass'><div class='small-title'>Sem histórico</div><div class='small-value'>Não há upload local para esse ano/posto</div></div>", unsafe_allow_html=True)
        return

    info = upload_info(c, upload_id)
    df_all = load_upload_df(c, upload_id)
    df = df_all[(df_all['CD_POSTO_CN'] == posto) & (df_all['DT_HR_INSPECAO'].dt.year == ano)].copy()
    if df.empty:
        st.markdown("<div class='glass'><div class='small-title'>Sem linhas válidas</div><div class='small-value'>O arquivo salvo não possui linhas válidas para esse filtro</div></div>", unsafe_allow_html=True)
        return

    min_date = df['DT_HR_INSPECAO'].dt.date.min()
    max_date = df['DT_HR_INSPECAO'].dt.date.max()

    st.markdown("<div class='section-title'>Exploração do período</div>", unsafe_allow_html=True)
    mode_options = ['Diário', 'Semanal', 'Mensal', 'Anual']
    default_mode = ls_get('modo', 'Diário')
    mode_idx = mode_options.index(default_mode) if default_mode in mode_options else 0
    mode = st.radio('Modo', mode_options, index=mode_idx, horizontal=True)
    ls_set('modo', mode)

    daily = weekly = monthly = yearly = ytd = None
    context = ''

    if mode == 'Diário':
        saved_day = ls_get('dia', '')
        try:
            default_day = datetime.fromisoformat(saved_day).date() if saved_day else max_date
        except Exception:
            default_day = max_date
        if default_day < min_date or default_day > max_date:
            default_day = max_date
        selected = st.date_input('Dia', value=default_day, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='day_v53')
        ls_set('dia', selected.isoformat())
        daily = calc_rft(df, selected, selected)
        ws = selected - timedelta(days=selected.weekday())
        we = ws + timedelta(days=6)
        weekly = calc_rft(df, ws, we)
        ms = date(ano, selected.month, 1)
        me = date(ano, selected.month, monthrange(ano, selected.month)[1])
        monthly = calc_rft(df, ms, me)
        ok, _ = year_status(df, ano)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok else None
        ytd = calc_rft(df, date(ano, 1, 1), selected)
        context = 'Dia {}'.format(format_date(selected))
    elif mode == 'Semanal':
        opts = week_options(df, ano)
        labels = [x[0] for x in opts]
        if not labels:
            st.markdown("<div class='glass'><div class='small-title'>Sem semanas</div><div class='small-value'>Não há semanas disponíveis para esse ano</div></div>", unsafe_allow_html=True)
            return
        saved_week = ls_get('semana_label', '')
        week_idx = labels.index(saved_week) if saved_week in labels else len(labels)-1
        label = st.selectbox('Semana do ano', labels, index=week_idx)
        ls_set('semana_label', label)
        found = next(x for x in opts if x[0] == label)
        ws, we = found[1], found[2]
        weekly = calc_rft(df, ws, we)
        ytd = calc_rft(df, date(ano, 1, 1), we if we <= max_date else max_date)
        ok, _ = year_status(df, ano)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok else None
        context = label
    elif mode == 'Mensal':
        opts = month_options(df, ano)
        labels = [x[0] for x in opts]
        if not labels:
            st.markdown("<div class='glass'><div class='small-title'>Sem meses</div><div class='small-value'>Não há meses disponíveis para esse ano</div></div>", unsafe_allow_html=True)
            return
        saved_month = ls_get('mes_label', '')
        month_idx = labels.index(saved_month) if saved_month in labels else len(labels)-1
        label = st.selectbox('Mês do ano', labels, index=month_idx)
        ls_set('mes_label', label)
        found = next(x for x in opts if x[0] == label)
        ms, me = found[1], found[2]
        monthly = calc_rft(df, ms, me)
        ytd = calc_rft(df, date(ano, 1, 1), me if me <= max_date else max_date)
        ok, _ = year_status(df, ano)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok else None
        context = label
    else:
        ok, _ = year_status(df, ano)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok else None
        ytd = calc_rft(df, date(ano, 1, 1), max_date if max_date <= date(ano, 12, 12) else date(ano, 12, 12))
        context = 'Ano {}'.format(ano)

    ok_ano, year_badge = year_status(df, ano)
    status_chip = "<span class='chip'><strong>Status do ano:</strong> {}</span>".format(year_badge)
    st.markdown(
        "<div class='panel-wrap'><span class='chip'><strong>Arquivo:</strong> {}</span><span class='chip'><strong>Salvo em:</strong> {}</span><span class='chip'><strong>Posto:</strong> {}</span><span class='chip'><strong>Ano:</strong> {}</span><span class='chip'><strong>Filtro:</strong> {}</span><span class='chip'><strong>Janela:</strong> {} a {}</span>{}</div>".format(
            info['file_name'], info['uploaded_at'], posto, ano, context, format_date(min_date), format_date(max_date), status_chip
        ),
        unsafe_allow_html=True
    )

    m1, m2 = st.columns(2)
    m1.markdown("<div class='small-panel'><div class='small-title'>Último arquivo do ano</div><div class='small-value'>{}</div></div>".format(info['file_name']), unsafe_allow_html=True)
    m2.markdown("<div class='small-panel'><div class='small-title'>Fechamento anual</div><div class='small-value'>{}</div></div>".format('Fechado em 12/12' if ok_ano else year_badge), unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(card_html('Diário', daily, 'Dia selecionado'), unsafe_allow_html=True)
    c2.markdown(card_html('Semanal', weekly, 'Consolidação semanal'), unsafe_allow_html=True)
    c3.markdown(card_html('Mensal', monthly, 'Consolidação mensal'), unsafe_allow_html=True)
    c4.markdown(card_html('Anual', yearly, 'Ano até 12/12'), unsafe_allow_html=True)
    c5.markdown(card_html('YTD', ytd, 'Acumulado do ano'), unsafe_allow_html=True)


def render_data_ops(c):
    st.markdown("<div class='section-title'>Base local e snapshots</div>", unsafe_allow_html=True)
    st.markdown("<div class='ribbon'>💾 <strong>Snapshots</strong> permitem compartilhar manualmente a base salva entre pessoas sem depender de banco externo. O navegador guarda apenas preferências leves.</div>", unsafe_allow_html=True)

    col_left, col_right = st.columns([1.2, 1])
    with col_left:
        st.markdown("<div class='glass'>", unsafe_allow_html=True)
        st.subheader('Adicionar ou atualizar base')
        uploaded = st.file_uploader('Base operacional atual (.xlsx, .xls ou .csv)', type=['xlsx', 'xls', 'csv'])
        if st.button('Salvar arquivo localmente', type='primary', use_container_width=True):
            if uploaded is None:
                st.error('Selecione um arquivo antes de salvar.')
                st.stop()
            try:
                raw = read_file(uploaded)
                ok, miss = validate_df(raw)
                if not ok:
                    st.error('Base operacional inválida: ' + ', '.join(miss))
                    st.stop()
                df = prepare(raw)
            except Exception as e:
                st.error('Erro ao ler a base operacional: {}'.format(e))
                st.stop()
            uid = create_upload(c, uploaded.name, len(df), message='Base recebida e salva localmente.')
            try:
                save_raw(c, uid, df)
                update_upload(c, uid, 'PROCESSADO', 'Base salva com sucesso.')
                st.success('Arquivo salvo com sucesso.')
                st.rerun()
            except Exception as e:
                update_upload(c, uid, 'ERRO', str(e))
                st.error('Erro ao salvar a base: {}'.format(e))
        st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
        st.markdown("<div class='glass'>", unsafe_allow_html=True)
        st.subheader('Compartilhar por snapshot')
        snapshot_bytes = export_snapshot(c)
        st.download_button(
            'Baixar snapshot da base',
            data=snapshot_bytes,
            file_name='RFT_Snapshot_V5_3.json',
            mime='application/json',
            use_container_width=True
        )
        import_file = st.file_uploader('Importar snapshot (.json)', type=['json'], key='snapshot_import')
        if st.button('Importar snapshot para esta instância', use_container_width=True):
            if import_file is None:
                st.error('Selecione um snapshot antes de importar.')
                st.stop()
            try:
                import_snapshot(c, import_file)
                st.success('Snapshot importado com sucesso.')
                st.rerun()
            except Exception as e:
                st.error('Erro ao importar snapshot: {}'.format(e))
        st.markdown("</div>", unsafe_allow_html=True)


def render_history(c):
    st.markdown("<div class='section-title'>Histórico local de uploads</div>", unsafe_allow_html=True)
    df = uploads_table(c)
    if df.empty:
        st.markdown("<div class='glass'><div class='small-title'>Nada salvo ainda</div><div class='small-value'>O histórico começará a aparecer após o primeiro upload</div></div>", unsafe_allow_html=True)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_help():
    with st.expander('Resumo da versão V5.3', expanded=False):
        st.markdown("""
- Design renovado com foco em visual mais bonito e leitura mais limpa.
- QG09 principal e QG07 opcional, sem misturar resultados.
- Consulta por anos (ex.: 2025/2026), semanal, mensal, anual e YTD.
- Base local em SQLite para operação simples.
- Snapshot em JSON para exportar/importar a base entre pessoas manualmente.
- Navegador armazena apenas preferências leves de filtro (posto, ano, semana, mês e modo).
""")


def main():
    c = get_conn()
    init_db(c)
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown("<div class='hero'><h1>RFT Automático — V5.3</h1><p>Design elevado, experiência mais elegante e snapshots compartilháveis para trocar a base entre pessoas, mantendo QG09/QG07, 2025/2026, semanal, mensal, anual e YTD.</p></div>", unsafe_allow_html=True)
    render_dashboard(c)
    st.divider()
    render_data_ops(c)
    st.divider()
    render_history(c)
    st.divider()
    render_help()


if __name__ == '__main__':
    main()
