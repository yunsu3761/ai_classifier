@echo off
cd /d D:\TAXOADAPT
call .venv\Scripts\activate.bat
echo.
echo ============================================
echo   TaxoAdapt Web Interface Starting...
echo ============================================
echo.
echo Server available at:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr "IPv4"') do echo   http://%%a:8501
echo.
streamlit run web_interface.py --server.address 0.0.0.0 --server.port 8501
pause
