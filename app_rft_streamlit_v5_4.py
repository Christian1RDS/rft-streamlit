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

st.set_page_config(page_title='RFT Automático — V5.4', page_icon='📊', layout='wide')
DB='rft_v54_local.db'
REQ=['NR_WO','DT_HR_INSPECAO','C_DPU_QG_AMARELO','CD_POSTO_CN']
POSTOS=['QG09','QG07']
LS_PREFIX='rft_v54_'
POSTO_PADRAO='QG09'

CUSTOM_CSS = '''
<style>
.block-container{max-width:1500px;padding-top:1rem;padding-bottom:2rem}
html, body, [data-testid="stAppViewContainer"]{background:radial-gradient(circle at top right, rgba(77,181,245,.14), transparent 30%),radial-gradient(circle at top left, rgba(31,111,178,.12), transparent 22%),linear-gradient(180deg,#f8fbff 0%, #f2f7fc 100%)}
.hero{background:linear-gradient(135deg,#07172d 0%,#0d2d54 35%,#1b5fa0 75%,#45a8ef 100%);color:#fff;padding:1.55rem 1.7rem;border-radius:28px;margin-bottom:1rem;box-shadow:0 18px 40px rgba(7,23,45,.24);position:relative;overflow:hidden}
.hero:before{content:'';position:absolute;inset:auto -80px -80px auto;width:250px;height:250px;border-radius:50%;background:rgba(255,255,255,.07)}
.hero:after{content:'';position:absolute;inset:-80px auto auto -80px;width:220px;height:220px;border-radius:50%;background:rgba(255,255,255,.05)}
.hero h1{margin:0;font-size:2.2rem;letter-spacing:.2px;font-weight:900}
.hero p{margin:.42rem 0 0 0;opacity:.97;font-size:1rem;max-width:980px;line-height:1.45}
.section-title{font-size:1.02rem;font-weight:900;color:#0f2340;margin:1.1rem 0 .65rem 0;letter-spacing:.2px;text-transform:uppercase}
.panel{background:rgba(255,255,255,.82);backdrop-filter: blur(12px);border:1px solid rgba(224,234,245,.9);border-radius:22px;padding:1rem 1.05rem;box-shadow:0 8px 24px rgba(15,35,64,.05);margin-bottom:.9rem}
.soft-ribbon{background:linear-gradient(90deg,#edf6ff 0%, #f8fbff 100%);border:1px solid #d9e9f8;color:#12355b;border-radius:16px;padding:.82rem 1rem;margin-bottom:.85rem}
.summary-bar{display:flex;flex-wrap:wrap;gap:.55rem;margin-top:.2rem}
.chip{display:inline-flex;align-items:center;gap:.45rem;padding:.45rem .85rem;border:1px solid #dbe9f6;background:#f6fbff;border-radius:999px;color:#12355b;font-size:.9rem;line-height:1}
.mini-card{background:#fff;border:1px solid #e4edf6;border-radius:18px;padding:.9rem 1rem;box-shadow:0 8px 22px rgba(15,35,64,.04)}
.mini-title{font-size:.78rem;font-weight:800;color:#6c7b89;text-transform:uppercase;letter-spacing:.35px;margin-bottom:.2rem}
.mini-value{font-size:1rem;font-weight:900;color:#10233d;line-height:1.25}
.kpi-card{background:linear-gradient(180deg,#ffffff 0%, #fbfdff 100%);border:1px solid #e4edf6;border-radius:22px;padding:1rem;box-shadow:0 10px 30px rgba(15,35,64,.06);min-height:146px;position:relative;overflow:hidden}
.kpi-card:after{content:'';position:absolute;inset:0 auto 0 0;width:6px;background:#1f6fb2}
.kpi-card.ok:after{background:#16a34a}.kpi-card.warn:after{background:#ea580c}.kpi-card.neutral:after{background:#1f6fb2}
.kpi-title{font-size:.88rem;font-weight:800;color:#637487;margin-bottom:.22rem;text-transform:uppercase;letter-spacing:.35px}
.kpi-value{font-size:2.08rem;font-weight:900;color:#10233d;line-height:1.02;margin-bottom:.3rem;letter-spacing:-.5px}
.kpi-sub{font-size:.8rem;color:#6b7c8d;line-height:1.35}
div[data-testid="stFileUploader"] section{border-radius:18px !important;border:1px dashed #c6d9ec !important;background:rgba(255,255,255,.7) !important}
button[kind="primary"], .stDownloadButton button{border-radius:14px !important}
div[data-testid="stDataFrame"]{background:#fff;border:1px solid #e4edf6;border-radius:18px;padding:.35rem}
</style>
'''
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db(c):
    c.execute('CREATE TABLE IF NOT EXISTS upload_log (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL, uploaded_at TEXT NOT NULL, total_rows INTEGER NOT NULL, status TEXT NOT NULL, message TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS raw_inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, nr_wo TEXT, dt_hr_inspecao TEXT, c_dpu_qg_amarelo REAL, cd_posto_cn TEXT)')
    c.commit()

def get_local_storage():
    if LocalStorage is None:
        return None
    try:
        return LocalStorage()
    except Exception:
        return None

def ls_get(key, default=None):
    ls=get_local_storage()
    if ls is None: return default
    try:
        val=ls.getItem(LS_PREFIX + key, key=f'get_{key}')
        return default if val in (None,'','null','None') else val
    except Exception:
        return default

def ls_set(key, value):
    ls=get_local_storage()
    if ls is None: return
    try:
        ls.setItem(LS_PREFIX + key, str(value), key=f'set_{key}')
    except Exception:
        pass

def normalize_columns(df):
    df=df.copy()
    df.columns=[str(x).strip().replace('\ufeff','') for x in df.columns]
    return df

def read_file(uploaded_file):
    ext=uploaded_file.name.lower().split('.')[-1]
    b=uploaded_file.getvalue()
    if ext=='csv':
        last_err=None
        for enc in ['utf-8-sig','utf-16','latin1']:
            for sep in [None,'; ',',','\t']:
                try:
                    if sep is None:
                        df=pd.read_csv(io.BytesIO(b), encoding=enc, sep=None, engine='python')
                    else:
                        df=pd.read_csv(io.BytesIO(b), encoding=enc, sep=sep)
                    return normalize_columns(df)
                except Exception as e:
                    last_err=e
        raise ValueError(f'Não foi possível ler o CSV. Detalhe: {last_err}')
    if ext in ['xlsx','xls']:
        engine='openpyxl' if ext=='xlsx' else 'xlrd'
        return normalize_columns(pd.read_excel(io.BytesIO(b), engine=engine))
    raise ValueError('Formato não suportado. Use .xlsx, .xls ou .csv')

def validate_df(df):
    missing=[c for c in REQ if c not in df.columns]
    return len(missing)==0, missing

def parse_dt(s):
    dt=pd.to_datetime(s, errors='coerce')
    mask=dt.isna() & s.notna()
    if mask.any():
        dt.loc[mask]=pd.to_datetime(s[mask], errors='coerce', dayfirst=True)
    return dt

def norm_posto(v):
    txt=str(v).upper().strip()
    if 'QG09' in txt: return 'QG09'
    if 'QG07' in txt: return 'QG07'
    return txt

def prepare(df):
    w=df.copy()
    w['DT_HR_INSPECAO']=parse_dt(w['DT_HR_INSPECAO'])
    w['C_DPU_QG_AMARELO']=pd.to_numeric(w['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    w['NR_WO']=w['NR_WO'].astype(str).str.strip()
    w['CD_POSTO_CN']=w['CD_POSTO_CN'].astype(str).map(norm_posto)
    return w[w['DT_HR_INSPECAO'].notna()].copy()

def create_upload(c, file_name, total_rows, status='RECEBIDO', message=''):
    cur=c.execute('INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)', (file_name, datetime.now().isoformat(timespec='seconds'), int(total_rows), status, message))
    c.commit(); return int(cur.lastrowid)

def update_upload(c, upload_id, status, message=''):
    c.execute('UPDATE upload_log SET status=?, message=? WHERE id=?', (status, message, upload_id))
    c.commit()

def save_raw(c, upload_id, df):
    rows=[]
    for _,r in df.iterrows():
        rows.append((int(upload_id), r['NR_WO'], r['DT_HR_INSPECAO'].isoformat(sep=' ', timespec='seconds'), float(r['C_DPU_QG_AMARELO']), r['CD_POSTO_CN']))
    c.executemany('INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn) VALUES (?, ?, ?, ?, ?)', rows)
    c.commit()

def uploads_table(c):
    return pd.read_sql_query('SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC LIMIT 300', c)

def available_years(c, posto):
    q="SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano FROM raw_inspections WHERE cd_posto_cn=? ORDER BY ano"
    df=pd.read_sql_query(q, c, params=[posto])
    return [int(x) for x in df['ano'].dropna().tolist()] if not df.empty else []

def latest_upload_id_for_year(c, posto, year):
    q="SELECT MAX(upload_id) AS upload_id FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?"
    df=pd.read_sql_query(q, c, params=[posto, str(year)])
    if df.empty or pd.isna(df.loc[0,'upload_id']): return None
    return int(df.loc[0,'upload_id'])

def upload_info(c, upload_id):
    c.row_factory=sqlite3.Row
    return c.execute('SELECT * FROM upload_log WHERE id=?', (upload_id,)).fetchone()

def load_upload_df(c, upload_id):
    df=pd.read_sql_query('SELECT nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE upload_id=?', c, params=[upload_id])
    if not df.empty:
        df['DT_HR_INSPECAO']=pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
        df['C_DPU_QG_AMARELO']=pd.to_numeric(df['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
        df['CD_POSTO_CN']=df['CD_POSTO_CN'].astype(str).map(norm_posto)
    return df
def calc_rft(df, start_date, end_date):
    sdt=datetime.combine(start_date, time(0,0,0)); edt=datetime.combine(end_date, time(23,59,59))
    f=df[(df['DT_HR_INSPECAO']>=sdt)&(df['DT_HR_INSPECAO']<=edt)].copy()
    if f.empty: return {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0}
    grp=f.groupby('NR_WO', as_index=False)['C_DPU_QG_AMARELO'].sum().rename(columns={'C_DPU_QG_AMARELO':'SOMA'})
    grp['RFT']=(grp['SOMA']==0).astype(int)
    total=int(len(grp)); good=int(grp['RFT'].sum()); bad=int(total-good)
    pct=round((good/total)*100, 2) if total else None
    return {'rft_pct': pct, 'total': total, 'good': good, 'bad': bad}

def year_status(df, year):
    ydf=df[df['DT_HR_INSPECAO'].dt.year==year]
    if ydf.empty: return False, 'Sem dados'
    max_d=ydf['DT_HR_INSPECAO'].dt.date.max()
    cutoff=date(year, CUTOFF_MONTH, CUTOFF_DAY)
    return (max_d >= cutoff), ('Fechado em 12/12' if max_d >= cutoff else 'Até ' + max_d.strftime('%d/%m/%Y'))

def week_options(df, year):
    ydf=df[df['DT_HR_INSPECAO'].dt.year==year].copy()
    if ydf.empty: return []
    dates=sorted(ydf['DT_HR_INSPECAO'].dt.date.unique().tolist())
    mondays=sorted({d-timedelta(days=d.weekday()) for d in dates})
    opts=[]
    for i,monday in enumerate(mondays, start=1):
        sunday=monday+timedelta(days=6)
        label='Semana {} — {} a {}'.format(i, monday.strftime('%d/%m/%Y'), sunday.strftime('%d/%m/%Y'))
        opts.append((label,monday,sunday))
    return opts

def month_options(df, year):
    ydf=df[df['DT_HR_INSPECAO'].dt.year==year].copy()
    if ydf.empty: return []
    opts=[]
    for m in sorted(ydf['DT_HR_INSPECAO'].dt.month.unique().tolist()):
        start=date(year,int(m),1); end=date(year,int(m),monthrange(year,int(m))[1])
        label='{} — {} a {}'.format(start.strftime('%m/%Y'), start.strftime('%d/%m/%Y'), end.strftime('%d/%m/%Y'))
        opts.append((label,start,end))
    return opts

def format_pct(v):
    return 'Sem dados' if v is None or pd.isna(v) else f'{v:.2f}'.replace('.', ',') + '%'

def format_date(d):
    return '-' if d is None else d.strftime('%d/%m/%Y')

def status_class(v):
    if v is None or pd.isna(v): return 'neutral'
    return 'ok' if v >= 95 else 'warn'

def card_html(title, result, subtitle=''):
    if result is None:
        return "<div class='kpi-card neutral'><div class='kpi-title'>{}</div><div class='kpi-value'>Sem dados</div><div class='kpi-sub'>{}</div></div>".format(title, subtitle)
    cls=status_class(result['rft_pct'])
    sub='{} • WOs boas: {} • ruins: {} • total: {}'.format(subtitle, result['good'], result['bad'], result['total'])
    return "<div class='kpi-card {}'><div class='kpi-title'>{}</div><div class='kpi-value'>{}</div><div class='kpi-sub'>{}</div></div>".format(cls, title, format_pct(result['rft_pct']), sub)
def render_dashboard(c):
    default_posto=ls_get('posto', POSTO_PADRAO)
    posto_idx=POSTOS.index(default_posto) if default_posto in POSTOS else 0
    posto=st.radio('Posto para cálculo do RFT', POSTOS, index=posto_idx, horizontal=True)
    ls_set('posto', posto)
    anos=available_years(c, posto)
    if not anos:
        st.markdown("<div class='panel'><div class='mini-title'>Base vazia</div><div class='mini-value'>Adicione um arquivo para começar o histórico visual</div></div>", unsafe_allow_html=True)
        return
    prev_year=ls_get('ano', None)
    try:
        prev_year=int(prev_year) if prev_year is not None else None
    except Exception:
        prev_year=None
    ano_idx=anos.index(prev_year) if prev_year in anos else (anos.index(2025) if 2025 in anos else len(anos)-1)
    ano=st.selectbox('Ano salvo para consulta', anos, index=ano_idx)
    ls_set('ano', ano)
    upload_id=latest_upload_id_for_year(c, posto, ano)
    if upload_id is None:
        st.markdown("<div class='panel'><div class='mini-title'>Sem histórico</div><div class='mini-value'>Não há upload salvo para esse ano/posto</div></div>", unsafe_allow_html=True)
        return
    info=upload_info(c, upload_id)
    df_all=load_upload_df(c, upload_id)
    df=df_all[(df_all['CD_POSTO_CN']==posto) & (df_all['DT_HR_INSPECAO'].dt.year==ano)].copy()
    if df.empty:
        st.markdown("<div class='panel'><div class='mini-title'>Sem linhas válidas</div><div class='mini-value'>O arquivo salvo não possui linhas válidas para esse filtro</div></div>", unsafe_allow_html=True)
        return
    min_date=df['DT_HR_INSPECAO'].dt.date.min(); max_date=df['DT_HR_INSPECAO'].dt.date.max()
    ok_ano, status_label=year_status(df, ano)
    st.markdown("<div class='section-title'>Painel principal</div>", unsafe_allow_html=True)
    st.markdown("<div class='panel'><div class='summary-bar'><span class='chip'><strong>Arquivo:</strong> {}</span><span class='chip'><strong>Salvo em:</strong> {}</span><span class='chip'><strong>Posto:</strong> {}</span><span class='chip'><strong>Ano:</strong> {}</span><span class='chip'><strong>Fechamento:</strong> {}</span><span class='chip'><strong>Período:</strong> {} a {}</span></div></div>".format(info['file_name'], info['uploaded_at'], posto, ano, status_label, format_date(min_date), format_date(max_date)), unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Seleção por período</div>", unsafe_allow_html=True)
    mode_options=['Diário','Semanal','Mensal','Anual']
    default_mode=ls_get('modo', 'Diário')
    mode_idx=mode_options.index(default_mode) if default_mode in mode_options else 0
    mode=st.radio('Modo de visualização', mode_options, index=mode_idx, horizontal=True)
    ls_set('modo', mode)
    daily=weekly=monthly=yearly=ytd=None
    selected_label='—'
    if mode=='Diário':
        saved_day=ls_get('dia', '')
        try:
            default_day=datetime.fromisoformat(saved_day).date() if saved_day else max_date
        except Exception:
            default_day=max_date
        if default_day < min_date or default_day > max_date: default_day=max_date
        selected=st.date_input('Dia', value=default_day, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='day_v54')
        ls_set('dia', selected.isoformat())
        selected_label=format_date(selected)
        daily=calc_rft(df, selected, selected)
        ws=selected-timedelta(days=selected.weekday()); we=ws+timedelta(days=6)
        weekly=calc_rft(df, ws, we)
        ms=date(ano, selected.month, 1); me=date(ano, selected.month, monthrange(ano, selected.month)[1])
        monthly=calc_rft(df, ms, me)
        yearly=calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None
        ytd=calc_rft(df, date(ano,1,1), selected)
    elif mode=='Semanal':
        opts=week_options(df, ano)
        labels=[x[0] for x in opts]
        if not labels:
            st.markdown("<div class='panel'><div class='mini-title'>Sem semanas</div><div class='mini-value'>Não há semanas disponíveis para esse ano</div></div>", unsafe_allow_html=True)
            return
        saved_week=ls_get('semana_label', '')
        week_idx=labels.index(saved_week) if saved_week in labels else len(labels)-1
        label=st.selectbox('Semana do ano', labels, index=week_idx)
        ls_set('semana_label', label)
        selected_label=label
        found=next(x for x in opts if x[0]==label)
        ws,we=found[1],found[2]
        weekly=calc_rft(df, ws, we)
        yearly=calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None
        ytd=calc_rft(df, date(ano,1,1), we if we<=max_date else max_date)
    elif mode=='Mensal':
        opts=month_options(df, ano)
        labels=[x[0] for x in opts]
        if not labels:
            st.markdown("<div class='panel'><div class='mini-title'>Sem meses</div><div class='mini-value'>Não há meses disponíveis para esse ano</div></div>", unsafe_allow_html=True)
            return
        saved_month=ls_get('mes_label', '')
        month_idx=labels.index(saved_month) if saved_month in labels else len(labels)-1
        label=st.selectbox('Mês do ano', labels, index=month_idx)
        ls_set('mes_label', label)
        selected_label=label
        found=next(x for x in opts if x[0]==label)
        ms,me=found[1],found[2]
        monthly=calc_rft(df, ms, me)
        yearly=calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None
        ytd=calc_rft(df, date(ano,1,1), me if me<=max_date else max_date)
    else:
        selected_label='Ano {}'.format(ano)
        yearly=calc_rft(df, date(ano,1,1), date(ano,12,12)) if ok_ano else None
        ytd=calc_rft(df, date(ano,1,1), max_date if max_date<=date(ano,12,12) else date(ano,12,12))
    m1,m2,m3=st.columns(3)
    m1.markdown("<div class='mini-card'><div class='mini-title'>Recorte atual</div><div class='mini-value'>{}</div></div>".format(selected_label), unsafe_allow_html=True)
    m2.markdown("<div class='mini-card'><div class='mini-title'>Arquivo ativo</div><div class='mini-value'>{}</div></div>".format(info['file_name']), unsafe_allow_html=True)
    m3.markdown("<div class='mini-card'><div class='mini-title'>Janela do arquivo</div><div class='mini-value'>{} até {}</div></div>".format(format_date(min_date), format_date(max_date)), unsafe_allow_html=True)
    c1,c2,c3,c4,c5=st.columns(5)
    c1.markdown(card_html('Diário', daily, 'Leitura do dia selecionado'), unsafe_allow_html=True)
    c2.markdown(card_html('Semanal', weekly, 'Consolidação semanal'), unsafe_allow_html=True)
    c3.markdown(card_html('Mensal', monthly, 'Consolidação mensal'), unsafe_allow_html=True)
    c4.markdown(card_html('Anual', yearly, 'Ano até 12/12'), unsafe_allow_html=True)
    c5.markdown(card_html('YTD', ytd, 'Acumulado do ano'), unsafe_allow_html=True)
def render_data_ops(c):
    st.markdown("<div class='section-title'>Atualizar base do sistema</div>", unsafe_allow_html=True)
    st.markdown("<div class='soft-ribbon'><strong>Experiência simplificada:</strong> foco total no visual e na operação do arquivo. Basta selecionar a base e salvar.</div>", unsafe_allow_html=True)
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    uploaded=st.file_uploader('Base operacional atual (.xlsx, .xls ou .csv)', type=['xlsx','xls','csv'])
    if st.button('Salvar arquivo localmente', type='primary', use_container_width=True):
        if uploaded is None:
            st.error('Selecione um arquivo antes de salvar.')
            st.stop()
        try:
            raw=read_file(uploaded)
            ok, miss=validate_df(raw)
            if not ok:
                st.error('Base operacional inválida: ' + ', '.join(miss))
                st.stop()
            df=prepare(raw)
        except Exception as e:
            st.error('Erro ao ler a base operacional: {}'.format(e))
            st.stop()
        uid=create_upload(c, uploaded.name, len(df), message='Base recebida e salva localmente.')
        try:
            save_raw(c, uid, df)
            update_upload(c, uid, 'PROCESSADO', 'Base salva com sucesso.')
            st.success('Arquivo salvo com sucesso.')
            st.rerun()
        except Exception as e:
            update_upload(c, uid, 'ERRO', str(e))
            st.error('Erro ao salvar a base: {}'.format(e))
    st.markdown("</div>", unsafe_allow_html=True)

def render_history(c):
    st.markdown("<div class='section-title'>Histórico local</div>", unsafe_allow_html=True)
    df=uploads_table(c)
    if df.empty:
        st.markdown("<div class='panel'><div class='mini-title'>Sem histórico</div><div class='mini-value'>Os uploads processados aparecerão aqui</div></div>", unsafe_allow_html=True)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

def render_help():
    with st.expander('Sobre a versão V5.4', expanded=False):
        st.markdown("""
- Novo design com foco total em uma aparência mais limpa, premium e profissional.
- QG09 principal e QG07 opcional, sem misturar resultados.
- Consulta por anos, visão diária, semanal, mensal, anual e YTD.
- Armazenamento local simples para operação direta do arquivo.
- Navegador guarda apenas preferências leves de filtro para melhorar a experiência visual.
""")

def main():
    c=get_conn(); init_db(c)
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown("<div class='hero'><h1>RFT Automático — V5.4</h1><p>Uma versão redesenhada para priorizar uma experiência mais bonita, elegante e agradável de usar, mantendo os cálculos e a leitura por posto e por período.</p></div>", unsafe_allow_html=True)
    render_dashboard(c)
    st.divider(); render_data_ops(c)
    st.divider(); render_history(c)
    st.divider(); render_help()

if __name__ == '__main__':
    main()