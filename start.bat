@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Telegram Photo Bot

echo ==========================================
echo       Запуск Telegram Photo Bot
echo ==========================================

if not exist .env (
    echo [!] Файл .env не найден. Создаю копию из .env.example...
    copy .env.example .env > nul
    echo [!] Откройте файл .env и укажите BOT_TOKEN и ADMIN_ID.
    pause
    exit /b
)

echo Запуск бота через Python venv...
echo Для остановки бота закройте это окно или нажмите Ctrl+C.
echo.

.\venv\Scripts\python.exe bot.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Бот завершил работу с кодом ошибки %ERRORLEVEL%.
    pause
)
pause
