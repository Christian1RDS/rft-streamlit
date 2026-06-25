
# RFT Automatico - V9.7

Versão consolidada para facilitar o deploy.

Principais pontos:
- Pareto de Falhas sem `matplotlib`
- gráficos nativos do Streamlit
- Top 10 falhas por QG09 ou QG07
- demais postos ignorados
- detecção automática ou seleção manual da coluna de falha no upload
- calendário, YTD, upload e histórico mantidos
- cálculo anual corrigido: fechamento a partir de 10/12 até o último dia trabalhado de dezembro

## Deploy simples

Na raiz do GitHub deixe somente o essencial:

```text
app_rft_streamlit_v9_7.py
requirements.txt
```

Main file path no Streamlit Cloud:

```text
app_rft_streamlit_v9_7.py
```

## Como rodar localmente

```bash
pip install -r requirements.txt
streamlit run app_rft_streamlit_v9_7.py
```
