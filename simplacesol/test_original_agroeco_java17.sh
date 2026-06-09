#!/usr/bin/env bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH"

exec python3 /home/hydros/Downloads/SIMPLACE/AGROECO4CAST_AF/test_original_agroeco.py "$@"
