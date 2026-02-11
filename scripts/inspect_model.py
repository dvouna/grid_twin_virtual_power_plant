import xgboost as xgb

model = xgb.XGBRegressor()
model.load_model("xgb_vpp_grid.json")
booster = model.get_booster()
fnames = booster.feature_names
if fnames:
    for name in fnames:
        print(name)
else:
    print("No feature names found in model.")
