import os

def get_api_url() -> str:
    return os.environ["BENCHMARK_API_URL"]
