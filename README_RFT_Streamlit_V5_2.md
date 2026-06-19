
# RFT Automático — V5.2

Versão **híbrida leve** para uso apenas com Streamlit:

- visual bonito
- QG09 principal e QG07 opcional
- anos 2025/2026
- semanal / mensal / anual / YTD
- tentativa de salvar localmente no app (SQLite local)
- reforço leve no navegador (local storage) **somente para filtros e seleções**
- anual considera **12/12** como ano finalizado

## Como rodar

```bash
pip install -r requirements_v5_2.txt
streamlit run app_rft_streamlit_v5_2.py
```

## Importante

Esta versão é a melhor alternativa possível usando **somente Streamlit**, mas:

- o Streamlit Community Cloud **não garante persistência local definitiva**
- o local storage do navegador ajuda a lembrar seleções do **mesmo navegador**, mas **não compartilha dados com outras pessoas**
- o arquivo completo **não é salvo no navegador** para evitar peso e lentidão
