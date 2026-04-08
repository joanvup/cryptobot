# strategy/ai_model.py
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
import joblib
import os
import logging
from config.settings import settings

logger = logging.getLogger(__name__)

class CryptoAIModel:
    def __init__(self, model_path=None):
        self.model_path = model_path or settings.MODEL_PATH
        self.model = None
        # Características que la IA analizará (Features)
        self.features = ['rsi', 'ema_20', 'ema_50', 'rel_volume', 'atr']

    def train(self, csv_path: str):
        """Entrena el modelo XGBoost con los datos consolidados."""
        if not os.path.exists(csv_path):
            return "Error: Archivo de datos no encontrado."

        df = pd.read_csv(csv_path).dropna()
        if len(df) < 100:
            return "Error: Datos insuficientes para un entrenamiento fiable."

        X = df[self.features]
        y = df['target']

        # Split 80/20
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # Configuración de clasificación profesional
        self.model = xgb.XGBClassifier(
            n_estimators=200,      # Aumentado para manejar datasets más grandes (5000 velas)
            max_depth=6,           # Mayor profundidad para captar patrones complejos
            learning_rate=0.05,    # Más lento para evitar overfitting
            objective='binary:logistic',
            random_state=42
        )

        self.model.fit(X_train, y_train)
        
        # Persistencia del modelo
        model_dir = os.path.dirname(self.model_path)
        if model_dir and not os.path.exists(model_dir):
            os.makedirs(model_dir)
            
        joblib.dump(self.model, self.model_path)
        
        accuracy = self.model.score(X_test, y_test)
        return f"Entrenamiento Exitoso. Precisión: {accuracy:.2f}"

    def predict_probability(self, current_features_df: pd.DataFrame) -> float:
        """Realiza la inferencia de probabilidad (0.0 a 1.0)."""
        try:
            if self.model is None:
                if os.path.exists(self.model_path):
                    self.model = joblib.load(self.model_path)
                else:
                    return 0.5 # Neutralidad si no hay cerebro entrenado

            X = current_features_df[self.features]
            # Obtenemos la probabilidad de la clase 1 (Ganador)
            probs = self.model.predict_proba(X)
            return float(probs[0][1])
        except Exception as e:
            logger.error(f"Error en inferencia IA: {e}")
            return 0.5