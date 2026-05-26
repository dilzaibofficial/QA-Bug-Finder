@echo off
echo ============================================================
echo   AI Bug Detection — Model Training Pipeline
echo ============================================================
echo.

cd /d "d:\Zainab FYP\model_training"

echo [1/4] Installing requirements...
pip install -r requirements.txt -q
echo Done.
echo.

echo [2/4] Loading and preparing data...
python step1_load_data.py
if errorlevel 1 ( echo FAILED at Step 1 & pause & exit /b 1 )
echo.

echo [3/4] Training Defect Prediction Model (XGBoost)...
python step2_train_defect_model.py
if errorlevel 1 ( echo FAILED at Step 2 & pause & exit /b 1 )
echo.

echo [4/4] Training Bug Type + Severity Classifier...
python step3_train_bug_classifier.py
if errorlevel 1 ( echo FAILED at Step 3 & pause & exit /b 1 )
echo.

echo [5/5] Testing Predictor...
python step4_test_predictor.py
if errorlevel 1 ( echo FAILED at Step 4 & pause & exit /b 1 )
echo.

echo ============================================================
echo   ALL STEPS COMPLETE — Models saved in saved_models/
echo ============================================================
pause
