#!/bin/bash
# Revisa por qué un evento del bus no llegó a ms-notificaciones.
# Uso:  ./scripts/diagnostico.sh [stage] [bus] [userId]
#       (por defecto: dev, lms, alumno demo de UTEC)

STAGE=${1:-dev}
BUS=${2:-lms}
USUARIO=${3:-11111111-1111-4111-8111-111111111111}
REGLA="nubeduca-${STAGE}-notificaciones"
FUNCION="nubeduca-ms-notificaciones-${STAGE}-eventosBus"
INI=$(date -u -d '-60 min' +%FT%TZ)
FIN=$(date -u +%FT%TZ)

metrica() {
  aws cloudwatch get-metric-statistics \
    --namespace AWS/Events --metric-name "$1" \
    --dimensions Name=RuleName,Value="$REGLA" Name=EventBusName,Value="$BUS" \
    --start-time "$INI" --end-time "$FIN" \
    --period 3600 --statistics Sum \
    --query "Datapoints[].Sum" --output text
}

cola() {
  local url
  url=$(aws sqs get-queue-url --queue-name "$1" --query QueueUrl --output text)
  aws sqs get-queue-attributes --queue-url "$url" \
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
    --query "Attributes" --output text
}

echo "== Regla $REGLA en el bus $BUS (última hora)"
echo "   eventos que coincidieron: $(metrica MatchedEvents)"
echo "   entregas fallidas a la cola: $(metrica FailedInvocations)"

echo "== Cola y DLQ (en cola / en proceso)"
echo "   eventos: $(cola "nubeduca-${STAGE}-notificaciones-eventos")"
echo "   dlq:     $(cola "nubeduca-${STAGE}-notificaciones-eventos-dlq")"

echo "== Lambda $FUNCION conectada a la cola"
aws lambda list-event-source-mappings --function-name "$FUNCION" \
  --query "EventSourceMappings[].[State,EventSourceArn]" --output text
echo "   (si dice Disabled: ./scripts/activar_colas.sh)"

echo "== Últimos logs del Lambda"
aws logs tail "/aws/lambda/$FUNCION" --since 60m | tail -8

echo "== Avisos del usuario $USUARIO"
URL=$(aws ssm get-parameter --name "/nubeduca/${STAGE}/api/notificaciones/url" \
  --query Parameter.Value --output text)
curl -s "$URL/notifications/me?limit=3" \
  -H "Authorization: Bearer mock.utec.STUDENT.$USUARIO"
echo
