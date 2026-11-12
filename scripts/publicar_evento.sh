#!/bin/bash
# Publica en el bus "lms" un ejemplo del repo nubeduca-contratos, para probar sin esperar al productor.
# Con AWS_ENDPOINT_URL=http://localhost:4566 lo manda a LocalStack.
#
# Uso:  ./scripts/publicar_evento.sh ../nubeduca-contratos/eventos/ejemplos/lms.courses.course.published.v1.json

set -euo pipefail
ARCHIVO=${1:?Falta el JSON del evento}
ENTRADA=$(mktemp)
jq -c '[{Source: .source, DetailType: ."detail-type", Detail: (.detail | tojson), EventBusName: "lms"}]' "$ARCHIVO" > "$ENTRADA"
aws events put-events --entries "file://$ENTRADA"
rm -f "$ENTRADA"
