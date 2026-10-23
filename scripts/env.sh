#!/usr/bin/env bash
if [ -n "${BASH_VERSION:-}" ]; then
  VM_ENV_SOURCE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  VM_ENV_SOURCE="${(%):-%N}"
else
  echo 'Source this file from bash or zsh.' >&2
  return 1
fi
VM_ROOT="$(cd "$(dirname "$VM_ENV_SOURCE")/.." && pwd)"
if [ -d "$VM_ROOT/.tools/jdk" ]; then export JAVA_HOME="$VM_ROOT/.tools/jdk"; fi
export PATH="$VM_ROOT/.tools/node/bin:$VM_ROOT/.tools/gradle/bin:${JAVA_HOME:+$JAVA_HOME/bin:}$PATH"
export GRADLE_USER_HOME="$VM_ROOT/.tools/gradle-user-home"

