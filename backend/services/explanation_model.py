import lightgbm as lgb
import shap
import pandas as pd
import numpy as np
from typing import List, Dict, Any

class ExplanationModel:
    """
    Un wrapper para un modelo LightGBM y un explicador SHAP.
    Este modelo se entrena para predecir la puntuación de similitud semántica
    basándose en características de coincidencia de entidades (NER).
    Luego, utiliza SHAP para explicar las predicciones.
    """
    def __init__(self):
        self.model = lgb.LGBMRegressor(
            objective='regression_l1',
            n_estimators=100,
            learning_rate=0.1,
            num_leaves=20,
            min_child_samples=1, # CRITICAL for small datasets (default is 20)
            min_data_in_bin=1,   # CRITICAL for small datasets
            random_state=42,
            verbose=-1
        )
        self.explainer = None
        self.feature_names = []

    def train(self, training_data: List[Dict[str, Any]]):
        """
        Entrena el modelo LGBM con los datos proporcionados.

        Args:
            training_data: Una lista de diccionarios, donde cada uno contiene
                           las características (ej. 'area_match_count') y el
                           objetivo ('target').
        """
        if not training_data:
            return

        df = pd.DataFrame(training_data)
        
        # Asegurarse de que todas las columnas de características esperadas existan
        expected_features = [
            'area_match_count', 'lenguaje_match_count', 'herramienta_match_count',
            'metodologia_match_count', 'contenido_match_count', 'history_score',
            'semantic_score' # ADDED
        ]
        for col in expected_features:
            if col not in df.columns:
                df[col] = 0
        
        X = df[expected_features]
        y = df['target']
        
        self.feature_names = X.columns.tolist()
        
        self.model.fit(X, y)
        self.explainer = shap.TreeExplainer(self.model)

    def explain(self, prediction_data: pd.DataFrame) -> List[Dict[str, float]]:
        """
        Genera explicaciones SHAP para un conjunto de datos de predicción.

        Args:
            prediction_data: Un DataFrame de pandas con las mismas características
                             que los datos de entrenamiento.

        Returns:
            Una lista de diccionarios, donde cada diccionario mapea nombres de
            características a sus valores SHAP para una recomendación.
        """
        if self.explainer is None or prediction_data.empty:
            return [{} for _ in range(len(prediction_data))]

        # Asegurarse de que las columnas están en el mismo orden que en el entrenamiento
        prediction_data = prediction_data[self.feature_names]

        shap_values = self.explainer.shap_values(prediction_data)

        explanations = []
        for i in range(len(prediction_data)):
            explanation_dict = {
                self.feature_names[j]: float(shap_values[i, j])
                for j in range(len(self.feature_names))
            }
            explanations.append(explanation_dict)
            
        return explanations
