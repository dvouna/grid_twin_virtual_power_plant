import os
import xgboost as xgb
from .GridFeatureStore import GridFeatureStore

class VPPPredictor:
    def __init__(self, model_path, window_size=49):
        """
        Unifies feature engineering and model inference for the VPP.
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")
            
        # 1. Load the model
        # Note: We use XGBRegressor but access the booster for inplace_predict
        self.model = xgb.XGBRegressor()
        self.model.load_model(model_path)
        
        # 2. Extract feature names from the trained model booster
        self.trained_features = self.model.get_booster().feature_names
        if not self.trained_features:
            raise ValueError("Model does not contain feature names. Ensure it was trained with a DataFrame.")
            
        # 3. Initialize the Feature Store with the expected columns
        self.feature_store = GridFeatureStore(window_size=window_size, expected_columns=self.trained_features)
        
        print(f"VPPPredictor initialized with {len(self.trained_features)} features.")

    def add_observation(self, payload):
        """Adds observation to the inner feature store."""
        self.feature_store.add_observation(payload)

    def predict(self):
        """
        Transforms the current buffer into features and runs inference.
        Returns the prediction (float) or None if not primed.
        """
        # A. Get feature vector (DataFrame)
        inference_df = self.feature_store.get_inference_vector()
        
        if inference_df is None:
            return None
            
        # B. Robust Inference using inplace_predict for single-row performance
        # inplace_predict expects a numpy-like interface (values works well)
        # It handles feature alignment through the underlying Booster
        prediction = self.model.get_booster().inplace_predict(inference_df.values)[0]
        
        return float(prediction)

    @property
    def buffer_info(self):
        """Returns current buffer state."""
        return len(self.feature_store.buffer), self.feature_store.buffer.maxlen
