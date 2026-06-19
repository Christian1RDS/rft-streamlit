
import io
import json
import sqlite3
from datetime import date, datetime, time, timedelta
from calendar import monthrange

import pandas as pd
import streamlit as st

# Optional browser local storage helper
try:
    from streamlit_local_storage import LocalStorage
except Exception:  # package may be missing until requirements are installed
    LocalStorage = None

st.set_page_config(page_title="RFT Automático — V5.2", page_icon="📊", layout="wide")

DB = "rft_v52_local.db"
REQ = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO", "CD_POSTO_CN"]
POSTOS = ["QG09", "QG07"]
POSTO_PADRAO = "QG09"
CUTOFF_MONTH = 12
CUTOFF_DAY = 12
LS_PREFIX = "rft_v52_"

CUSTOM_CSS = """
<style>
.block-container{max-width:1450px;padding-top:1rem;padding-bottom:2rem}
.hero{background:linear-gradient(135deg,#0b1f3a 0%,#174c84 55%,#2f86c8 100%);color:#fff;padding:1.35rem 1.5rem;border-radius:22px;margin-bottom:1rem;box-shadow:0 8px 24px rgba(11,31,58,.22)}
.hero h1{margin:0;font-size:2rem}.hero p{margin:.35rem 0 0 0;opacity:.95}
.section-title{font-size:1.12rem;font-weight:700;color:#12355b;margin:1rem 0 .5rem 0}
.panel-wrap{background:#f9fbff;border:1px solid #e6eef7;border-radius:18px;padding:.8rem .9rem;margin-bottom:.75rem}
.card{background:#fff;border:1px solid #e8eef6;border-left:6px solid #1f6fb2;border-radius:18px;padding:1rem 1rem .9rem 1rem;min-height:126px;box-shadow:0 6px 18px rgba(10,35,66,.06)}
.card-ok{border-left-color:#16a34a}.card-warn{border-left-color:#ea580c}.card-neutral{border-left-color:#1f6fb2}
.card-title{color:#5d6b78;font-size:.92rem;font-weight:700;margin-bottom:.2rem}.card-value{color:#12355b;font-size:1.95rem;font-weight:800;line-height:1.1;margin-bottom:.25rem}.card-sub{color:#66788a;font-size:.80rem}
.chip{display:inline-block;background:#eef5fb;color:#12355b;border:1px solid #d7e7f5;border-radius:999px;padding:.35rem .8rem;margin:0 .35rem .35rem 0;font-size:.9rem}
.note{background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;border-radius:14px;padding:.85rem 1rem;margin-bottom:.75rem}
.oknote{background:#edf8f1;border:1px solid #b7dfc2;color:#166534;border-radius:14px;padding:.85rem 1rem;margin-bottom:.75rem}
.mininote{background:#eff6ff;border:1px solid #bfdbfe;color:#1d4ed8;border-radius:14px;padding:.75rem .9rem;margin-bottom:.75rem}
</style>
"""

# ----------------------------
# SQLite local persistence
# ----------------------------
def get_conn():
    c = sqlite3.connect(DB, check_same_thread=False)
    return c


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
        return default if val in (None, "", "null") else val
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
    df.columns = [str(x).strip().replace("\ufeff", "") for x in df.columns]
    return df


def read_file(uploaded_file) -> pd.DataFrame:
    ext = uploaded_file.name.lower().split('.')[-1]
    b = uploaded_file.getvalue()
    if ext == 'csv':
        last_err = None
        for enc in ['utf-8-sig', 'utf-16', 'latin1']:
            for sep in [None, ';', ',', '\t']:
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


def is_finished_year_via_dec12(df: pd.DataFrame, year: int):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year]
    if ydf.empty:
        return False, f'Sem dados de {year}.'
    min_d = ydf['DT_HR_INSPECAO'].dt.date.min()
    max_d = ydf['DT_HR_INSPECAO'].dt.date.max()
    cutoff = date(year, CUTOFF_MONTH, CUTOFF_DAY)
    complete = max_d >= cutoff
    if complete:
        return True, f'Ano {year} considerado finalizado ao atingir {cutoff.strftime("%d/%m/%Y")}. Intervalo encontrado: {min_d.strftime("%d/%m/%Y")} a {max_d.strftime("%d/%m/%Y")}. '
    return False, f'Ano {year} ainda não chegou em {cutoff.strftime("%d/%m/%Y")}. Intervalo encontrado: {min_d.strftime("%d/%m/%Y")} a {max_d.strftime("%d/%m/%Y")}. '


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


def simple_card_html(title, value, subtitle=''):
    return "<div class='card card-neutral'><div class='card-title'>{}</div><div class='card-value'>{}</div><div class='card-sub'>{}</div></div>".format(title, value, subtitle)

# ----------------------------
# Sections
# ----------------------------
def render_dashboard(c):
    default_posto = ls_get('posto', POSTO_PADRAO)
    posto_idx = POSTOS.index(default_posto) if default_posto in POSTOS else 0
    posto = st.radio('Posto para cálculo do RFT', POSTOS, index=posto_idx, horizontal=True)
    ls_set('posto', posto)

    anos = available_years(c, posto)
    if not anos:
        st.info('Ainda não existem dados salvos de {}. Faça upload de um arquivo para iniciar.'.format(posto))
        return

    prev_year = ls_get('ano', None)
    if prev_year is not None:
        try:
            prev_year = int(prev_year)
        except Exception:
            prev_year = None
    ano_index = anos.index(prev_year) if prev_year in anos else (anos.index(2025) if 2025 in anos else len(anos)-1)
    ano = st.selectbox('Ano salvo para consulta', anos, index=ano_index)
    ls_set('ano', ano)

    upload_id = latest_upload_id_for_year(c, posto, ano)
    if upload_id is None:
        st.warning('Não há upload salvo para {} em {}.'.format(posto, ano))
        return

    info = upload_info(c, upload_id)
    df_all = load_upload_df(c, upload_id)
    df = df_all[(df_all['CD_POSTO_CN'] == posto) & (df_all['DT_HR_INSPECAO'].dt.year == ano)].copy()
    if df.empty:
        st.warning('Não há dados de {} em {} no upload selecionado.'.format(posto, ano))
        return

    min_date = df['DT_HR_INSPECAO'].dt.date.min()
    max_date = df['DT_HR_INSPECAO'].dt.date.max()

    st.markdown("<div class='section-title'>Seleção por período</div>", unsafe_allow_html=True)
    mode_options = ['Diário', 'Semanal', 'Mensal', 'Anual']
    default_mode = ls_get('modo', 'Diário')
    mode_idx = mode_options.index(default_mode) if default_mode in mode_options else 0
    mode = st.radio('Escolha o período que você quer visualizar', mode_options, index=mode_idx, horizontal=True)
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
        selected = st.date_input('Clique no dia que você quer ver', value=default_day, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='day_v52')
        ls_set('dia', selected.isoformat())
        daily = calc_rft(df, selected, selected)
        ws = selected - timedelta(days=selected.weekday())
        we = ws + timedelta(days=6)
        weekly = calc_rft(df, ws, we)
        ms = date(ano, selected.month, 1)
        me = date(ano, selected.month, monthrange(ano, selected.month)[1])
        monthly = calc_rft(df, ms, me)
        ok, note = is_finished_year_via_dec12(df, ano)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok else {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0, 'note': note}
        ytd = calc_rft(df, date(ano, 1, 1), selected)
        context = 'Dia selecionado: {}'.format(format_date(selected))

    elif mode == 'Semanal':
        opts = week_options(df, ano)
        labels = [x[0] for x in opts]
        if not labels:
            st.warning('Não há semanas disponíveis para este ano.')
            return
        saved_week = ls_get('semana_label', '')
        week_idx = labels.index(saved_week) if saved_week in labels else len(labels)-1
        label = st.selectbox('Semana do ano', labels, index=week_idx)
        ls_set('semana_label', label)
        found = next(x for x in opts if x[0] == label)
        ws, we = found[1], found[2]
        weekly = calc_rft(df, ws, we)
        ytd = calc_rft(df, date(ano, 1, 1), we if we <= max_date else max_date)
        ok, note = is_finished_year_via_dec12(df, ano)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok else {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0, 'note': note}
        context = 'Semana selecionada: {}'.format(label)

    elif mode == 'Mensal':
        opts = month_options(df, ano)
        labels = [x[0] for x in opts]
        if not labels:
            st.warning('Não há meses disponíveis para este ano.')
            return
        saved_month = ls_get('mes_label', '')
        month_idx = labels.index(saved_month) if saved_month in labels else len(labels)-1
        label = st.selectbox('Mês do ano', labels, index=month_idx)
        ls_set('mes_label', label)
        found = next(x for x in opts if x[0] == label)
        ms, me = found[1], found[2]
        monthly = calc_rft(df, ms, me)
        ytd = calc_rft(df, date(ano, 1, 1), me if me <= max_date else max_date)
        ok, note = is_finished_year_via_dec12(df, ano)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok else {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0, 'note': note}
        context = 'Mês selecionado: {}'.format(label)

    else:
        ok, note = is_finished_year_via_dec12(df, ano)
        yearly = calc_rft(df, date(ano, 1, 1), date(ano, 12, 12)) if ok else {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0, 'note': note}
        ytd = calc_rft(df, date(ano, 1, 1), max_date if max_date <= date(ano, 12, 12) else date(ano, 12, 12))
        context = 'Ano selecionado: {}'.format(ano)

    st.markdown(
        "<div class='panel-wrap'><span class='chip'><strong>Arquivo:</strong> {}</span><span class='chip'><strong>Upload salvo localmente:</strong> {}</span><span class='chip'><strong>Posto:</strong> {}</span><span class='chip'><strong>Ano salvo:</strong> {}</span><span class='chip'><strong>{}</strong></span><span class='chip'><strong>Período disponível:</strong> {} a {}</span></div>".format(
            info['file_name'], info['uploaded_at'], posto, ano, context, format_date(min_date), format_date(max_date)
        ),
        unsafe_allow_html=True
    )

    ok_ano, nota_ano = is_finished_year_via_dec12(df, ano)
    note_class = 'oknote' if ok_ano else 'note'
    st.markdown("<div class='{}'><strong>Observação do anual:</strong> {}</div>".format(note_class, nota_ano), unsafe_allow_html=True)
    st.markdown("<div class='mininote'><strong>Persistência híbrida:</strong> os dados do arquivo são salvos localmente no app e apenas filtros leves (ano, posto, semana, mês, modo) são reforçados no navegador. Se houver reboot/redeploy do Streamlit Community Cloud, o histórico local pode ser perdido.</div>", unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(card_html('Diário', daily, 'Dia escolhido'), unsafe_allow_html=True)
    c2.markdown(card_html('Semanal', weekly, 'Semana correspondente'), unsafe_allow_html=True)
    c3.markdown(card_html('Mensal', monthly, 'Mês correspondente'), unsafe_allow_html=True)
    if yearly is not None and yearly.get('rft_pct') is None and 'note' in yearly:
        c4.markdown(simple_card_html('Anual', 'Ano incompleto', yearly['note']), unsafe_allow_html=True)
    else:
        c4.markdown(card_html('Anual', yearly, 'Ano {} (finaliza em 12/12)'.format(ano)), unsafe_allow_html=True)
    c5.markdown(card_html('YTD', ytd, 'Acumulado no ano selecionado'), unsafe_allow_html=True)


def render_imports(c):
    st.markdown("<div class='section-title'>Salvar novo arquivo</div>", unsafe_allow_html=True)
    st.caption('Esta versão tenta persistir localmente no app e também reforçar filtros leves no navegador. O arquivo completo não é salvo no navegador.')
    current_file = st.file_uploader('Base operacional atual (.xlsx, .xls ou .csv)', type=['xlsx', 'xls', 'csv'])
    if st.button('💾 Salvar arquivo localmente e atualizar histórico', type='primary', use_container_width=True):
        if current_file is None:
            st.error('Selecione a base operacional atual antes de salvar.')
            st.stop()
        try:
            raw = read_file(current_file)
            ok, miss = validate_df(raw)
            if not ok:
                st.error('Base operacional inválida: ' + ', '.join(miss))
                st.stop()
            df = prepare(raw)
        except Exception as e:
            st.error('Erro ao ler a base operacional: {}'.format(e))
            st.stop()
        uid = create_upload(c, current_file.name, len(df), message='Base recebida e salva localmente.')
        try:
            save_raw(c, uid, df)
            update_upload(c, uid, 'PROCESSADO', 'Base salva com sucesso.')
            st.success('Arquivo salvo com sucesso. Enquanto a instância local do app estiver disponível, os anos e históricos poderão ser consultados.')
            st.rerun()
        except Exception as e:
            update_upload(c, uid, 'ERRO', str(e))
            st.error('Erro ao salvar a base: {}'.format(e))


def render_history(c):
    st.markdown("<div class='section-title'>Histórico de arquivos salvos localmente</div>", unsafe_allow_html=True)
    df = uploads_table(c)
    if df.empty:
        st.info('Ainda não existe upload salvo.')
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_help():
    with st.expander('Como esta versão funciona', expanded=False):
        st.markdown(
            '- Visual renovado com cards mais limpos e painel superior mais elegante.\n'
            '- O app usa **somente** QG09 e QG07, sem misturar os resultados.\n'
            '- Existe alternância entre anos salvos (ex.: 2025 e 2026) **enquanto o histórico local do app existir**.\n'
            '- O ano é considerado **finalizado em 12/12** para cálculo anual.\n'
            '- No modo semanal, existe um seletor de **Semana 1, Semana 2, Semana 3...**.\n'
            '- No modo mensal, existe um seletor de meses disponíveis do ano salvo.\n'
            '- O navegador guarda **apenas estado leve** (filtros e seleções) para não ficar pesado.\n'
            '- Esta versão **não garante** persistência definitiva compartilhada entre usuários no Streamlit Community Cloud.'
        )


def main():
    c = get_conn()
    init_db(c)
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown("<div class='hero'><h1>RFT Automático — V5.2</h1><p>Versão híbrida leve: visual bonito, QG09/QG07, anos 2025/2026, semanal/mensal/anual/YTD, salvamento local no app e reforço leve no navegador.</p></div>", unsafe_allow_html=True)
    render_dashboard(c)
    st.divider()
    render_imports(c)
    st.divider()
    render_history(c)
    st.divider()
    render_help()


if __name__ == '__main__':
    main()
