from pathlib import Path

import yaml

from ciris_engine.schemas.config.agent import AgentTemplate


def validate_templates():
    """
    Validates the agent templates against the AgentTemplate schema.
    """
    template_paths = [
        Path("ciris_templates/echo-core.yaml"),
        Path("ciris_templates/echo-speculative.yaml"),
    ]

    for path in template_paths:
        print(f"Validating {path}...")
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)
                AgentTemplate.model_validate(data)
            print(f"SUCCESS: {path} is valid against the AgentTemplate schema.")
        except Exception as e:
            print(f"ERROR: {path} failed validation.")
            print(e)
            return


if __name__ == "__main__":
    validate_templates()
