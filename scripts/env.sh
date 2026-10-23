#!/usr/bin/env bash
VM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -d "$VM_ROOT/.tools/jdk" ]; then export JAVA_HOME="$VM_ROOT/.tools/jdk"; fi
export PATH="$VM_ROOT/.tools/node/bin:$VM_ROOT/.tools/gradle/bin:${JAVA_HOME:+$JAVA_HOME/bin:}$PATH"
export GRADLE_USER_HOME="$VM_ROOT/.tools/gradle-user-home"

