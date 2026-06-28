# scripts/test_agent.py
import logging
from agent.react_loop import run_meal_logging

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    image_path = "745104219_67.jpg"  # reuse an existing test photo
    result = run_meal_logging(user_id=12345, image_path=image_path)
    print("\n--- FINAL REPLY ---")
    print(result)