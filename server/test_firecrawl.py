import os
import json
import time
from dotenv import load_dotenv
from firecrawl import Firecrawl
from pydantic import BaseModel, Field

# 1. Load Environment Variables
load_dotenv()
api_key = os.getenv("FIRECRAWL_API_KEY")

if not api_key:
    print("Error: FIRECRAWL_API_KEY not found in .env")
    exit(1)

# 2. Initialize Firecrawl App
try:
    app = Firecrawl(api_key=api_key)
    print(f"Success: Initialized Firecrawl with key ending in ...{api_key[-4:]}")
except Exception as e:
    print(f"Critical: Failed to initialize Firecrawl. Error: {e}")
    exit(1)

# 3. Define the Schema for JSON Output
# This structure ensures the agent returns exactly what your coding agent needs.
class RestaurantUIResearch(BaseModel):
    ui_component_structure: str = Field(description="Recommended folder and file structure for the React project")
    essential_dependencies: list[str] = Field(description="List of npm packages required (e.g., UI libraries, state management)")
    key_features_implementation: str = Field(description="Technical details on how to implement key features like Menu, Cart, and Checkout")
    styling_approach: str = Field(description="Best practices for styling (e.g., Tailwind, CSS-in-JS) for this specific use case")

# 4. Define the Prompt
prompt = (
    "Research a working restaurant UI for React. Find me all the info for it, "
    "including the code structure and other info required. We will feed the "
    "info to a coding agent, so give it accordingly."
)

print(f"\n--- STARTING AGENT ---")
print(f"Prompt: {prompt}")
print("Agent is researching... this may take up to 60 seconds.")

# 5. Run Agent with 'spark-1-mini' and Schema
try:
    response = app.agent(
        prompt=prompt,
        schema=RestaurantUIResearch.model_json_schema(), # Force JSON output
        model="spark-1-mini",
        timeout=60000  # Set timeout to 60 seconds (value in ms)
    )
    
    print("\n*** SUCCESS ***")
    
    # 6. Extract and Save Data
    # The 'data' attribute contains the structured JSON result
    result_data = response.data if hasattr(response, 'data') else response
    
    # Print to console (formatted)
    print(json.dumps(result_data, indent=2))
    
    # Save to file
    filename = "restaurant_ui_data.json"
    with open(filename, "w") as f:
        json.dump(result_data, f, indent=2)
    
    print(f"\nResults saved to '{filename}'. You can pass this file to your coding agent.")

except Exception as e:
    print(f"\nError: An unexpected error occurred: {e}")
