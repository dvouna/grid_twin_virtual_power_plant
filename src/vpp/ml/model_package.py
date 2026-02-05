import xgboost as xgb
import json
import platform
import pkg_resources
from datetime import datetime

def package_xgboost_model(model, model_name, random_search_results=None, additional_metadata=None):
    """
    Saves an XGBoost model and captures its environment/metadata into a JSON file.
    
    Args:
        model: The trained XGBoost model (e.g., best_model).
        model_name: Base filename to save the model and metadata.
        random_search_results: Optional RandomizedSearchCV object to extract hyperparams and scores.
        additional_metadata: Dictionary of extra info (author, dataset version, etc.).
    """
    # 1. Save model in native JSON format (highly portable)
    model.save_model(f"{model_name}.json")
    
    # 2. Extract specific model info if results are provided
    results_info = {}
    if random_search_results:
        results_info = {
            "best_hyperparameters": {k: str(v) for k, v in random_search_results.best_params_.items()},
            "best_score_rmse": float(-random_search_results.best_score_) if hasattr(random_search_results, 'best_score_') else None
        }

    # 3. Capture Environment
    env_info = {
        "python_version": platform.python_version(),
        "xgboost_version": xgb.__version__,
        "platform": platform.platform(),
        "installed_packages": [f"{d.project_name}=={d.version}" for d in pkg_resources.working_set]
    }
    
    # 4. Combine into final package info
    package_details = {
        "model_summary": {
            "name": model_name,
            "type": "XGBoost Regression",
            "saved_at": datetime.now().isoformat(),
            **results_info
        },
        "environment": env_info,
        "metadata": additional_metadata or {}
    }
    
    # 5. Save metadata to JSON
    metadata_filename = f"{model_name}_metadata.json"
    with open(metadata_filename, "w") as f:
        json.dump(package_details, f, indent=4)
    
    print("--- Model Packaging Complete ---")
    print(f"Model saved to:    {model_name}.json")
    print(f"Metadata saved to: {metadata_filename}")

if __name__ == "__main__":
    print("This script provides the package_xgboost_model function for use in your notebooks.")
