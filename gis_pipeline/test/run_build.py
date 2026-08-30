# run_build.py
from network.build_roads import build_canonical_roads

if __name__ == "__main__":
    # Use a small area for quick testing
    build_canonical_roads("Shillong, India", out_path="data/processed/roads.parquet")