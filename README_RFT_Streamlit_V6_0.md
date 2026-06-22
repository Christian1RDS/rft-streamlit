## RFT Automático — V6.0

Versão com **design corporativo escuro**, estrutura mais organizada e experiência visual premium para consulta do RFT.

### Destaques da V6.0
- Layout corporativo, moderno e não totalmente branco
- Sidebar organizada para filtros de posto, ano e período
- Cards executivos para RFT diário, semanal, mensal, anual e YTD
- Tendência mensal e visão diária do período selecionado
- Consolidação por WO com opção de download em CSV
- Fluxo pensado para **GitHub + Streamlit Community Cloud**

### Como rodar localmente
```bash
pip install -r requirements_v6_0.txt
streamlit run app_rft_streamlit_v6_0.py
```

### Colunas obrigatórias da base
- `NR_WO`
- `DT_HR_INSPECAO`
- `C_DPU_QG_AMARELO`
- `CD_POSTO_CN`

### Observação
A V6.0 continua usando banco SQLite local (`rft_v60_local.db`) para facilitar o uso imediato. Em uma próxima evolução corporativa, o ideal é conectar um banco externo para persistência centralizada.
