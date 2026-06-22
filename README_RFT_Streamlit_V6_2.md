## RFT Automatico - V6.2

Versao com design corporativo escuro, meta de RFT configuravel e consolidacao de multiplos uploads sem perder o historico anterior.

### Estrutura da versao
- Tema corporativo escuro
- Meta de RFT configuravel na sidebar
- Regra visual aplicada conforme solicitado:
  - RFT igual ou menor que a meta = verde
  - RFT acima da meta = vermelho
- Dashboard com KPIs executivos
- Aba de Tendencia mantida
- Aba Operacional removida
- Multiplos uploads sao preservados; registros sobrepostos sao consolidados mantendo o registro mais recente para a mesma WO + data/hora + posto

### Como rodar
```bash
pip install -r requirements_v6_2.txt
streamlit run app_rft_streamlit_v6_2.py
```
