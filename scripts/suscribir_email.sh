#!/bin/bash
# Suscribe un correo al topic de emails de ms-notificaciones, filtrado por userId:
# ese correo solo recibe los avisos de ese usuario. AWS manda un email de confirmación
# que hay que aceptar antes de recibir avisos.
#
# Uso:  ./scripts/suscribir_email.sh <email> <userId> [stage]
# Ej.:  ./scripts/suscribir_email.sh alumno.demo@gmail.com 11111111-1111-4111-8111-111111111111

set -euo pipefail
EMAIL=${1:?Falta el email}
USER_ID=${2:?Falta el userId (sub de Cognito)}
STAGE=${3:-dev}

TOPIC=$(aws sns list-topics --query "Topics[?ends_with(TopicArn, ':nubeduca-${STAGE}-notificaciones')].TopicArn | [0]" --output text)
if [ -z "$TOPIC" ] || [ "$TOPIC" = "None" ]; then
  echo "No existe el topic nubeduca-${STAGE}-notificaciones. ¿Ya hiciste sls deploy?" >&2
  exit 1
fi

aws sns subscribe \
  --topic-arn "$TOPIC" \
  --protocol email \
  --notification-endpoint "$EMAIL" \
  --attributes "{\"FilterPolicy\":\"{\\\"userId\\\":[\\\"${USER_ID}\\\"]}\"}" \
  --query SubscriptionArn --output text
echo "Revisa la bandeja de $EMAIL y confirma la suscripción."
