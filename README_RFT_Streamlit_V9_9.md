# RFT Automatico - V9.9

Versão com Pareto de Falhas corrigido.

Inclui:
- Pareto real com Top 10 ordenado por quantidade decrescente
- filtro de período por data inicial e data final
- filtro por posto QG09 ou QG07
- demais postos ignorados
- barras de quantidade e linha de % acumulado usando gráficos nativos do Streamlit
- detecção automática ou seleção manual da coluna de falha no upload
- sem dependência de matplotlib

## Deploy simples

Na raiz do GitHub deixe:

```text
app_rft_streamlit_v9_9.py
requirements.txt
```

Main file path no Streamlit Cloud:

```text
app_rft_streamlit_v9_9.py
```
