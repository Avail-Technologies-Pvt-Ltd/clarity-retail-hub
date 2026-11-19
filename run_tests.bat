@echo off
TITLE Clarity Retail Hub - Automated Test Suite Runner
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================================
echo      CLARITY RETAIL HUB - AUTOMATED TEST SUITE RUNNER
echo ============================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please ensure Python 3.10+ is installed.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%p in ('python --version 2^>^&1') do set "PY_VER=%%p"
echo [ENV] Python      : %PY_VER%
echo [ENV] Settings    : retail_hub.settings_test (Fast Standalone SQLite)
echo [ENV] Project Dir : %CD%
echo.

echo ------------------------------------------------------------
echo  SELECT TEST SUITE TO EXECUTE:
echo ------------------------------------------------------------
echo   [0] FULL Test Suite (All 20 tests across all apps - default)
echo.
echo   [1] Branches (Single Main Branch, Hardware Locks, Edit Workbench)
echo.
echo   [2] Sync Gateway (Anti-Theft Hardware Bind, Transfer Buffer Ingestion)
echo.
echo   [3] Reports (Daily, Weekly, Monthly, Annual, Cashflow ^& Stock Matrix)
echo.
echo   [4] Subscriptions (60-Day Grace ^& 2-Stage Expiry Protocol)
echo.
echo   [5] Tenants (Subdomain Routing, SSO Handover, Workspace Portals)
echo ------------------------------------------------------------
echo.

set "CHOICE=0"
if not "%~1"=="" (
    set "CHOICE=%~1"
) else (
    set /p "CHOICE=Enter selection [0-4, Press Enter for default]: "
)
if "!CHOICE!"=="" set "CHOICE=0"

set "TARGET_APP="
if "!CHOICE!"=="0" (
    set "TARGET_NAME=FULL RETAIL HUB SYSTEM TEST SUITE"
    set "TARGET_APP=tenants branches sync_gateway reports subscriptions"
) else if "!CHOICE!"=="1" (
    set "TARGET_NAME=Branches & Main Branch Authority"
    set "TARGET_APP=branches"
) else if "!CHOICE!"=="2" (
    set "TARGET_NAME=Sync Gateway & Inter-Branch Buffer"
    set "TARGET_APP=sync_gateway"
) else if "!CHOICE!"=="3" (
    set "TARGET_NAME=Reports & Live Stock Matrix"
    set "TARGET_APP=reports"
) else if "!CHOICE!"=="4" (
    set "TARGET_NAME=Subscriptions & Grace Periods"
    set "TARGET_APP=subscriptions"
) else if "!CHOICE!"=="5" (
    set "TARGET_NAME=Tenants & Subdomain Routing"
    set "TARGET_APP=tenants"
) else (
    echo [ERROR] Invalid selection "!CHOICE!".
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   EXECUTING: !TARGET_NAME!
echo   Target Apps: !TARGET_APP!
echo ============================================================
echo.

python manage.py test !TARGET_APP! --settings=retail_hub.settings_test --verbosity=2
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if %EXIT_CODE% equ 0 (
    echo ============================================================
    echo   [SUCCESS] ALL TESTS COMPLETED SUCCESSFULLY!
    echo ============================================================
) else (
    echo ============================================================
    echo   [FAILURE] TEST SUITE ENCOUNTERED FAILURES (Code: %EXIT_CODE%)
    echo ============================================================
)
echo.
exit /b %EXIT_CODE%
