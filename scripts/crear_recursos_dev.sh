#!/bin/bash
# Crea en TU cuenta de pruebas lo que ms-notificaciones consume pero producen otros:
#   - el bus EventBridge "lms" (en el despliegue final lo crea PLT-04)
#   - el tópico SNS FIFO "<stage>-notas.fifo" (en el despliegue final lo crea ms-calificaciones)
# Es idempotente. Correrlo ANTES de "sls deploy". NO usar en la cuenta del despliegue final.
#
# Uso:  ./scripts/crear_recursos_dev.sh [stage]      (por defecto: dev)

set -euo pipefail
STAGE=${1:-dev}

aws events create-event-bus --name lms >/dev/null 2>&1 || true
echo "OK  bus lms"

ARN=$(aws sns create-topic --name "${STAGE}-notas.fifo" \
  --attributes FifoTopic=true,ContentBasedDeduplication=false \
  --query TopicArn --output text)
echo "OK  $ARN"
