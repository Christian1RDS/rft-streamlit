import io
import sqlite3
from datetime import date, datetime, time, timedelta
from calendar import monthrange
import pandas as pd
import streamlit as st

st.set_page_config(page_title='RFT Automático — V4.4', page_icon='📊', layout='wide')
DB='rft_v44.db'
REQ=['NR_WO','DT_HR_INSPECAO','C_DPU_QG_AMARELO','CD_POSTO_CN']
POSTOS=['QG09','QG07']

def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db(c):
    c.execute('CREATE TABLE IF NOT EXISTS upload_log (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL, uploaded_at TEXT NOT NULL, total_rows INTEGER NOT NULL, status TEXT NOT NULL, message TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS raw_inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, nr_wo TEXT, dt_hr_inspecao TEXT, c_dpu_qg_amarelo REAL, cd_posto_cn TEXT)')
    c.commit()

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
                        df=pd.read_csv(io.BytesIO(b),encoding=enc,sep=None,engine='python')
                    else:
                        df=pd.read_csv(io.BytesIO(b),encoding=enc,sep=sep)
                    return normalize_columns(df)
                except Exception as e:
                    last_err=e
        raise ValueError(f'Não foi possível ler o CSV. Detalhe: {last_err}')
    if ext in ['xlsx','xls']:
        engine='openpyxl' if ext=='xlsx' else 'xlrd'
        return normalize_columns(pd.read_excel(io.BytesIO(b),engine=engine))
    raise ValueError('Formato não suportado. Use .xlsx, .xls ou .csv')

def validate_df(df):
    missing=[c for c in REQ if c not in df.columns]
    return len(missing)==0, missing

def parse_dt(s):
    dt=pd.to_datetime(s,errors='coerce')
    mask=dt.isna() & s.notna()
    if mask.any():
        dt.loc[mask]=pd.to_datetime(s[mask],errors='coerce',dayfirst=True)
    return dt

def norm_posto(v):
    txt=str(v).upper().strip()
    if 'QG09' in txt: return 'QG09'
    if 'QG07' in txt: return 'QG07'
    return txt

def prepare(df):
    w=df.copy()
    w['DT_HR_INSPECAO']=parse_dt(w['DT_HR_INSPECAO'])
    w['C_DPU_QG_AMARELO']=pd.to_numeric(w['C_DPU_QG_AMARELO'],errors='coerce').fillna(0)
    w['NR_WO']=w['NR_WO'].astype(str).str.strip()
    w['CD_POSTO_CN']=w['CD_POSTO_CN'].astype(str).map(norm_posto)
    return w[w['DT_HR_INSPECAO'].notna()].copy()

def create_upload(c,file_name,total_rows,status="RECEBIDO",message=""):
    cur=c.execute('INSERT INTO upload_log (file_name, uploaded_at, total_rows, status, message) VALUES (?, ?, ?, ?, ?)', (file_name, datetime.now().isoformat(timespec='seconds'), int(total_rows), status, message))
    c.commit(); return int(cur.lastrowid)

def update_upload(c,upload_id,status,message=""):
    c.execute('UPDATE upload_log SET status=?, message=? WHERE id=?',(status,message,upload_id))
    c.commit()

def save_raw(c,upload_id,df):
    rows=[]
    for _,r in df.iterrows():
        rows.append((upload_id, r['NR_WO'], r['DT_HR_INSPECAO'].isoformat(sep=' ', timespec='seconds'), float(r['C_DPU_QG_AMARELO']), r['CD_POSTO_CN']))
    c.executemany('INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn) VALUES (?, ?, ?, ?, ?)', rows)
    c.commit()

def uploads_table(c):
    return pd.read_sql_query('SELECT id, file_name, uploaded_at, total_rows, status, message FROM upload_log ORDER BY id DESC LIMIT 300', c)

def latest_upload_id_for_year(c, posto, year):
    q="SELECT MAX(upload_id) AS upload_id FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?"
    df=pd.read_sql_query(q,c,params=[posto,str(year)])
    if df.empty or pd.isna(df.loc[0,'upload_id']): return None
    return int(df.loc[0,'upload_id'])

def available_years(c, posto):
    q="SELECT DISTINCT CAST(strftime('%Y', dt_hr_inspecao) AS INT) AS ano FROM raw_inspections WHERE cd_posto_cn=? ORDER BY ano"
    df=pd.read_sql_query(q,c,params=[posto])
    return [int(x) for x in df['ano'].dropna().tolist()] if not df.empty else []

def upload_info(c, upload_id):
    c.row_factory=sqlite3.Row
    return c.execute('SELECT * FROM upload_log WHERE id=?',(upload_id,)).fetchone()

def load_upload_df(c, upload_id):
    df=pd.read_sql_query('SELECT nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE upload_id=?', c, params=[upload_id])
    if not df.empty:
        df['DT_HR_INSPECAO']=pd.to_datetime(df['DT_HR_INSPECAO'],errors='coerce')
        df['C_DPU_QG_AMARELO']=pd.to_numeric(df['C_DPU_QG_AMARELO'],errors='coerce').fillna(0)
        df['CD_POSTO_CN']=df['CD_POSTO_CN'].astype(str).map(norm_posto)
    return df

def calc_rft(df,start_date,end_date):
    sdt=datetime.combine(start_date,time(0,0,0)); edt=datetime.combine(end_date,time(23,59,59))
    f=df[(df['DT_HR_INSPECAO']>=sdt)&(df['DT_HR_INSPECAO']<=edt)].copy()
    if f.empty: return {"rft_pct":None,"total":0,"good":0,"bad":0}
    grp=f.groupby('NR_WO',as_index=False)['C_DPU_QG_AMARELO'].sum().rename(columns={'C_DPU_QG_AMARELO':'SOMA'})
    grp['RFT']=(grp['SOMA']==0).astype(int)
    total=int(len(grp)); good=int(grp["RFT"].sum()); bad=int(total-good)
    pct=round((good/total)*100,2) if total else None
    return {"rft_pct":pct,"total":total,"good":good,"bad":bad}

def is_full_year(df, year):
    ydf=df[df['DT_HR_INSPECAO'].dt.year==year]
    if ydf.empty: return False, f"Sem dados de {year}."
    min_d=ydf['DT_HR_INSPECAO'].dt.date.min(); max_d=ydf['DT_HR_INSPECAO'].dt.date.max()
    complete=(min_d<=date(year,1,1)) and (max_d>=date(year,12,31))
    if complete: return True, f"Ano {year} completo no arquivo."
    return False, f"Ano {year} incompleto ({min_d.strftime('%d/%m/%Y')} a {max_d.strftime('%d/%m/%Y')})."

def week_options(df, year):
    ydf=df[df['DT_HR_INSPECAO'].dt.year==year].copy()
    if ydf.empty: return []
    dates=sorted(ydf['DT_HR_INSPECAO'].dt.date.unique().tolist())
    mondays=sorted({d-timedelta(days=d.weekday()) for d in dates})
    opts=[]
    for i,monday in enumerate(mondays, start=1):
        sunday=monday+timedelta(days=6)
        label=f'Semana {i} — {monday.strftime('%d/%m/%Y')} a {sunday.strftime('%d/%m/%Y')}'
        opts.append((label,monday,sunday))
    return opts

def month_options(df, year):
    ydf=df[df['DT_HR_INSPECAO'].dt.year==year].copy()
    if ydf.empty: return []
    opts=[]
    for m in sorted(ydf['DT_HR_INSPECAO'].dt.month.unique().tolist()):
        start=date(year,int(m),1); end=date(year,int(m),monthrange(year,int(m))[1])
        label=f'{start.strftime('%m/%Y')} — {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}'
        opts.append((label,start,end))
    return opts

def format_pct(v):
    return 'Sem dados' if v is None or pd.isna(v) else f'{v:.2f}'.replace('.', ',') + '%' 

def format_date(d):
    return '-' if d is None else d.strftime('%d/%m/%Y')

def card(title,value,subtitle=""):
    return f"**{title}**\n\n### {value}\n{subtitle}"

def render_panel(title,result,subtitle=""):
    if result is None:
        return card(title,'Sem dados',subtitle)
    sub=f"{subtitle} | WOs boas: {result['good']} | ruins: {result['bad']} | total: {result['total']}"
    return card(title, format_pct(result['rft_pct']), sub)

def render_dashboard(c):
    posto=st.radio('Posto para cálculo do RFT', POSTOS, index=0, horizontal=True)
    anos=available_years(c, posto)
    if not anos:
        st.info(f'Ainda não existem dados salvos de {posto}. Faça upload de um arquivo para iniciar.')
        return
    idx=anos.index(2025) if 2025 in anos else len(anos)-1
    ano=st.selectbox('Ano salvo para consulta', anos, index=idx)
    upload_id=latest_upload_id_for_year(c, posto, ano)
    if upload_id is None:
        st.warning(f'Não há upload salvo para {posto} em {ano}.')
        return
    info=upload_info(c, upload_id)
    df_all=load_upload_df(c, upload_id)
    df=df_all[(df_all['CD_POSTO_CN']==posto) & (df_all['DT_HR_INSPECAO'].dt.year==ano)].copy()
    if df.empty:
        st.warning(f'Não há dados de {posto} em {ano} no upload selecionado.')
        return
    min_date=df['DT_HR_INSPECAO'].dt.date.min(); max_date=df['DT_HR_INSPECAO'].dt.date.max()
    st.subheader('Seleção por período')
    mode=st.radio('Escolha o período que você quer visualizar', ['Diário','Semanal','Mensal','Anual'], horizontal=True)
    daily=weekly=monthly=yearly=ytd=None
    context=""
    if mode=='Diário':
        selected=st.date_input('Clique no dia que você quer ver', value=max_date, min_value=min_date, max_value=max_date, format='DD/MM/YYYY', key='day_v44')
        daily=calc_rft(df, selected, selected)
        ws=selected-timedelta(days=selected.weekday()); we=ws+timedelta(days=6)
        weekly=calc_rft(df, ws, we)
        ms=date(ano, selected.month, 1); me=date(ano, selected.month, monthrange(ano, selected.month)[1])
        monthly=calc_rft(df, ms, me)
        ok, note=is_full_year(df, ano)
        yearly=calc_rft(df, date(ano,1,1), date(ano,12,31)) if ok else {"rft_pct":None,"total":0,"good":0,"bad":0,"note":note}
        ytd=calc_rft(df, date(ano,1,1), selected)
        context=f'Dia selecionado: {format_date(selected)}'
    elif mode=='Semanal':
        opts=week_options(df, ano)
        labels=[x[0] for x in opts]
        label=st.selectbox('Semana do ano', labels, index=len(labels)-1)
        selected=next(x for x in opts if x[0]==label)
        ws,we=selected[1],selected[2]
        weekly=calc_rft(df, ws, we)
        ytd=calc_rft(df, date(ano,1,1), we if we<=max_date else max_date)
        ok, note=is_full_year(df, ano)
        yearly=calc_rft(df, date(ano,1,1), date(ano,12,31)) if ok else {"rft_pct":None,"total":0,"good":0,"bad":0,"note":note}
        context=f'Semana selecionada: {label}'
    elif mode=='Mensal':
        opts=month_options(df, ano)
        labels=[x[0] for x in opts]
        label=st.selectbox('Mês do ano', labels, index=len(labels)-1)
        selected=next(x for x in opts if x[0]==label)
        ms,me=selected[1],selected[2]
        monthly=calc_rft(df, ms, me)
        ytd=calc_rft(df, date(ano,1,1), me if me<=max_date else max_date)
        ok, note=is_full_year(df, ano)
        yearly=calc_rft(df, date(ano,1,1), date(ano,12,31)) if ok else {"rft_pct":None,"total":0,"good":0,"bad":0,"note":note}
        context=f'Mês selecionado: {label}'
    else:
        ok, note=is_full_year(df, ano)
        yearly=calc_rft(df, date(ano,1,1), date(ano,12,31)) if ok else {"rft_pct":None,"total":0,"good":0,"bad":0,"note":note}
        ytd=calc_rft(df, date(ano,1,1), max_date)
        context=f'Ano selecionado: {ano}'
    st.subheader('Painel do período selecionado')
    st.markdown(f"<span class='chip'><strong>Arquivo:</strong> {info['file_name']}</span><span class='chip'><strong>Upload salvo:</strong> {info['uploaded_at']}</span><span class='chip'><strong>Posto:</strong> {posto}</span><span class='chip'><strong>Ano salvo:</strong> {ano}</span><span class='chip'><strong>{context}</strong></span><span class='chip'><strong>Período disponível:</strong> {format_date(min_date)} a {format_date(max_date)}</span>", unsafe_allow_html=True)
    cols=st.columns(5)
    cols[0].markdown(render_panel('Diário', daily, 'Dia escolhido'))
    cols[1].markdown(render_panel('Semanal', weekly, 'Semana correspondente'))
    cols[2].markdown(render_panel('Mensal', monthly, 'Mês correspondente'))
    if yearly is not None and yearly.get('rft_pct') is None and 'note' in yearly:
        cols[3].markdown(card('Anual','Ano incompleto', yearly['note']))
    else:
        cols[3].markdown(render_panel('Anual', yearly, f'Ano {ano}'))
    cols[4].markdown(render_panel('YTD', ytd, 'Acumulado no ano selecionado'))

def render_imports(c):
    st.subheader('Salvar novo arquivo')
    st.caption('Cada arquivo salvo fica disponível para consulta posterior. Você poderá voltar para 2025 e depois retornar para 2026 quando quiser.')
    current_file=st.file_uploader('Base operacional atual (.xlsx, .xls ou .csv)', type=['xlsx','xls','csv'])
    if st.button('💾 Salvar arquivo e atualizar histórico', type='primary', use_container_width=True):
        if current_file is None:
            st.error('Selecione a base operacional atual antes de salvar.'); st.stop()
        try:
            raw=read_file(current_file)
            ok, miss=validate_df(raw)
            if not ok:
                st.error('Base operacional inválida: ' + ', '.join(miss)); st.stop()
            df=prepare(raw)
        except Exception as e:
            st.error(f'Erro ao ler a base operacional: {e}'); st.stop()
        uid=create_upload(c, current_file.name, len(df), message='Base recebida.')
        try:
            save_raw(c, uid, df)
            update_upload(c, uid, 'PROCESSADO', 'Base salva com sucesso.')
            st.success('Arquivo salvo com sucesso. Agora os anos contidos nele ficam disponíveis para consulta futura.'); st.rerun()
        except Exception as e:
            update_upload(c, uid, 'ERRO', str(e)); st.error(f'Erro ao salvar a base: {e}')

def render_history(c):
    st.subheader('Histórico de arquivos salvos')
    df=uploads_table(c)
    if df.empty:
        st.info('Ainda não existe upload salvo.')
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

def render_help():
    with st.expander('Como esta versão funciona', expanded=False):
        st.markdown('''- Você envia **arquivos separados ao longo do tempo** e o app **salva todos** no histórico.
- O app usa **somente os dados de QG09 e QG07**; os demais postos são ignorados.
- **QG09 é o principal**, mas você pode alternar para **QG07** sem misturar os resultados.
- Existe um seletor de **Ano salvo para consulta**, então você pode voltar para **2025** e depois retornar para **2026** quando quiser.
- No modo **Semanal**, existe um seletor separado com **Semana 1, Semana 2, Semana 3...** com base nas semanas disponíveis do ano salvo.
- No modo **Mensal**, existe um seletor separado para o mês do ano salvo.
- O **RFT anual** só é calculado se o ano estiver completo; caso contrário, o sistema mostra **Ano incompleto**.''')

def main():
    c=get_conn(); init_db(c)
    st.markdown("<div class='hero'><h1>RFT Automático — V4.4</h1><p>Versão ajustada para salvar todos os arquivos por ano, permitir alternância livre entre 2025 e 2026, separar QG09 e QG07 e oferecer filtro de semanas do ano.</p></div>", unsafe_allow_html=True)
    render_dashboard(c)
    st.divider(); render_imports(c)
    st.divider(); render_history(c)
    st.divider(); render_help()

if __name__ == '__main__':
    main()