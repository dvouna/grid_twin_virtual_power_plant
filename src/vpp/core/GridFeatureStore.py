import pandas as pd
import numpy as np
from collections import deque

class GridFeatureStore:
    def __init__(self, window_size=49, expected_columns=None):
        """
        window_size: Number of steps to keep for lags/rolling stats. 
                     Default 49 supports up to lag 48.
        expected_columns: The exact list/order of features used during model.fit()
        """
        self.buffer = deque(maxlen=window_size)
        self.expected_columns = expected_columns
        self.is_primed = False
        self.lag_cols = [
            "Hist_Load", "Elec_Load", "Solar_kw", "Wind_kw", "RF_Error", "C_Flag",
            "C_R_S", "B_SOC", "Temp", "Humidity", "S_Irr", "Cloud", "W_Speed", 
            "HPa", "Net_Load", "Hist_Ramp"
        ]
        self.lags = [1, 2, 24, 48]
        self.r_windows = [3, 6, 12, 48]
        self.stats = ['mean', 'std', 'min', 'max'] 
        self.MODEL_FEATURES = [
            "Hour", "Day", "Weekend", "Month", "Hist_Load", "Elec_Load", "Solar_kw", "Wind_kw", "RF_Error", "C_Flag",
            "C_R_S", "B_SOC", "Temp", "Humidity", "S_Irr", "Cloud", "W_Speed", "HPa", "Net_Load", "Hist_Ramp",
            "Hist_Load_lag_1", "Hist_Load_lag_2", "Hist_Load_lag_24", "Hist_Load_lag_48", "Elec_Load_lag_1", 
            "Elec_Load_lag_2", "Elec_Load_lag_24", "Elec_Load_lag_48", "Solar_kw_lag_1", "Solar_kw_lag_2", 
            "Solar_kw_lag_24", "Solar_kw_lag_48", "Wind_kw_lag_1", "Wind_kw_lag_2", "Wind_kw_lag_24", 
            "Wind_kw_lag_48", "RF_Error_lag_1", "RF_Error_lag_2", "RF_Error_lag_24", "RF_Error_lag_48", 
            "C_Flag_lag_1", "C_Flag_lag_2", "C_Flag_lag_24", "C_Flag_lag_48", "C_R_S_lag_1", "C_R_S_lag_2", 
            "C_R_S_lag_24", "C_R_S_lag_48", "B_SOC_lag_1", "B_SOC_lag_2", "B_SOC_lag_24", "B_SOC_lag_48", 
            "Temp_lag_1", "Temp_lag_2", "Temp_lag_24", "Temp_lag_48", "Humidity_lag_1", "Humidity_lag_2", 
            "Humidity_lag_24", "Humidity_lag_48", "S_Irr_lag_1", "S_Irr_lag_2", "S_Irr_lag_24", "S_Irr_lag_48", 
            "Cloud_lag_1", "Cloud_lag_2", "Cloud_lag_24", "Cloud_lag_48", "W_Speed_lag_1", "W_Speed_lag_2", 
            "W_Speed_lag_24", "W_Speed_lag_48", "HPa_lag_1", "HPa_lag_2", "HPa_lag_24", "HPa_lag_48", 
            "Net_Load_lag_1", "Net_Load_lag_2", "Net_Load_lag_24", "Net_Load_lag_48", "Hist_Ramp_lag_1", 
            "Hist_Ramp_lag_2", "Hist_Ramp_lag_24", "Hist_Ramp_lag_48", "Hist_Load_rw_mean", "Hist_Load_rw_std", 
            "Hist_Load_rw_min", "Hist_Load_rw_max", "Elec_Load_rw_mean", "Elec_Load_rw_std", "Elec_Load_rw_min", 
            "Elec_Load_rw_max", "Solar_kw_rw_mean", "Solar_kw_rw_std", "Solar_kw_rw_min", "Solar_kw_rw_max", 
            "Wind_kw_rw_mean", "Wind_kw_rw_std", "Wind_kw_rw_min", "Wind_kw_rw_max", "RF_Error_rw_mean", 
            "RF_Error_rw_std", "RF_Error_rw_min", "RF_Error_rw_max", "C_Flag_rw_mean", "C_Flag_rw_std", 
            "C_Flag_rw_min", "C_Flag_rw_max", "C_R_S_rw_mean", "C_R_S_rw_std", "C_R_S_rw_min", "C_R_S_rw_max", 
            "B_SOC_rw_mean", "B_SOC_rw_std", "B_SOC_rw_min", "B_SOC_rw_max", "Temp_rw_mean", "Temp_rw_std", 
            "Temp_rw_min", "Temp_rw_max", "Humidity_rw_mean", "Humidity_rw_std", "Humidity_rw_min", 
            "Humidity_rw_max", "S_Irr_rw_mean", "S_Irr_rw_std", "S_Irr_rw_min", "S_Irr_rw_max", "Cloud_rw_mean", 
            "Cloud_rw_std", "Cloud_rw_min", "Cloud_rw_max", "W_Speed_rw_mean", "W_Speed_rw_std", "W_Speed_rw_min", 
            "W_Speed_rw_max", "HPa_rw_mean", "HPa_rw_std", "HPa_rw_min", "HPa_rw_max", "Net_Load_rw_mean", 
            "Net_Load_rw_std", "Net_Load_rw_min", "Net_Load_rw_max", "Hist_Ramp_rw_mean", "Hist_Ramp_rw_std", 
            "Hist_Ramp_rw_min", "Hist_Ramp_rw_max", "IsPeakHour", "Temp_pkhr", "IsSummer", "Temp_x_Sum", 
            "IsWinter", "Temp_x_Win", "hr_sin", "hr_cos", "wk_sin", "wk_cos", "mo_sin", "mo_cos"
        ]

    def add_observation(self, payload):
        """Adds a new data point from Kafka to the state for downstream feature engineering."""
        # Create a clean dictionary with identical keys as expected by apply_* methods
        # Use case-insensitive lookup for robustness
        def g(key):
            return payload.get(key) or payload.get(key.lower()) or 0

        row = {
            'Timestamp': g('Timestamp'),
            'Hist_Load': g('Hist_Load'),
            'Elec_Load': g('Elec_Load'),
            'Solar_kw': g('Solar_kw'),
            'Wind_kw': g('Wind_kw'),
            'RF_Error': g('RF_Error'),
            'C_Flag': g('C_Flag'),
            'C_R_S': g('C_R_S'),
            'B_SOC': g('B_SOC'),
            'Temp': g('Temp'),
            'Humidity': g('Humidity'),
            'S_Irr': g('S_Irr'),
            'Cloud': g('Cloud'),
            'W_Speed': g('W_Speed'),
            'HPa': g('HPa'),
            'Net_Load': g('Net_Load')
        }

        self.buffer.append(row)
        if len(self.buffer) >= self.buffer.maxlen:
            self.is_primed = True

    def get_inference_vector(self):
        """
        Transforms the buffer into a single feature row for XGBoost.
        Uses pd.concat to avoid DataFrame fragmentation.
        """
        if not self.is_primed:
            return None

        # 1. Base DataFrame from buffer
        df = pd.DataFrame(list(self.buffer))
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        # 2. Basic Date & Target calculation
        df['Hour'] = df['Timestamp'].dt.hour
        df['Day'] = df['Timestamp'].dt.dayofweek
        df['Month'] = df['Timestamp'].dt.month
        df['Hist_Ramp'] = df['Net_Load'].diff()

        # 3. Collect Lags and Rolling Windows in a dictionary
        new_feats = {}
        for col in self.lag_cols:
            if col in df.columns:
                # Lags [1, 2, 24, 48]
                for lag in self.lags:
                    new_feats[f'{col}_lag_{lag}'] = df[col].shift(lag)
                
                # Rolling stats (window 48) - Match model names like 'Hist_Load_rw_mean'
                # Based on model_features.txt, it's always window 48
                rolling_win = df[col].rolling(window=48)
                for stat in self.stats:
                    feat_name = f'{col}_rw_{stat}'
                    if stat == 'mean':
                        new_feats[feat_name] = rolling_win.mean()
                    elif stat == 'std':
                        new_feats[feat_name] = rolling_win.std()
                    elif stat == 'min':
                        new_feats[feat_name] = rolling_win.min()
                    elif stat == 'max':
                        new_feats[feat_name] = rolling_win.max()
        
        # Join large feature set at once
        df = pd.concat([df, pd.DataFrame(new_feats)], axis=1)

        # 4. Interactions & Cyclical features
        final_bits = {}
        # Ensure we use the exact names from model_features.txt
        final_bits['IsPeakHour'] = ((df['Hour'] >= 7) & (df['Hour'] < 22)).astype(int)
        final_bits['Temp_pkhr'] = df['Temp'] * final_bits['IsPeakHour']
        final_bits['IsSummer'] = ((df['Month'] >= 6) & (df['Month'] <= 8)).astype(int)
        final_bits['Temp_x_Sum'] = df['Temp'] * final_bits['IsSummer']
        final_bits['IsWinter'] = ((df['Month'] == 12) | (df['Month'] <= 2)).astype(int)
        final_bits['Temp_x_Win'] = df['Temp'] * final_bits['IsWinter']
            
        final_bits['hr_sin'] = np.sin(2 * np.pi * df['Hour'] / 24)
        final_bits['hr_cos'] = np.cos(2 * np.pi * df['Hour'] / 24)
        final_bits['wk_sin'] = np.sin(2 * np.pi * df['Day'] / 7)
        final_bits['wk_cos'] = np.cos(2 * np.pi * df['Day'] / 7)
        final_bits['mo_sin'] = np.sin(2 * np.pi * df['Month'] / 12)
        final_bits['mo_cos'] = np.cos(2 * np.pi * df['Month'] / 12)
        
        df = pd.concat([df, pd.DataFrame(final_bits)], axis=1)

        # 5. Extract the last row
        latest_features = df.iloc[[-1]].copy()

        # 6. Strict Alignment
        cols_to_use = self.expected_columns if self.expected_columns else self.MODEL_FEATURES
        
        # Reindex to match model EXACTLY, fill missing with 0
        latest_features = latest_features.reindex(columns=cols_to_use).fillna(0)
        
        # CRITICAL: Convert all columns to float64 so XGBoost sees a proper
        # numeric DataFrame with feature names intact.
        latest_features = latest_features.astype(np.float64)
            
        return latest_features



