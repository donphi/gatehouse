"""Example: standalone gate validation loop with any LLM API.

Demonstrates the core generate-validate-fix loop: an LLM generates Python
code, Gatehouse validates it against a schema, and violations are fed back
to the LLM until the code passes. The LLM call is a placeholder you can
replace with any SDK (OpenAI, Anthropic, local models, etc.).

Usage:
    python examples/standalone_usage.py
"""

import os
import subprocess

# Uncomment and install the SDK you want to use:
# from openai import OpenAI


def extract_code_from_response(response_text):
    """Extract Python code from a markdown code block in the response.

    Looks for a fenced ``python`` block first, then any fenced block,
    and falls back to the raw text if no fences are found.

    Args:
        response_text: Raw LLM response that may contain markdown fences.

    Returns:
        The extracted Python source code as a string.
    """
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
    """Log a violation for telemetry.

    Args:
        filepath: Path of the file that was validated.
        iteration: Zero-based retry iteration number.
        violations: Newline-separated violation messages from the gate.
        code: The source code that produced the violations.
    """
    print(f"  Iteration {iteration + 1}: {len(violations.splitlines())} violation lines")


def main():
    """Run the generate-validate-fix loop.

    Loads a gate schema, sends a placeholder prompt to an LLM, validates
    the generated code with the Gatehouse engine, and prints the results.
    In production, replace the placeholder with a real LLM API call.
    """
    # Use the installed gatehouse package via python -m
    gate_engine_module = "gatehouse.gate_engine"
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

        # Run gate_engine module on the code string (stdin)
        result = subprocess.run(
            ["python3", "-m", gate_engine_module, "--stdin", "--schema", schema_path,
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
        # response = client.chat.completions.create(
        #     model="gpt-4o",
        #     messages=[
        #         {"role": "user", "content": "Write src/train.py: a training loop"},
        #         {"role": "assistant", "content": f"```python\n{code}\n```"},
        #         {"role": "user", "content": f"Validation failed. Fix ALL errors:\n\n{result.stderr}"}
        #     ]
        # )
        # code = extract_code_from_response(response.choices[0].message.content)

        print("  (In production, feed errors back to the LLM and get corrected code)")
        break  # Break here since we don't have a real LLM in this example

    else:
        print(f"Failed to pass gate after {MAX_ITERATIONS} iterations")


if __name__ == "__main__":
    main()
