# run_build.py
from ml.pipeline.build_roads import build_canonical_roads

if __name__ == "__main__":
    # No arguments needed anymore, it uses the hardcoded Shillong coordinates
    build_canonical_roads(out_path="data/processed/roads.parquet")