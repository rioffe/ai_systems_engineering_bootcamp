"""Put the fixture `repo/` on sys.path so `from config import parse_config`
resolves under `pytest -q`, whatever the working directory.

The agent copies this whole tree (fixtures/parse-config) into its ephemeral
sandbox and runs the verifier inside it; the agent's OWN tests never leak into
the sandbox (I-011), so pytest collects only test/test_config.py here.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "repo"))
