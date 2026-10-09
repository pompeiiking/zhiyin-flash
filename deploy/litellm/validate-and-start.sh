#!/bin/sh
set -eu

key_1="${DEEPSEEK_API_KEY_1:-}"
key_2="${DEEPSEEK_API_KEY_2:-}"
key_3="${DEEPSEEK_API_KEY_3:-}"
key_4="${DEEPSEEK_API_KEY_4:-}"
master_key="${LITELLM_MASTER_KEY:-}"

if [ -z "$key_1" ] || [ -z "$key_2" ] || [ -z "$key_3" ] || [ -z "$key_4" ]; then
  echo "LiteLLM startup refused: all four DEEPSEEK_API_KEY_* values are required." >&2
  exit 64
fi

if [ "$key_1" = "$key_2" ] || [ "$key_1" = "$key_3" ] || [ "$key_1" = "$key_4" ] || \
   [ "$key_2" = "$key_3" ] || [ "$key_2" = "$key_4" ] || [ "$key_3" = "$key_4" ]; then
  echo "LiteLLM startup refused: DEEPSEEK_API_KEY_* values must be distinct." >&2
  exit 64
fi

case "$master_key" in
  sk-*) ;;
  *)
    echo "LiteLLM startup refused: LITELLM_MASTER_KEY must start with sk-." >&2
    exit 64
    ;;
esac

exec litellm "$@"
