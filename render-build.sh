#!/bin/bash
set -e

echo "=== Installing backend dependencies ==="
pip install -r backend/requirements.txt

echo "=== Installing ML training dependencies ==="
pip install -r model_training/requirements.txt

echo "=== Retraining models on this environment ==="
cd model_training

# Step 1: Load and prepare data
python step1_load_data.py

# Step 5: Train best defect model (Ensemble: XGBoost + RF + GB)
python step5_improve_model.py

# Step 3: Train bug type classifier
python step3_train_bug_classifier.py

echo "=== Models trained and saved ==="
cd ..
