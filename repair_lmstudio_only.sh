#!/usr/bin/env bash
# Repair OpenJarvis on C:/AgentJarvis and configure LM Studio ONLY.
# Run from Windows Git Bash: bash repair_lmstudio_only.sh
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/c/AgentJarvis}"
LMSTUDIO_HOST="${LMSTUDIO_HOST:-http://127.0.0.1:1234}"
LMSTUDIO_API="${LMSTUDIO_HOST%/}/v1"

say()  { printf '\n\033[1;36m[LM Studio setup]\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m[Warning]\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[1;31m[Error]\033[0m %s\n' "$*" >&2; exit 1; }

say "Checking the project location..."
[[ -d "$PROJECT_DIR" ]] || die "Project directory not found: $PROJECT_DIR. The expected Windows folder is C:\\AgentJarvis."
cd "$PROJECT_DIR"
[[ -f pyproject.toml ]] || die "pyproject.toml was not found in $PROJECT_DIR."

say "Clearing the stale virtual-environment reference from this shell..."
# The terminal log showed an old G:/AgentJarvis environment being activated.
# Do not activate a moved venv; let uv manage C:/AgentJarvis/.venv.
if declare -F deactivate >/dev/null 2>&1; then
  deactivate >/dev/null 2>&1 || true
fi
unset VIRTUAL_ENV
export UV_LINK_MODE=copy
hash -r

command -v uv >/dev/null 2>&1 || die "uv is missing from PATH. Install it with: winget install --id astral-sh.uv -e"
say "Tools detected: $(uv --version)"
if command -v git >/dev/null 2>&1; then
  git --version || warn "Git executable is present but failed to report its version."
else
  warn "Git was not found on PATH. The previous installation attempt failed; this setup can continue if the project dependencies do not require Git."
fi
if command -v node >/dev/null 2>&1; then node --version; else warn "Node.js is not on PATH. The Python backend can still work; GUI/frontend tasks may need Node.js."; fi
if command -v npm >/dev/null 2>&1; then npm --version; else warn "npm is not on PATH."; fi

# If an activation script still contains the former G: location, discard only
# the virtual environment (it is reproducible) and recreate it on C:.
if [[ -f .venv/Scripts/activate ]] && grep -Eiq 'G:[/\\]AgentJarvis' .venv/Scripts/activate; then
  warn "The C: virtual environment still contains the old G: path. Recreating .venv..."
  rm -rf .venv
fi

say "Synchronizing the project environment on C:..."
uv sync --extra dev --extra desktop

VENV_PREFIX="$(uv run python -c 'import sys; print(sys.prefix)')"
printf 'Python environment: %s\n' "$VENV_PREFIX"
if printf '%s' "$VENV_PREFIX" | grep -Eiq 'G:[/\\]AgentJarvis'; then
  die "uv is still using the old G: environment. Close this terminal, open a fresh Git Bash, cd to /c/AgentJarvis and rerun."
fi

say "Checking the LM Studio OpenAI-compatible API at $LMSTUDIO_API/models..."
API_JSON=""
for attempt in $(seq 1 4); do
  API_JSON="$(curl --connect-timeout 2 --max-time 8 -fsS "$LMSTUDIO_API/models" 2>/dev/null || true)"
  [[ -n "$API_JSON" ]] && break

  # If the LM Studio CLI is available, ask it to start the local server.
  if [[ "$attempt" -eq 1 ]] && command -v lms >/dev/null 2>&1; then
    say "Starting the LM Studio server via lms..."
    lms server start || warn "Could not start the server through lms; check the Developer tab in LM Studio."
  fi
  sleep 2
done

if [[ -z "$API_JSON" ]]; then
  die "LM Studio API is not responding. Open LM Studio -> Developer -> Local Server, start the server on port 1234, and turn OFF API-token authentication for local OpenJarvis access. Then rerun this script. No other inference engine will be configured."
fi

say "Reading model IDs reported by LM Studio..."
mapfile -t MODEL_IDS < <(
  printf '%s' "$API_JSON" | uv run python -c 'import json,sys; d=json.load(sys.stdin); [print(x["id"]) for x in d.get("data",[]) if isinstance(x,dict) and isinstance(x.get("id"),str) and x["id"].strip()]'
)

((${#MODEL_IDS[@]} > 0)) || die "LM Studio API is online, but /v1/models returned no loaded models. In LM Studio, download and LOAD a model, then rerun this script."

if ((${#MODEL_IDS[@]} == 1)); then
  MODEL_ID="${MODEL_IDS[0]}"
  say "Found loaded model: $MODEL_ID"
else
  printf '\nModels currently exposed by LM Studio:\n'
  for i in "${!MODEL_IDS[@]}"; do
    printf '  %d) %s\n' "$((i + 1))" "${MODEL_IDS[$i]}"
  done
  read -r -p "Choose the model number to use with OpenJarvis and the C# agent [1]: " MODEL_CHOICE
  MODEL_CHOICE="${MODEL_CHOICE:-1}"
  [[ "$MODEL_CHOICE" =~ ^[0-9]+$ ]] || die "Enter a numeric model choice."
  ((MODEL_CHOICE >= 1 && MODEL_CHOICE <= ${#MODEL_IDS[@]})) || die "Model choice is outside the list."
  MODEL_ID="${MODEL_IDS[$((MODEL_CHOICE - 1))]}"
fi

say "Backing up the current OpenJarvis config..."
CONFIG_FILE="$HOME/.openjarvis/config.toml"
if [[ -f "$CONFIG_FILE" ]]; then
  BACKUP_FILE="$CONFIG_FILE.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  cp -p "$CONFIG_FILE" "$BACKUP_FILE"
  printf 'Backup: %s\n' "$BACKUP_FILE"
fi

say "Pinning OpenJarvis to LM Studio..."
uv run jarvis config set engine.default lmstudio
uv run jarvis config set engine.lmstudio.host "$LMSTUDIO_HOST"
uv run jarvis config set intelligence.preferred_engine lmstudio
uv run jarvis config set intelligence.default_model "$MODEL_ID"

say "Testing inference explicitly through LM Studio..."
if ! uv run jarvis ask --engine lmstudio --model "$MODEL_ID" --no-stream \
  "Ответь одной короткой фразой по-русски: локальная модель через LM Studio работает."; then
  die "The model is visible to LM Studio, but the OpenJarvis test request failed. Check the LM Studio model load, context length, and the error printed above."
fi

say "Updating the Windows user environment for the C# ProductionDevAgent..."
# LM Studio's server does not require an API key by default. 'lm-studio' is
# the harmless placeholder expected by the C# client when auth is disabled.
if command -v setx.exe >/dev/null 2>&1; then
  setx.exe OPENAI_BASE_URL "$LMSTUDIO_API" >/dev/null
  setx.exe OPENAI_API_KEY "lm-studio" >/dev/null
  setx.exe JARVIS_MODEL_ID "$MODEL_ID" >/dev/null
  export OPENAI_BASE_URL="$LMSTUDIO_API"
  export OPENAI_API_KEY="lm-studio"
  export JARVIS_MODEL_ID="$MODEL_ID"
  say "Saved OPENAI_BASE_URL, OPENAI_API_KEY and JARVIS_MODEL_ID for Windows user processes. Restart Visual Studio/Rider/your C# app."
else
  warn "setx.exe is unavailable. Set these Windows user variables manually:"
  printf '  OPENAI_BASE_URL=%s\n  OPENAI_API_KEY=lm-studio\n  JARVIS_MODEL_ID=%s\n' "$LMSTUDIO_API" "$MODEL_ID"
fi

say "Running OpenJarvis Doctor (it may still show warnings for unused optional engines)..."
if ! uv run jarvis doctor; then
  warn "Doctor returned a non-zero status. Review the report above; this script's inference test through LM Studio has already been completed."
fi

printf '\n\033[1;32mLM Studio-only setup completed.\033[0m\n'
printf 'Project: %s\nEngine:  lmstudio\nAPI:     %s\nModel:   %s\n' "$PROJECT_DIR" "$LMSTUDIO_API" "$MODEL_ID"
printf '\nUse these commands from now on:\n  cd /c/AgentJarvis\n  uv run jarvis ask --engine lmstudio "%s"\n' 'Привет, Jarvis!'
