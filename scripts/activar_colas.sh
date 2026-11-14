#!/bin/bash
# Reactiva las conexiones cola SQS -> Lambda que quedaron en Disabled.
# El Learner Lab las desactiva al terminar la sesión; córrelo al empezar cada sesión.
# Solo las de Nubeduca (Lambdas cuyo nombre empieza con "nubeduca-": ms-notificaciones, ms-cursos, etc.).
#
# Uso:  ./scripts/activar_colas.sh

UUIDS=$(aws lambda list-event-source-mappings \
  --query "EventSourceMappings[?State=='Disabled' && contains(FunctionArn, ':function:nubeduca-')].UUID" \
  --output text)

if [ -z "$UUIDS" ]; then
  echo "Todas las conexiones ya están activas."
  exit 0
fi

for UUID in $UUIDS; do
  aws lambda update-event-source-mapping --uuid "$UUID" --enabled \
    --query "[FunctionArn, State]" --output text
done
echo "Listo. Tardan hasta 1 minuto en quedar en Enabled."
