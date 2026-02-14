"""
Standalone gate usage with any LLM API.
The gate runs locally. The LLM runs anywhere (API, local, etc.).

This example uses the Anthropic API, but the pattern works with any LLM.
"""

import json
import subprocess
import os

# Uncomment and install the SDK you want to use:
# from anthropic import Anthropic
# from openai import OpenAI


def extract_code_from_response(response_text):
    """Extract Python code from a markdown code block in the response."""
    if "```python" in response_text:
        start = response_text.index("```python") + len("```python")
        end = response_text.index("```", start)
        return response_text[start:end].strip()
    elif "```" in response_text:
        start = response_text.index("```") + 3
        end = response_text.index("```", start)
        return response_text[start:end].strip()
    return response_text.strip()


def log_violation(filepath, iteration, violations, code):
    """Log a violation for telemetry."""
    print(f"  Iteration {iteration + 1}: {len(violations.splitlines())} violation lines")


def main():
    """
    Example: Generate a Python file using an LLM, validate it with the gate,
    and loop until it passes.
    """
    gate_home = os.environ.get("GATE_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    gate_engine = os.path.join(gate_home, "gate_engine.py")
    schema_path = ".gate_schema.yaml"

    # Step 1: Load the schema so the LLM knows the rules
    if not os.path.exists(schema_path):
        print(f"No {schema_path} found. Run 'gatehouse init --schema production' first.")
        return

    with open(schema_path) as f:
        schema_text = f.read()

    # Step 2: This is where you'd call your LLM API
    # For this example, we use a placeholder
    print("Step 1: Ask the LLM to write code...")
    print("  (Replace this with your actual LLM API call)")
    print()

    # Placeholder code that would come from the LLM
    code = '''import torch

class Trainer:
    def train(self):
        learning_rate = 0.001
        epochs = 10
        for epoch in range(epochs):
            print(f"Epoch {epoch}")
'''

    # Step 3: Validate with the gate engine
    MAX_ITERATIONS = 5
    for iteration in range(MAX_ITERATIONS):
        print(f"Step {iteration + 2}: Validating with gate engine...")

        # Run gate_engine.py on the code string (stdin)
        result = subprocess.run(
            ["python3", gate_engine, "--stdin", "--schema", schema_path,
             "--filename", "src/train.py"],
            input=code,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            # Gate passed — save the file
            os.makedirs("src", exist_ok=True)
            with open("src/train.py", "w") as f:
                f.write(code)
            print(f"  Passed! Saved src/train.py (iteration {iteration + 1})")
            break

        # Gate failed — show errors
        print(f"  Failed. Violations:")
        for line in result.stderr.strip().splitlines():
            print(f"    {line}")
        print()

        # In a real implementation, you'd feed these errors back to the LLM:
        #
        # response = client.messages.create(
        #     model="claude-sonnet-4-20250514",
        #     messages=[
        #         {"role": "user", "content": "Write src/train.py: a training loop"},
        #         {"role": "assistant", "content": f"```python\n{code}\n```"},
        #         {"role": "user", "content": f"Validation failed. Fix ALL errors:\n\n{result.stderr}"}
        #     ]
        # )
        # code = extract_code_from_response(response.content[0].text)

        print("  (In production, feed errors back to the LLM and get corrected code)")
        break  # Break here since we don't have a real LLM in this example

    else:
        print(f"Failed to pass gate after {MAX_ITERATIONS} iterations")


if __name__ == "__main__":
    main()
