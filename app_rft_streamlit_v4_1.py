
import io
import sqlite3
from calendar import monthrange
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="RFT Automático — V4.1", page_icon="📅", layout="wide")

DB = "rft_v41.db"
REQ = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO"]

st.markdown(
    """
    <style>
    .block-container{max-width:1450px;padding-top:1rem;padding-bottom:2rem}
    .hero{background:linear-gradient(135deg,#0f2747 0%,#1f6fb2 100%);color:#fff;padding:1.2rem 1.4rem;border-radius:18px;margin-bottom:1rem}
    .card{background:#fff;border:1px solid #e6eef7;border-left:6px solid #1f6fb2;border-radius:16px;padding:1rem;min-height:115px;box-shadow:0 6px 18px rgba(10,35,66,.06)}
    .card-title{color:#5d6b78;font-size:.9rem;font-weight:600}.card-value{color:#12355b;font-size:1.9rem;font-weight:800}.card-sub{color:#6f7f8d;font-size:.82rem}
    .chip{display:inline-block;background:#eef5fb;color:#12355b;border:1px solid #d7e7f5;border-radius:999px;padding:.35rem .8rem;margin:0 .35rem .35rem 0;font-size:.9rem}
    </style>
    """,
    unsafe_allow_html=True,
)

# DB

def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)


def init_db(c):
    stmts = [
        "CREATE TABLE IF NOT EXISTS upload_log (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL, uploaded_at TEXT NOT NULL, total_rows INTEGER NOT NULL, status TEXT NOT NULL, message TEXT)",
        "CREATE TABLE IF NOT EXISTS raw_inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, nr_wo TEXT, dt_hr_inspecao TEXT, c_dpu_qg_amarelo REAL, cd_modelo TEXT, cd_posto_cn TEXT, anomalia_falha TEXT)",
        "CREATE TABLE IF NOT EXISTS metric_daily (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, metric_date TEXT NOT NULL, rft_pct REAL, total_wos INTEGER, good_wos INTEGER, bad_wos INTEGER)",
        "CREATE TABLE IF NOT EXISTS metric_weekly (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, week_start TEXT NOT NULL, week_end TEXT NOT NULL, rft_pct REAL, total_wos INTEGER, good_wos INTEGER, bad_wos INTEGER)",
        "CREATE TABLE IF NOT EXISTS metric_monthly (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, month_key TEXT NOT NULL, month_start TEXT NOT NULL, month_end TEXT NOT NULL, rft_pct REAL, total_wos INTEGER, good_wos INTEGER, bad_wos INTEGER)",
        "CREATE TABLE IF NOT EXISTS metric_yearly (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, metric_year INTEGER NOT NULL, is_complete INTEGER NOT NULL, rft_pct REAL, total_wos INTEGER, good_wos INTEGER, bad_wos INTEGER, note TEXT)",
        "CREATE TABLE IF NOT EXISTS metric_ytd (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, metric_date TEXT NOT NULL, metric_year INTEGER NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL, rft_pct REAL, total_wos INTEGER, good_wos INTEGER, bad_wos INTEGER)"
    ]
    for s in stmts:
        c.execute(s)
    c.commit()

# Read/prep

def normalize_columns(df):
    df = df.copy()
    df.columns = [str(x).strip().replace("﻿", "") for x in df.columns]
    return df


def read_file(uploaded_file):
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


def validate_df(df):
    missing = [c for c in REQ if c not in df.columns]
    return len(missing) == 0, missing


def parse_dt(s):
    dt = pd.to_datetime(s, errors='coerce')
    mask = dt.isna() & s.notna()
    if mask.any():
        dt.loc[mask] = pd.to_datetime(s[mask], errors='coerce', dayfirst=True)
    return dt


def prepare(df):
    w = df.copy()
    w['DT_HR_INSPECAO'] = parse_dt(w['DT_HR_INSPECAO'])
    w['C_DPU_QG_AMARELO'] = pd.to_numeric(w['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    w['NR_WO'] = w['NR_WO'].astype(str).str.strip()
    for col in ['CD_MODELO', 'CD_POSTO_CN', 'ANOMALIA_FALHA']:
        if col not in w.columns:
            w[col] = None
    return w[w['DT_HR_INSPECAO'].notna()].copy()

# Metric logic

def calc_rft(df, start_date, end_date):
    sdt = datetime.combine(start_date, time(0, 0, 0))
    edt = datetime.combine(end_date, time(23, 59, 59))
    f = df[(df['DT_HR_INSPECAO'] >= sdt) & (df['DT_HR_INSPECAO'] <= edt)].copy()
    if f.empty:
        return {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0}
    grp = f.groupby('NR_WO', as_index=False)['C_DPU_QG_AMARELO'].sum().rename(columns={'C_DPU_QG_AMARELO': 'SOMA'})
    grp['RFT'] = (grp['SOMA'] == 0).astype(int)
    total = int(len(grp)); good = int(grp['RFT'].sum()); bad = int(total - good)
    pct = round((good / total) * 100, 2) if total else None
    return {'rft_pct': pct, 'total': total, 'good': good, 'bad': bad}


def is_full_year_available(df, year):
    year_df = df[df['DT_HR_INSPECAO'].dt.year == year]
    if year_df.empty:
        return False, f'Sem dados de {year} no arquivo.'
    min_d = year_df['DT_HR_INSPECAO'].dt.date.min()
    max_d = year_df['DT_HR_INSPECAO'].dt.date.max()
    start_expected = date(year, 1, 1)
    end_expected = date(year, 12, 31)
    complete = (min_d <= start_expected) and (max_d >= end_expected)
    if complete:
        return True, f'Ano {year} completo no arquivo.'
    return False, f'Ano {year} incompleto no arquivo ({min_d.strftime("%d/%m/%Y")} a {max_d.strftime("%d/%m/%Y")}).'


def clear_metrics(c, upload_id):
    for t in ['metric_daily', 'metric_weekly', 'metric_monthly', 'metric_yearly', 'metric_ytd']:
        c.execute(f'DELETE FROM {t} WHERE upload_id=?', (upload_id,))
    c.commit()


def generate_metrics(c, upload_id, df):
    clear_metrics(c, upload_id)
    if df.empty:
        return
    unique_dates = sorted(df['DT_HR_INSPECAO'].dt.date.dropna().unique().tolist())

    daily_rows, ytd_rows = [], []
    for d in unique_dates:
        r = calc_rft(df, d, d)
        daily_rows.append((upload_id, d.isoformat(), r['rft_pct'], r['total'], r['good'], r['bad']))
        y = calc_rft(df, date(d.year, 1, 1), d)
        ytd_rows.append((upload_id, d.isoformat(), d.year, date(d.year, 1, 1).isoformat(), d.isoformat(), y['rft_pct'], y['total'], y['good'], y['bad']))
    c.executemany('INSERT INTO metric_daily (upload_id, metric_date, rft_pct, total_wos, good_wos, bad_wos) VALUES (?, ?, ?, ?, ?, ?)', daily_rows)
    c.executemany('INSERT INTO metric_ytd (upload_id, metric_date, metric_year, period_start, period_end, rft_pct, total_wos, good_wos, bad_wos) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', ytd_rows)

    weekly_rows = []
    for monday in sorted({d - timedelta(days=d.weekday()) for d in unique_dates}):
        sunday = monday + timedelta(days=6)
        w = calc_rft(df, monday, sunday)
        weekly_rows.append((upload_id, monday.isoformat(), sunday.isoformat(), w['rft_pct'], w['total'], w['good'], w['bad']))
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
        complete, note = is_full_year_available(df, y)
        if complete:
            r = calc_rft(df, date(y, 1, 1), date(y, 12, 31))
            yearly_rows.append((upload_id, y, 1, r['rft_pct'], r['total'], r['good'], r['bad'], note))
        else:
            yearly_rows.append((upload_id, y, 0, None, 0, 0, 0, note))
    c.executemany('INSERT INTO metric_yearly (upload_id, metric_year, is_complete, rft_pct, total_wos, good_wos, bad_wos, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', yearly_rows)
    c.commit()

# Upload/query helpers

def create_upload(c, file_name, total_rows, status='RECEBIDO', message=''):
    cur = c.execute('INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)', (file_name, datetime.now().isoformat(timespec='seconds'), int(total_rows), status, message))
    c.commit()
    return int(cur.lastrowid)


def update_upload(c, upload_id, status, message=''):
    c.execute('UPDATE upload_log SET status=?, message=? WHERE id=?', (status, message, upload_id))
    c.commit()


def save_raw(c, upload_id, df):
    rows = []
    for _, r in df.iterrows():
        rows.append((upload_id, r.get('NR_WO'), r.get('DT_HR_INSPECAO').isoformat(sep=' ', timespec='seconds') if pd.notna(r.get('DT_HR_INSPECAO')) else None, float(r.get('C_DPU_QG_AMARELO', 0)) if pd.notna(r.get('C_DPU_QG_AMARELO')) else 0.0, r.get('CD_MODELO'), r.get('CD_POSTO_CN'), r.get('ANOMALIA_FALHA')))
    c.executemany('INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_modelo, cd_posto_cn, anomalia_falha) VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
    c.commit()


def latest_upload(c):
    c.row_factory = sqlite3.Row
    return c.execute('SELECT * FROM upload_log WHERE status=? ORDER BY id DESC LIMIT 1', ('PROCESSADO',)).fetchone()


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

# UI helpers

def format_pct(v):
    return 'Sem dados' if v is None or pd.isna(v) else f'{v:.2f}'.replace('.', ',') + '%'


def format_date(d):
    return '-' if d is None else d.strftime('%d/%m/%Y')


def card(title, value, subtitle=''):
    return f"<div class='card'><div class='card-title'>{title}</div><div class='card-value'>{value}</div><div class='card-sub'>{subtitle}</div></div>"


def render_panel(title, row, subtitle=''):
    if row is None:
        return card(title, 'Sem dados', subtitle)
    good = row['good_wos'] if 'good_wos' in row.keys() else 0
    bad = row['bad_wos'] if 'bad_wos' in row.keys() else 0
    total = row['total_wos'] if 'total_wos' in row.keys() else 0
    sub = f"{subtitle} | WOs boas: {good} | ruins: {bad} | total: {total}"
    return card(title, format_pct(row['rft_pct']), sub)

# Sections

def render_dashboard(c):
    cur = latest_upload(c)
    if cur is None:
        st.info('Ainda não existe base operacional processada. Faça o primeiro upload para inicializar o sistema.')
        return
    df = load_upload_df(c, cur['id'])
    min_date = df['DT_HR_INSPECAO'].dt.date.min()
    max_date = df['DT_HR_INSPECAO'].dt.date.max()

    st.markdown("<div class='section-title'>Seleção por calendário</div>", unsafe_allow_html=True)
    mode = st.radio('Escolha o período que você quer visualizar', ['Diário', 'Semanal', 'Mensal', 'Anual'], horizontal=True)

    daily = weekly = monthly = yearly = ytd = None
    context = ''
    if mode == 'Diário':
        selected = st.date_input('Clique no dia que você quer ver', value=max_date, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='daily_picker')
        daily = fetch_metric(c, 'metric_daily', cur['id'], metric_date=selected.isoformat())
        week_start = selected - timedelta(days=selected.weekday())
        week_end = week_start + timedelta(days=6)
        weekly = fetch_metric(c, 'metric_weekly', cur['id'], week_start=week_start.isoformat())
        month_key = f'{selected.year}-{selected.month:02d}'
        monthly = fetch_metric(c, 'metric_monthly', cur['id'], month_key=month_key)
        yearly = fetch_metric(c, 'metric_yearly', cur['id'], metric_year=int(selected.year))
        ytd = fetch_metric(c, 'metric_ytd', cur['id'], metric_date=selected.isoformat())
        context = f'Dia selecionado: {format_date(selected)}'
    elif mode == 'Semanal':
        selected = st.date_input('Escolha qualquer dia da semana que você quer ver', value=max_date, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='weekly_picker')
        week_start = selected - timedelta(days=selected.weekday())
        week_end = week_start + timedelta(days=6)
        weekly = fetch_metric(c, 'metric_weekly', cur['id'], week_start=week_start.isoformat())
        ytd = fetch_metric(c, 'metric_ytd', cur['id'], metric_date=selected.isoformat())
        context = f'Semana selecionada: {format_date(week_start)} a {format_date(week_end)}'
    elif mode == 'Mensal':
        selected = st.date_input('Escolha qualquer dia do mês que você quer ver', value=max_date, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='monthly_picker')
        month_key = f'{selected.year}-{selected.month:02d}'
        start_m = date(selected.year, selected.month, 1)
        end_m = date(selected.year, selected.month, monthrange(selected.year, selected.month)[1])
        monthly = fetch_metric(c, 'metric_monthly', cur['id'], month_key=month_key)
        ytd = fetch_metric(c, 'metric_ytd', cur['id'], metric_date=selected.isoformat())
        context = f'Mês selecionado: {format_date(start_m)} a {format_date(end_m)}'
    else:
        years = sorted(df['DT_HR_INSPECAO'].dt.year.dropna().unique().tolist())
        selected_year = st.selectbox('Escolha o ano', years, index=len(years)-1)
        yearly = fetch_metric(c, 'metric_yearly', cur['id'], metric_year=int(selected_year))
        last_day = df[df['DT_HR_INSPECAO'].dt.year == selected_year]['DT_HR_INSPECAO'].dt.date.max()
        if pd.notna(last_day):
            ytd = fetch_metric(c, 'metric_ytd', cur['id'], metric_date=last_day.isoformat())
        context = f'Ano selecionado: {selected_year}'

    st.markdown("<div class='section-title'>Painel do período selecionado</div>", unsafe_allow_html=True)
    st.markdown(
        f"<span class='chip'><strong>Arquivo:</strong> {cur['file_name']}</span>"
        f"<span class='chip'><strong>Último upload:</strong> {cur['uploaded_at']}</span>"
        f"<span class='chip'><strong>{context}</strong></span>"
        f"<span class='chip'><strong>Período disponível no arquivo:</strong> {format_date(min_date)} a {format_date(max_date)}</span>",
        unsafe_allow_html=True,
    )

    cols = st.columns(5)
    cols[0].markdown(render_panel('Diário', daily, 'Dia escolhido'), unsafe_allow_html=True)
    cols[1].markdown(render_panel('Semanal', weekly, 'Semana correspondente'), unsafe_allow_html=True)
    cols[2].markdown(render_panel('Mensal', monthly, 'Mês correspondente'), unsafe_allow_html=True)
    if yearly is not None and yearly['is_complete'] == 0:
        cols[3].markdown(card('Anual', 'Ano incompleto', yearly['note']), unsafe_allow_html=True)
    else:
        cols[3].markdown(render_panel('Anual', yearly, 'Somente se o ano estiver completo no arquivo'), unsafe_allow_html=True)
    cols[4].markdown(render_panel('YTD', ytd, 'Acumulado até a data selecionada'), unsafe_allow_html=True)


def render_imports(c):
    st.markdown("<div class='section-title'>Atualizar a base</div>", unsafe_allow_html=True)
    st.caption('Nesta versão você precisa enviar apenas um arquivo. O sistema usa esse arquivo para gerar todos os dias, semanas, meses, anos e YTD.')
    current_file = st.file_uploader('Base operacional atual (.xlsx, .xls ou .csv)', type=['xlsx', 'xls', 'csv'])
    c1, c2 = st.columns([1.7, 1])

    if c1.button('🔄 Processar arquivo e gerar todos os períodos', type='primary', use_container_width=True):
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
        cur_id = create_upload(c, current_file.name, len(cur_df), message='Base operacional recebida.')
        try:
            save_raw(c, cur_id, cur_df)
            generate_metrics(c, cur_id, cur_df)
            update_upload(c, cur_id, 'PROCESSADO', 'Base operacional processada com sucesso.')
            st.success('Arquivo processado com sucesso. Foram gerados automaticamente todos os períodos: diário, semanal, mensal, anual e YTD.')
            st.rerun()
        except Exception as e:
            update_upload(c, cur_id, 'ERRO', str(e))
            st.error(f'Erro ao processar a base: {e}')

    if c2.button('♻️ Reprocessar base atual', use_container_width=True):
        cur = latest_upload(c)
        if cur is None:
            st.warning('Não existe base atual processada para reprocessar.')
        else:
            generate_metrics(c, cur['id'], load_upload_df(c, cur['id']))
            st.success('Métricas da base atual reprocessadas com sucesso.')
            st.rerun()


def render_metric_tabs(c):
    st.markdown("<div class='section-title'>Tabelas por período</div>", unsafe_allow_html=True)
    cur = latest_upload(c)
    if cur is None:
        st.info('Ainda não existe base operacional processada.')
        return
    tabs = st.tabs(['Diário', 'Semanal', 'Mensal', 'Anual', 'YTD'])
    mapping = {
        'Diário': ('metric_daily', ['metric_date', 'rft_pct', 'total_wos', 'good_wos', 'bad_wos']),
        'Semanal': ('metric_weekly', ['week_start', 'week_end', 'rft_pct', 'total_wos', 'good_wos', 'bad_wos']),
        'Mensal': ('metric_monthly', ['month_key', 'month_start', 'month_end', 'rft_pct', 'total_wos', 'good_wos', 'bad_wos']),
        'Anual': ('metric_yearly', ['metric_year', 'is_complete', 'rft_pct', 'total_wos', 'good_wos', 'bad_wos', 'note']),
        'YTD': ('metric_ytd', ['metric_date', 'metric_year', 'period_start', 'period_end', 'rft_pct', 'total_wos', 'good_wos', 'bad_wos'])
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


def render_history(c):
    st.markdown("<div class='section-title'>Histórico de uploads</div>", unsafe_allow_html=True)
    df = pd.read_sql_query('SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC LIMIT 200', c)
    if df.empty:
        st.info('Ainda não existe upload salvo.')
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_help():
    with st.expander('Como esta versão funciona', expanded=False):
        st.markdown(
            """
- Você envia **apenas um arquivo** no campo de base operacional.
- O sistema processa esse arquivo e gera automaticamente:
  - todos os **dias**
  - todas as **semanas**
  - todos os **meses**
  - todos os **anos**
  - todos os **YTDs**
- Depois disso, você usa o seletor do período para escolher se quer ver **Diário, Semanal, Mensal ou Anual**.
- O **YTD** sempre aparece ao lado com base **no ano da data selecionada**.
- O **RFT Anual** só é calculado se o arquivo tiver o ano completo; caso contrário, o sistema mostra **Ano incompleto**.
            """
        )


def main():
    c = get_conn()
    init_db(c)
    st.markdown("<div class='hero'><h1>RFT Automático — V4.1</h1><p>Versão simplificada e ajustada: você sobe um único arquivo, o sistema calcula todos os períodos e você escolhe no calendário/período o que quer visualizar.</p></div>", unsafe_allow_html=True)
    render_dashboard(c)
    st.divider()
    render_imports(c)
    st.divider()
    render_metric_tabs(c)
    st.divider()
    render_history(c)
    st.divider()
    render_help()


if __name__ == '__main__':
    main()
