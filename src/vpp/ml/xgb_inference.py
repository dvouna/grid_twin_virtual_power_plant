import xgboost as xgb
import pandas as pd 

class XGBInference:
    def __init__(self, model_path, feature_names):
        self.model = xgb.XGBRegressor()
        self.model.load_model(model_path)
        self.feature_names = feature_names 
        
    def create_lags(self, df, lag_cols, lag_steps):
        for col in lag_cols:
            for step in range(1, lag_steps + 1):
                df[f'{col}_lag_{step}'] = df[col].shift(step)
        return df 

    def create_rollings(self, df, roll_cols, roll_windows):
        for col in roll_cols:
            for window in roll_windows:
                df[f'{col}_rolling_{window}'] = df[col].rolling(window=window).mean()
        return df 

    def cyclical_features(self, df, cyclical_cols, period):
        for col in cyclical_cols:
            df[f'{col}_sin'] = np.sin(2 * np.pi * df[col] / period)
            df[f'{col}_cos'] = np.cos(2 * np.pi * df[col] / period)
        return df 

    def interactions(self, df, interaction_cols):
        for col in interaction_cols:
            df[col] = df[col].astype(float)
        return df 
    
    def load_model(self, model_path):
        self.model.load_model(model_path)


# ----- USING THE SCRIPT -----
Feature_names = ['feature1', 'feature2', 'feature3'] 

# Initialize the Inference class 
inference = XGBInference(model_path='model.json', feature_names=feature_names) 

# Load data 
inf_data = pd.read_csv('data.csv') 

# Make predictions 
predictions = inference.predict(inf_data) 

print(f"Predictions: {predictions}")

Feature_names = [
    'Hour of Day', 'Day of Week', 'Is Weekend', 'Season', 'Month', 
    'Historical Electricity Load (kW)', 'Solar PV Output (kW)', 'Wind Power Output (kW)', 
    'Wind Speed (m/s)', 'Battery State of Charge (SOC) (%)', 'Renewable Forecast Error', 
    'Curtailment Event Flag', 'Temperature (°C)', 'Humidity (%)', 'Solar Irradiance (W/m²)', 
    'Cloud Cover (%)', 'Atmospheric Pressure (hPa)', 'Electricity Load', 
    'Curtailment Risk / Surplus Flag', 'Net Load', 'Solar PV Output (kW)_lag_1', 
    'Solar PV Output (kW)_lag_2', 'Solar PV Output (kW)_lag_3', 'Solar PV Output (kW)_lag_48', 
    'Solar PV Output (kW)_lag_96', 'Solar PV Output (kW)_lag_336', 'Wind Power Output (kW)_lag_1', 
    'Wind Power Output (kW)_lag_2', 'Wind Power Output (kW)_lag_3', 'Wind Power Output (kW)_lag_48', 
    'Wind Power Output (kW)_lag_96', 'Wind Power Output (kW)_lag_336', 'Wind Speed (m/s)_lag_1', 
    'Wind Speed (m/s)_lag_2', 'Wind Speed (m/s)_lag_3', 'Wind Speed (m/s)_lag_48', 
    'Wind Speed (m/s)_lag_96', 'Wind Speed (m/s)_lag_336', 'Battery State of Charge (SOC) (%)_lag_1', 
    'Battery State of Charge (SOC) (%)_lag_2', 'Battery State of Charge (SOC) (%)_lag_3', 
    'Battery State of Charge (SOC) (%)_lag_48', 'Battery State of Charge (SOC) (%)_lag_96', 
    'Battery State of Charge (SOC) (%)_lag_336', 'Renewable Forecast Error_lag_1', 
    'Renewable Forecast Error_lag_2', 'Renewable Forecast Error_lag_3', 'Renewable Forecast Error_lag_48', 
    'Renewable Forecast Error_lag_96', 'Renewable Forecast Error_lag_336', 'Curtailment Event Flag_lag_1', 
    'Curtailment Event Flag_lag_2', 'Curtailment Event Flag_lag_3', 'Curtailment Event Flag_lag_48', 
    'Curtailment Event Flag_lag_96', 'Curtailment Event Flag_lag_336', 'Temperature (°C)_lag_1', 
    'Temperature (°C)_lag_2', 'Temperature (°C)_lag_3', 'Temperature (°C)_lag_48', 'Temperature (°C)_lag_96', 
    'Temperature (°C)_lag_336', 'Humidity (%)_lag_1', 'Humidity (%)_lag_2', 'Humidity (%)_lag_3', 
    'Humidity (%)_lag_48', 'Humidity (%)_lag_96', 'Humidity (%)_lag_336', 'Solar Irradiance (W/m²)_lag_1', 
    'Solar Irradiance (W/m²)_lag_2', 'Solar Irradiance (W/m²)_lag_3', 'Solar Irradiance (W/m²)_lag_48', 
    'Solar Irradiance (W/m²)_lag_96', 'Solar Irradiance (W/m²)_lag_336', 'Cloud Cover (%)_lag_1', 
    'Cloud Cover (%)_lag_2', 'Cloud Cover (%)_lag_3', 'Cloud Cover (%)_lag_48', 'Cloud Cover (%)_lag_96', 
    'Cloud Cover (%)_lag_336', 'Atmospheric Pressure (hPa)_lag_1', 'Atmospheric Pressure (hPa)_lag_2', 
    'Atmospheric Pressure (hPa)_lag_3', 'Atmospheric Pressure (hPa)_lag_48', 
    'Atmospheric Pressure (hPa)_lag_96', 'Atmospheric Pressure (hPa)_lag_336', 
    'Curtailment Risk / Surplus Flag_lag_1', 'Curtailment Risk / Surplus Flag_lag_2', 
    'Curtailment Risk / Surplus Flag_lag_3', 'Curtailment Risk / Surplus Flag_lag_48', 
    'Curtailment Risk / Surplus Flag_lag_96', 'Curtailment Risk / Surplus Flag_lag_336', 
    'Net Load_lag_1', 'Net Load_lag_2', 'Net Load_lag_3', 'Net Load_lag_48', 'Net Load_lag_96', 
    'Net Load_lag_336', 'Solar PV Output (kW)_rw_mean', 'Solar PV Output (kW)_rw_std', 
    'Solar PV Output (kW)_rw_min', 'Solar PV Output (kW)_rw_max', 'Wind Power Output (kW)_rw_mean', 
    'Wind Power Output (kW)_rw_std', 'Wind Power Output (kW)_rw_min', 'Wind Power Output (kW)_rw_max', 
    'Wind Speed (m/s)_rw_mean', 'Wind Speed (m/s)_rw_std', 'Wind Speed (m/s)_rw_min', 
    'Wind Speed (m/s)_rw_max', 'Battery State of Charge (SOC) (%)_rw_mean', 
    'Battery State of Charge (SOC) (%)_rw_std', 'Battery State of Charge (SOC) (%)_rw_min', 
    'Battery State of Charge (SOC) (%)_rw_max', 'Renewable Forecast Error_rw_mean', 
    'Renewable Forecast Error_rw_std', 'Renewable Forecast Error_rw_min', 'Renewable Forecast Error_rw_max', 
    'Temperature (°C)_rw_mean', 'Temperature (°C)_rw_std', 'Temperature (°C)_rw_min', 
    'Temperature (°C)_rw_max', 'Humidity (%)_rw_mean', 'Humidity (%)_rw_std', 'Humidity (%)_rw_min', 
    'Humidity (%)_rw_max', 'Solar Irradiance (W/m²)_rw_mean', 'Solar Irradiance (W/m²)_rw_std', 
    'Solar Irradiance (W/m²)_rw_min', 'Solar Irradiance (W/m²)_rw_max', 'Cloud Cover (%)_rw_mean', 
    'Cloud Cover (%)_rw_std', 'Cloud Cover (%)_rw_min', 'Cloud Cover (%)_rw_max', 
    'Atmospheric Pressure (hPa)_rw_mean', 'Atmospheric Pressure (hPa)_rw_std', 
    'Atmospheric Pressure (hPa)_rw_min', 'Atmospheric Pressure (hPa)_rw_max', 
    'Net Load_rw_mean', 'Net Load_rw_std', 'Net Load_rw_min', 'Net Load_rw_max', 'IsPeakHour', 
    'Temp_pkhr', 'IsSummer', 'IsWinter', 'Temp_x_Win', 'Temp_x_Sum', 'hr_sin', 'hr_cos', 'wk_sin', 
    'wk_cos', 'mo_sin', 'mo_cos', '4hr_load']
        