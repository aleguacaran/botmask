# AGENTS.md

## Git rules
- NEVER commit, stage, push, amend, or otherwise run git write commands without explicit user confirmation.

## Runtime rules
- ALWAYS run commands that involve the app (browser, patchright, playwright, python scripts, tests, lint) inside the container via `docker compose run --rm app <command>` (or `docker compose exec app <command>` if the container is already up), never directly on the host. Prefer `--rm` for one-off commands.
- To test inside the container: `docker compose run --rm app bash`
- Do NOT force headless mode in test commands when `BROWSER_HEADLESS=false` in `.env`; respect the env var (default is non-headless). Only set `BROWSER_HEADLESS=true` when the user explicitly asks for a headless test.
