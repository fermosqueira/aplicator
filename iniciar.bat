@echo off
rem Levanta el servidor local del Aplicador. Dejalo abierto mientras navegues LinkedIn.
cd /d "%~dp0"
title Aplicador - servidor local
python servidor.py
echo.
echo El servidor se cerro. Apreta una tecla para salir.
pause >nul
