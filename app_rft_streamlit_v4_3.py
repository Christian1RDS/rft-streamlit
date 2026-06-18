
import io
import sqlite3
from datetime import date, datetime, time, timedelta
from calendar import monthrange

import pandas as pd
import streamlit as st

st.set_page_config(page_title="RFT Automático — V4.3", page_icon="📊", layout="wide")

DB = "rft_v43.db"
REQ = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO", "CD_POSTO_CN"]
POSTOS = ["QG09", "QG07"]
POSTO_PADRAO = "QG09"

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

# =========================
# Banco de dados
# =========================
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)


def init_db(c):
    c.execute("CREATE TABLE IF NOT EXISTS upload_log (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL, uploaded_at TEXT NOT NULL, total_rows INTEGER NOT NULL, status TEXT NOT NULL, message TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS raw_inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, nr_wo TEXT, dt_hr_inspecao TEXT, c_dpu_qg_amarelo REAL, cd_modelo TEXT, cd_posto_cn TEXT, anomalia_falha TEXT)")
    c.commit()

# =========================
# Leitura / preparação
# =========================
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


def normalize_posto(v):
    txt = str(v).upper().strip()
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
    w['CD_POSTO_CN'] = w['CD_POSTO_CN'].astype(str).map(normalize_posto)
    for col in ['CD_MODELO', 'ANOMALIA_FALHA']:
        if col not in w.columns:
            w[col] = None
    return w[w['DT_HR_INSPECAO'].notna()].copy()

# =========================
# Persistência
# =========================
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
        rows.append((
            upload_id,
            r.get('NR_WO'),
            r.get('DT_HR_INSPECAO').isoformat(sep=' ', timespec='seconds') if pd.notna(r.get('DT_HR_INSPECAO')) else None,
            float(r.get('C_DPU_QG_AMARELO', 0)) if pd.notna(r.get('C_DPU_QG_AMARELO')) else 0.0,
            r.get('CD_MODELO'),
            r.get('CD_POSTO_CN'),
            r.get('ANOMALIA_FALHA')
        ))
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
        df['CD_POSTO_CN'] = df['CD_POSTO_CN'].astype(str).map(normalize_posto)
    return df

# =========================
# Regras de cálculo
# =========================
def calc_rft(df, start_date, end_date):
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


def is_full_year_available(df, year):
    year_df = df[df['DT_HR_INSPECAO'].dt.year == year]
    if year_df.empty:
        return False, f'Sem dados de {year} no posto selecionado.'
    min_d = year_df['DT_HR_INSPECAO'].dt.date.min()
    max_d = year_df['DT_HR_INSPECAO'].dt.date.max()
    complete = (min_d <= date(year, 1, 1)) and (max_d >= date(year, 12, 31))
    if complete:
        return True, f'Ano {year} completo no arquivo.'
    return False, f'Ano {year} incompleto no arquivo ({min_d.strftime("%d/%m/%Y")} a {max_d.strftime("%d/%m/%Y")}).'


def years_available(df):
    years = sorted(df['DT_HR_INSPECAO'].dt.year.dropna().astype(int).unique().tolist())
    return years

# =========================
# UI helpers
# =========================
def format_pct(v):
    return 'Sem dados' if v is None or pd.isna(v) else f'{v:.2f}'.replace('.', ',') + '%'


def format_date(d):
    return '-' if d is None else d.strftime('%d/%m/%Y')


def card(title, value, subtitle=''):
    return f"<div class='card'><div class='card-title'>{title}</div><div class='card-value'>{value}</div><div class='card-sub'>{subtitle}</div></div>"


def render_panel(title, result, subtitle=''):
    if result is None:
        return card(title, 'Sem dados', subtitle)
    sub = f"{subtitle} | WOs boas: {result['good']} | ruins: {result['bad']} | total: {result['total']}"
    return card(title, format_pct(result['rft_pct']), sub)

# =========================
# Seções da tela
# =========================
def render_dashboard(c):
    cur = latest_upload(c)
    if cur is None:
        st.info('Ainda não existe base processada. Faça o upload do arquivo para inicializar o sistema.')
        return

    df_all = load_upload_df(c, cur['id'])
    posto = st.radio('Posto para cálculo do RFT', POSTOS, index=0, horizontal=True)
    df = df_all[df_all['CD_POSTO_CN'] == posto].copy()

    if df.empty:
        st.warning(f'Não há dados de {posto} no arquivo carregado. O app não mistura QG09 com QG07.')
        return

    min_date = df['DT_HR_INSPECAO'].dt.date.min()
    max_date = df['DT_HR_INSPECAO'].dt.date.max()
    years = years_available(df)
    ano_painel = st.selectbox('Ano do painel anual (ex.: 2025)', years, index=0 if 2025 in years else len(years)-1)

    st.markdown("<div class='section-title'>Seleção por período</div>", unsafe_allow_html=True)
    mode = st.radio('Escolha o período que você quer visualizar', ['Diário', 'Semanal', 'Mensal', 'Anual'], horizontal=True)

    daily = weekly = monthly = yearly = ytd = None
    context = ''

    if mode == 'Diário':
        selected = st.date_input('Clique no dia que você quer ver', value=max_date, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='daily_picker_v43')
        daily = calc_rft(df, selected, selected)
        week_start = selected - timedelta(days=selected.weekday())
        week_end = week_start + timedelta(days=6)
        weekly = calc_rft(df, week_start, week_end)
        month_start = date(selected.year, selected.month, 1)
        month_end = date(selected.year, selected.month, monthrange(selected.year, selected.month)[1])
        monthly = calc_rft(df, month_start, month_end)
        complete, note = is_full_year_available(df, int(ano_painel))
        yearly = calc_rft(df, date(int(ano_painel), 1, 1), date(int(ano_painel), 12, 31)) if complete else {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0, 'note': note}
        ytd = calc_rft(df, date(selected.year, 1, 1), selected)
        context = f'Dia selecionado: {format_date(selected)}'

    elif mode == 'Semanal':
        selected = st.date_input('Escolha qualquer dia da semana que você quer ver', value=max_date, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='weekly_picker_v43')
        week_start = selected - timedelta(days=selected.weekday())
        week_end = week_start + timedelta(days=6)
        weekly = calc_rft(df, week_start, week_end)
        complete, note = is_full_year_available(df, int(ano_painel))
        yearly = calc_rft(df, date(int(ano_painel), 1, 1), date(int(ano_painel), 12, 31)) if complete else {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0, 'note': note}
        ytd = calc_rft(df, date(selected.year, 1, 1), selected)
        context = f'Semana selecionada: {format_date(week_start)} a {format_date(week_end)}'

    elif mode == 'Mensal':
        selected = st.date_input('Escolha qualquer dia do mês que você quer ver', value=max_date, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='monthly_picker_v43')
        month_start = date(selected.year, selected.month, 1)
        month_end = date(selected.year, selected.month, monthrange(selected.year, selected.month)[1])
        monthly = calc_rft(df, month_start, month_end)
        complete, note = is_full_year_available(df, int(ano_painel))
        yearly = calc_rft(df, date(int(ano_painel), 1, 1), date(int(ano_painel), 12, 31)) if complete else {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0, 'note': note}
        ytd = calc_rft(df, date(selected.year, 1, 1), selected)
        context = f'Mês selecionado: {format_date(month_start)} a {format_date(month_end)}'

    else:
        complete, note = is_full_year_available(df, int(ano_painel))
        if complete:
            yearly = calc_rft(df, date(int(ano_painel), 1, 1), date(int(ano_painel), 12, 31))
        else:
            yearly = {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0, 'note': note}
        last_day = df[df['DT_HR_INSPECAO'].dt.year == int(ano_painel)]['DT_HR_INSPECAO'].dt.date.max()
        if pd.notna(last_day):
            ytd = calc_rft(df, date(int(ano_painel), 1, 1), last_day)
        context = f'Ano selecionado: {ano_painel}'

    st.markdown("<div class='section-title'>Painel do período selecionado</div>", unsafe_allow_html=True)
    st.markdown(
        f"<span class='chip'><strong>Arquivo:</strong> {cur['file_name']}</span>"
        f"<span class='chip'><strong>Último upload:</strong> {cur['uploaded_at']}</span>"
        f"<span class='chip'><strong>Posto:</strong> {posto}</span>"
        f"<span class='chip'><strong>{context}</strong></span>"
        f"<span class='chip'><strong>Ano anual escolhido:</strong> {ano_painel}</span>"
        f"<span class='chip'><strong>Período disponível no arquivo para {posto}:</strong> {format_date(min_date)} a {format_date(max_date)}</span>",
        unsafe_allow_html=True,
    )

    cols = st.columns(5)
    cols[0].markdown(render_panel('Diário', daily, 'Dia escolhido'), unsafe_allow_html=True)
    cols[1].markdown(render_panel('Semanal', weekly, 'Semana correspondente'), unsafe_allow_html=True)
    cols[2].markdown(render_panel('Mensal', monthly, 'Mês correspondente'), unsafe_allow_html=True)
    if yearly is not None and yearly.get('rft_pct') is None and 'note' in yearly:
        cols[3].markdown(card('Anual', 'Ano incompleto', yearly['note']), unsafe_allow_html=True)
    else:
        cols[3].markdown(render_panel('Anual', yearly, f'Ano {ano_painel}'), unsafe_allow_html=True)
    cols[4].markdown(render_panel('YTD', ytd, 'Acumulado até a data/ano selecionado'), unsafe_allow_html=True)


def render_imports(c):
    st.markdown("<div class='section-title'>Atualizar a base</div>", unsafe_allow_html=True)
    st.caption('Agora o app usa apenas os dados de QG09 e QG07. QG09 é o padrão, mas você pode alternar para QG07 sem misturar os postos.')
    current_file = st.file_uploader('Base operacional atual (.xlsx, .xls ou .csv)', type=['xlsx', 'xls', 'csv'])
    c1, c2 = st.columns([1.7, 1])
    if c1.button('🔄 Processar arquivo', type='primary', use_container_width=True):
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
            update_upload(c, cur_id, 'PROCESSADO', 'Base operacional processada com sucesso.')
            st.success('Arquivo processado com sucesso. Agora escolha QG09 ou QG07 e depois o período que você deseja visualizar.')
            st.rerun()
        except Exception as e:
            update_upload(c, cur_id, 'ERRO', str(e))
            st.error(f'Erro ao processar a base: {e}')

    if c2.button('🔁 Atualizar leitura do último arquivo', use_container_width=True):
        cur = latest_upload(c)
        if cur is None:
            st.warning('Não existe base atual processada.')
        else:
            st.success('Última base carregada pronta para consulta.')
            st.rerun()


def render_tables(c):
    st.markdown("<div class='section-title'>Tabelas automáticas por período</div>", unsafe_allow_html=True)
    cur = latest_upload(c)
    if cur is None:
        st.info('Ainda não existe base operacional processada.')
        return
    df_all = load_upload_df(c, cur['id'])
    posto = st.radio('Posto das tabelas', POSTOS, index=0, horizontal=True, key='table_posto_v43')
    df = df_all[df_all['CD_POSTO_CN'] == posto].copy()
    if df.empty:
        st.info(f'Sem dados de {posto} para mostrar nas tabelas.')
        return

    unique_dates = sorted(df['DT_HR_INSPECAO'].dt.date.dropna().unique().tolist())
    daily_tbl = []
    for d in unique_dates:
        r = calc_rft(df, d, d)
        daily_tbl.append([d.isoformat(), format_pct(r['rft_pct']), r['good'], r['bad'], r['total']])

    weekly_tbl = []
    for monday in sorted({d - timedelta(days=d.weekday()) for d in unique_dates}):
        sunday = monday + timedelta(days=6)
        r = calc_rft(df, monday, sunday)
        weekly_tbl.append([monday.isoformat(), sunday.isoformat(), format_pct(r['rft_pct']), r['good'], r['bad'], r['total']])

    monthly_tbl = []
    for y, m in sorted({(d.year, d.month) for d in unique_dates}):
        start = date(y, m, 1)
        end = date(y, m, monthrange(y, m)[1])
        r = calc_rft(df, start, end)
        monthly_tbl.append([f'{y}-{m:02d}', start.isoformat(), end.isoformat(), format_pct(r['rft_pct']), r['good'], r['bad'], r['total']])

    yearly_tbl = []
    for y in sorted({d.year for d in unique_dates}):
        complete, note = is_full_year_available(df, y)
        if complete:
            r = calc_rft(df, date(y, 1, 1), date(y, 12, 31))
            yearly_tbl.append([y, 'Completo', format_pct(r['rft_pct']), r['good'], r['bad'], r['total'], note])
        else:
            yearly_tbl.append([y, 'Incompleto', 'Sem dados', 0, 0, 0, note])

    ytd_tbl = []
    for d in unique_dates:
        r = calc_rft(df, date(d.year, 1, 1), d)
        ytd_tbl.append([d.isoformat(), d.year, format_pct(r['rft_pct']), r['good'], r['bad'], r['total']])

    tabs = st.tabs(['Diário', 'Semanal', 'Mensal', 'Anual', 'YTD'])
    with tabs[0]:
        st.dataframe(pd.DataFrame(daily_tbl, columns=['Data', 'RFT', 'WOs boas', 'WOs ruins', 'WOs total']), use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(pd.DataFrame(weekly_tbl, columns=['Início semana', 'Fim semana', 'RFT', 'WOs boas', 'WOs ruins', 'WOs total']), use_container_width=True, hide_index=True)
    with tabs[2]:
        st.dataframe(pd.DataFrame(monthly_tbl, columns=['Mês', 'Início mês', 'Fim mês', 'RFT', 'WOs boas', 'WOs ruins', 'WOs total']), use_container_width=True, hide_index=True)
    with tabs[3]:
        st.dataframe(pd.DataFrame(yearly_tbl, columns=['Ano', 'Status', 'RFT', 'WOs boas', 'WOs ruins', 'WOs total', 'Observação']), use_container_width=True, hide_index=True)
    with tabs[4]:
        st.dataframe(pd.DataFrame(ytd_tbl, columns=['Data de corte', 'Ano', 'RFT YTD', 'WOs boas', 'WOs ruins', 'WOs total']), use_container_width=True, hide_index=True)


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
- O app usa **somente os dados de QG09 e QG07**; os demais postos são ignorados.
- **QG09 é o principal**, mas você pode alternar manualmente para **QG07** sem misturar os resultados.
- Agora existe uma opção explícita para escolher o **ano do painel anual** (por exemplo: 2025).
- O **RFT anual** só é calculado se o arquivo tiver o ano completo; caso contrário, o sistema mostra **Ano incompleto**.
- O **YTD** continua aparecendo ao lado com base no ano da data/ano selecionado.
- As tabelas por período são geradas **dinamicamente** e separadas por posto.
            """
        )


def main():
    c = get_conn()
    init_db(c)
    st.markdown("<div class='hero'><h1>RFT Automático — V4.3</h1><p>Versão ajustada para usar apenas QG09 e QG07, com QG09 como padrão, QG07 opcional e seleção explícita do ano anual (ex.: 2025).</p></div>", unsafe_allow_html=True)
    render_dashboard(c)
    st.divider()
    render_imports(c)
    st.divider()
    render_tables(c)
    st.divider()
    render_history(c)
    st.divider()
    render_help()


if __name__ == '__main__':
    main()
