#!/bin/bash
# Crea en TU cuenta de pruebas lo que ms-notificaciones consume pero producen otros:
#   - el bus EventBridge "lms-<stage>" y el tópico SNS FIFO "nubeduca-<stage>-notas.fifo"
#     (mismos nombres que PLT-04, nubeduca-infra/bus; en la cuenta final los crea ese stack)
# Es idempotente. Correrlo ANTES de "sls deploy". NO usar en la cuenta del despliegue final.
#
# Uso:  ./scripts/crear_recursos_dev.sh [stage]      (por defecto: dev)

set -euo pipefail
STAGE=${1:-dev}

aws events create-event-bus --name "lms-${STAGE}" >/dev/null 2>&1 || true
echo "OK  bus lms-${STAGE}"

ARN=$(aws sns create-topic --name "nubeduca-${STAGE}-notas.fifo" \
  --attributes FifoTopic=true,ContentBasedDeduplication=false \
  --query TopicArn --output text)
echo "OK  $ARN"
