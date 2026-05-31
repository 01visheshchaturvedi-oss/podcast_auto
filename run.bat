@echo off
REM ========================================
REM  🎙️ Aakashvani - Emotional Hindi Podcast Generator
REM  Quick launcher for Windows
REM ========================================
echo.
echo   🎙️ Aakashvani - Emotional Hindi Podcast Generator
echo   =================================================
echo.

cd /d "%~dp0"

REM Check if user passed an argument
if "%1"=="" goto interactive
if "%1"=="--help" goto help
if "%1"=="-h" goto help

REM Run with arguments
echo Running with arguments: %*
C:\Users\sk\AppData\Local\Programs\Python\Python311\python.exe podcast_agent.py %*
if errorlevel 1 (
    echo.
    echo ❌ Error occurred! Check the output above.
    pause
)
goto end

:interactive
C:\Users\sk\AppData\Local\Programs\Python\Python311\python.exe podcast_agent.py
if errorlevel 1 (
    echo.
    echo ❌ Error occurred! Check the output above.
    pause
)
goto end

:help
echo.
echo Usage:
echo   run.bat                        Interactive mode
echo   run.bat --script script.txt    From labeled script file
echo   run.bat --text "Male:..."      Inline text
echo   run.bat --preview              Emotion analysis only
echo.
echo Options:
echo   --mode 1     Revision (fast)
echo   --mode 2     Learn (slow)
echo   --mode 3     Natural (default)
echo   --mode 4     Expressive (recommended)
echo   --name NAME  Output filename
echo   --no-mastering  Skip audio mastering
echo.
echo Examples:
echo   run.bat --script transcribe.txt --mode 4 --name mypodcast
echo   run.bat --text "Male: नमस्ते! Female: स्वागत है।"
echo.
pause

:end
