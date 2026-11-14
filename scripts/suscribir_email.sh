#!/bin/bash
# Suscribe un correo al topic de emails de ms-notificaciones, filtrado por userId:
# ese correo solo recibe los avisos de ese usuario. AWS manda un email de confirmación
# que hay que aceptar antes de recibir avisos. Si el correo ya está suscrito, agrega el
# userId a su filtro (así un correo puede recibir los avisos de varios usuarios demo).
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

# ¿El correo ya está suscrito? Entonces se agrega el userId a su filtro (SNS no deja
# suscribir dos veces el mismo correo con otro filtro).
EXISTENTE=$(aws sns list-subscriptions-by-topic --topic-arn "$TOPIC" \
  --query "Subscriptions[?Endpoint=='${EMAIL}'].SubscriptionArn | [0]" --output text)

if [ -n "$EXISTENTE" ] && [ "$EXISTENTE" != "None" ] && [ "$EXISTENTE" != "PendingConfirmation" ]; then
  ACTUAL=$(aws sns get-subscription-attributes --subscription-arn "$EXISTENTE" \
    --query "Attributes.FilterPolicy" --output text)
  NUEVA=$(python3 -c '
import json, sys
actual, user_id = sys.argv[1], sys.argv[2]
ids = json.loads(actual).get("userId", []) if actual not in ("", "None") else []
if user_id not in ids:
    ids.append(user_id)
print(json.dumps({"userId": ids}))
' "$ACTUAL" "$USER_ID")
  aws sns set-subscription-attributes --subscription-arn "$EXISTENTE" \
    --attribute-name FilterPolicy --attribute-value "$NUEVA"
  echo "$EMAIL ya estaba suscrito. Filtro actualizado: $NUEVA"
  exit 0
fi

aws sns subscribe \
  --topic-arn "$TOPIC" \
  --protocol email \
  --notification-endpoint "$EMAIL" \
  --attributes "{\"FilterPolicy\":\"{\\\"userId\\\":[\\\"${USER_ID}\\\"]}\"}" \
  --query SubscriptionArn --output text
echo "Revisa la bandeja de $EMAIL y confirma la suscripción."
