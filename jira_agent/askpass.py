#!/usr/bin/env python3
"""GIT_ASKPASS helper: keeps Bitbucket credentials out of remote URLs and the agent's view."""
import os
import sys

prompt = sys.argv[1].lower() if len(sys.argv) > 1 else ""
print("x-bitbucket-api-token-auth" if "username" in prompt else os.environ["BITBUCKET_API_TOKEN"])
