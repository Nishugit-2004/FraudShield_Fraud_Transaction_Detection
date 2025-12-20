from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import numpy as np
import pandas as pd
import joblib
import os
import random
from typing import Dict



class DummyScaler:
    def transform(self, X):
        return np.array(X).astype(float)

class DummyModel:
    def predict(self, X):
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        amounts = X[:, 1]
        return (amounts > 100000).astype(int)

    def predict_proba(self, X):
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        amounts = X[:, 1]
        max_amt = amounts.max() if amounts.max() > 0 else 1.0
        probs = np.clip(amounts / (max_amt * 1.2), 0, 1)
        return np.vstack([1 - probs, probs]).T

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "fraud_detector_best.pkl")
SCALER_PATH = os.path.join(BASE_DIR, "scaler.pkl")

# print("Looking for model at:", os.path.abspath(MODEL_PATH))
# print("Looking for scaler at:", os.path.abspath(SCALER_PATH))


try:
    if os.path.exists(MODEL_PATH):
        model = joblib.load(MODEL_PATH)
    else:
        raise FileNotFoundError
    if os.path.exists(SCALER_PATH):
        scaler = joblib.load(SCALER_PATH)
    else:
        raise FileNotFoundError
    print("✅ Loaded model and scaler from disk.")
except Exception as e:
    print(f"⚠️ Failed to load model/scaler: {e}")
    model = DummyModel()
    scaler = DummyScaler()



class UPITransactionSimulator:
    def _prepare_features(self, transaction):
        df = pd.DataFrame([{
            'step': transaction['step'],
            'amount': transaction['amount'],
            'oldbalanceOrg': transaction['oldbalanceOrg'],
            'newbalanceOrig': transaction['newbalanceOrig'],
            'oldbalanceDest': transaction['oldbalanceDest'],
            'newbalanceDest': transaction['newbalanceDest']
        }])
        type_cols = ['type_CASH_OUT','type_DEBIT','type_PAYMENT','type_TRANSFER']
        for c in type_cols:
            df[c] = 0
        tcol = f"type_{transaction['type']}"
        if tcol in type_cols:
            df[tcol] = 1
        feature_order = ['step','amount','oldbalanceOrg','newbalanceOrig','oldbalanceDest','newbalanceDest'] + type_cols
        return df[feature_order]

    def predict_transaction(self, transaction):
        features = self._prepare_features(transaction)
        scaled = scaler.transform(features)
        pred = model.predict(scaled)[0]
        try:
            prob = float(model.predict_proba(scaled)[0][1])
        except Exception:
            prob = 0.99 if pred == 1 else 0.01
        return int(pred), float(prob)

    def enhanced_fraud_detection(self, transaction):
        ml_pred, ml_prob = self.predict_transaction(transaction)
        amount = transaction['amount']
        new_bal_orig = transaction['newbalanceOrig']
        old_bal_dest = transaction['oldbalanceDest']
        new_bal_dest = transaction['newbalanceDest']
        ttype = transaction['type']

        if new_bal_orig / (new_bal_orig + amount ) < 0.1:
            return True, max(0.92, ml_prob), "🚨 Rule: Account drained"
        if old_bal_dest == 0 and new_bal_dest == 0:
            return True, max(0.88, ml_prob), "🚨 Rule: Money disappeared"
        if new_bal_dest == 0 and old_bal_dest < amount * 0.1:
            return True, max(0.85, ml_prob), "🚨 Rule: Rapid transfer detected"
        if amount > 300000 and ttype in ['TRANSFER', 'CASH_OUT']:
            return True, max(0.80, ml_prob), "⚠️ Rule: Large amount alert"
        if ml_prob > 0.70:
            return True, ml_prob, "🤖 ML Model: High risk"
        if ml_prob > 0.15 and amount > 100000:
            return True, ml_prob, "⚠️ Hybrid: Medium risk + large amount"
        return False, ml_prob, "✅ Legitimate"


app = FastAPI(
    title="UPI Fraud Detection API",
    description="Predicts if a UPI transaction is fraudulent using ML + rule-based logic.",
    version="1.0.0"
)

sim = UPITransactionSimulator()



class TransactionInput(BaseModel):
    step: int
    type: str
    amount: float
    nameOrig: str
    oldbalanceOrg: float
    newbalanceOrig: float
    nameDest: str
    oldbalanceDest: float
    newbalanceDest: float



@app.post("/predict")
def predict_fraud(transaction: TransactionInput):
    try:
        trans_dict = transaction.dict()
        is_fraud, prob, reason = sim.enhanced_fraud_detection(trans_dict)
        return {
            "fraudulent": bool(is_fraud),
            "probability": round(prob, 4),
            "reason": reason,
            "details": trans_dict
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return {
        "message": "UPI Fraud Detection API",
        "usage": "POST /predict with transaction JSON to get fraud prediction."
    }
