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

    def predict_curve(self, current_net_load_kw: float, steps: int = 4) -> list[float]:
        """
        Generates a simulated multi-step predicted load curve.
        Since the core model predicts a single 30-min change, this method 
        extrapolates that change across `steps` intervals to provide 
        the trajectory needed for BAM Agent pre-conditioning.
        
        Args:
            current_net_load_kw: The current known grid net load in kW.
            steps: The number of intervals to extrapolate the curve over.
            
        Returns:
            A list of forecasted net load values (kW).
        """
        prediction_change = self.predict()
        if prediction_change is None:
            return []
            
        step_change = prediction_change / steps
        curve = [current_net_load_kw + (step_change * i) for i in range(1, steps + 1)]
        return curve

    @property
    def buffer_info(self):
        """Returns current buffer state."""
        return len(self.feature_store.buffer), self.feature_store.buffer.maxlen
