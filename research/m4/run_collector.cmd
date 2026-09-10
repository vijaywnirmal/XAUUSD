@echo off
cd /d C:\Users\Vijay\Downloads\XAUUSD
echo ==================== %DATE% %TIME% ==================== >> research\m4\paper_run.log
python -m data_pipeline.topup_bars_pg >> research\m4\paper_run.log 2>&1
python -m research.m4.primary_lead_signal --since 2026-09-11 >> research\m4\paper_run.log 2>&1
echo.>> research\m4\paper_run.log
