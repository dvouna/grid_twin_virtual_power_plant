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

    def add_observation(self, payload):
        """Adds a new data point from Kafka to the state for downstream feature engineering."""
        # Create a clean dictionary with identical keys as expected by apply_* methods
        row = {
            'Timestamp': payload.get('Timestamp', 0),
            'Hist_Load': payload.get('Hist_Load', 0),
            'Elec_Load': payload.get('Elec_Load', 0),
            'Solar_kw': payload.get('Solar_kw', 0),
            'Wind_kw': payload.get('Wind_kw', 0),
            'RF_Error': payload.get('RF_Error', 0),
            'C_Flag': payload.get('C_Flag', 0),
            'C_R_S': payload.get('C_R_S', 0),
            'B_SOC': payload.get('B_SOC', 0),
            'Temp': payload.get('Temp', 0),
            'Humidity': payload.get('Humidity', 0),
            'S_Irr': payload.get('S_Irr', 0),
            'Cloud': payload.get('Cloud', 0),
            'W_Speed': payload.get('W_Speed', 0),
            'HPa': payload.get('HPa', 0),
            'Net_Load': payload.get('Net_Load', 0)
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
        df['Weekend'] = (df['Timestamp'].dt.dayofweek >= 5).astype(int)
        df['Hist_Ramp'] = df['Net_Load'].diff()

        # 3. Collect Lags and Rolling Windows in a dictionary
        new_feats = {}
        for col in self.lag_cols:
            if col in df.columns:
                # Lags
                for lag in self.lags:
                    new_feats[f'{col}_lag_{lag}'] = df[col].shift(lag)
                # Rolling stats (window 48)
                rolling_win = df[col].rolling(window=48)
                for stat in self.stats:
                    new_feats[f'{col}_rw_{stat}'] = rolling_win.agg(stat)
        
        # Join large feature set at once
        df = pd.concat([df, pd.DataFrame(new_feats)], axis=1)

        # 4. Interactions & Cyclical features
        final_bits = {}
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

        # 5. Extract the last row and Align
        latest_features = df.iloc[[-1]].copy()
        if self.expected_columns:
            latest_features = latest_features.reindex(columns=self.expected_columns).fillna(0)
            
        return latest_features

    # Deprecated: These are now inlined in get_inference_vector for performance
    def date_features(self, df): return df
    def target_column(self, df): return df
    def apply_lags(self, df): return df
    def apply_rolling_windows(self, df): return df
    def apply_interactions_cyclical_features(self, df): return df
