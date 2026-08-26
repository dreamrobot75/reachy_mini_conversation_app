@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_sim_mujoco.ps1"
if %errorlevel% neq 0 pause
