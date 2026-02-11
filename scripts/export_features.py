import json

import xgboost as xgb

bst = xgb.Booster()
bst.load_model('models/xgb_vpp_grid.json')
with open('model_features_list.json', 'w') as f:
    json.dump(bst.feature_names, f, indent=4)
