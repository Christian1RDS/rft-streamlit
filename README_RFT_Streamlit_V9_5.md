
# RFT Automatico - V9.5

Versão com refinamento visual corporativo e regra visual ajustada.

Mantém:
- calendário e modos Diário / Semanal / Mensal / Anual
- RFT YTD no dashboard
- gráfico mensal da aba Tendência em barras/colunas, igual ao semanal
- fluxo corrigido de upload na aba Base & Upload
- blocos Meta x resultado, Resumo executivo do recorte e Leitura diária do RFT no Dashboard

Regra visual da V9.5:
- abaixo da meta = vermelho
- acima ou igual à meta = verde

## Como rodar
```bash
pip install -r requirements_v9_5.txt
streamlit run app_rft_streamlit_v9_5.py
```
