# Streamlit Cloud fix

If you deploy on Streamlit Community Cloud, keep a file named `requirements.txt` in the repository root (or in the same folder as the app entrypoint) so dependencies are installed automatically.

This fix file contains:
- streamlit
- pandas
- openpyxl
- xlrd
- streamlit-local-storage
- matplotlib
