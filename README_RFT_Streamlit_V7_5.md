## RFT Qualidade - V7.5

Esta versão usa a base funcional da **V7.2**, que já contém:
- calendário restaurado
- aba de Tendências restaurada
- RFT completo (Diário, Semanal, Mensal, YTD e Anual)
- Rolling 12 separado em outra aba
- correção do bug de importação por ano
- gráfico mensal em colunas igual ao semanal
- gráfico Rolling 12 em colunas

### Como rodar
```bash
pip install -r requirements.txt
streamlit run app_rft_streamlit_v7_5.py
```

> Importante: mantenha o arquivo `app_rft_streamlit_v7_2.py` na mesma pasta, pois a V7.5 chama a implementação principal dessa versão.
