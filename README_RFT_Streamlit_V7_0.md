
## RFT Qualidade - V7.0

Versao com design corporativo escuro, meta de RFT configuravel, consolidacao de multiplos uploads e governanca do historico.

### Inclui
- Modo de importacao:
  - Somar ao historico
  - Substituir periodo sobreposto
  - Reprocessar o ano inteiro
- Aviso de sobreposicao de datas ja existentes
- Indicadores de base:
  - data minima e maxima
  - ultima data com dado
  - dias cobertos
  - uploads consolidados
  - status da base (Atualizada, Parcial, Defasada)
- Acoes no historico:
  - excluir upload especifico
  - reprocessar upload
  - ver detalhes do upload
- Tendencia com:
  - linha de meta mais visivel
  - grafico por performance
  - marcador de melhor e pior periodo
  - comparacao mes atual vs mes anterior
  - acumulado do ano
  - variacao em p.p., setas e status visual
- Identidade da area: Qualidade

### Como rodar
```bash
pip install -r requirements_v7_0.txt
streamlit run app_rft_streamlit_v7_0.py
```
