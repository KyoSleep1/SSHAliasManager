@echo off
setlocal EnableExtensions DisableDelayedExpansion
py -3 "%~dp0ssh_aliases.py" %*
exit /b %errorlevel%
