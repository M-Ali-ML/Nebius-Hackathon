# Worker hf: Hugging Face publish

## Status 14:45: BLOCKED

Token check (`whoami-v2`, account MightyStudent):

- `nebius-build-week` is not in the account orgs (orgs: arbml, MCP-1st-Birthday). Join the org with the invite link.
- The token is fine-grained with only `repo.content.read` on the user MightyStudent. It cannot write anywhere.

Fix:

1. Join `nebius-build-week` with the invite link.
2. Open https://huggingface.co/settings/tokens and edit the token in `.env` (or make a new one).
3. Under "Org permissions", add `nebius-build-week` and tick "Write access to contents/settings of all repos in selected organizations" and "Create repos / Interact with discussions".
4. Save. If you make a new token, put it in `/Users/aly/repos/Nebius-Hackathon/.env` as `HF_TOKEN`.

The worker checks every 2 minutes and publishes when the token can write.
