
import os
import pandas as pd

from dotenv import load_dotenv
from entsoe import EntsoePandasClient

# Load API token from .env
load_dotenv()

api_key = os.getenv("ENTSOE_API_KEY")

if not api_key:
    raise ValueError("ENTSOE_API_KEY not found in .env")

# Connect to ENTSO-E
client = EntsoePandasClient(api_key=api_key)

# Test: actual electricity load for Italy
start = pd.Timestamp("2024-01-01", tz="Europe/Rome")
end = pd.Timestamp("2024-01-03", tz="Europe/Rome")

actual_load = client.query_load(
    "IT",
    start=start,
    end=end
)

print("ENTSO-E connection successful!")
print("Number of observations:", len(actual_load))
print(actual_load.head())


# Test: day-ahead load forecasts for Italy
forecast_load = client.query_load_forecast(
    "IT",
    start=start,
    end=end
)

print("\nDAY-AHEAD FORECAST")
print("Number of observations:", len(forecast_load))
print(forecast_load.head())
