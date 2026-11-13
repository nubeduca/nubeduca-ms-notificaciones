#!/bin/bash
# Publica en el bus (BUS, por defecto "lms-dev") un ejemplo del repo nubeduca-contratos, para probar sin esperar al productor.
# Con AWS_ENDPOINT_URL=http://localhost:4566 BUS=lms lo manda a LocalStack.
#
# Uso:  ./scripts/publicar_evento.sh ../nubeduca-contratos/eventos/ejemplos/lms.courses.course.published.v1.json

set -euo pipefail
ARCHIVO=${1:?Falta el JSON del evento}
BUS=${BUS:-lms-dev}
ENTRADA=$(mktemp)
jq -c '[{Source: .source, DetailType: ."detail-type", Detail: (.detail | tojson), EventBusName: $bus}]' --arg bus "$BUS" "$ARCHIVO" > "$ENTRADA"
aws events put-events --entries "file://$ENTRADA"
rm -f "$ENTRADA"
