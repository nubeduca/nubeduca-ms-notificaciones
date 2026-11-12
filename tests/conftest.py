import json
import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import envio  # noqa: E402
from lib import tabla as t  # noqa: E402

TENANT = "utec"
CURSO = "crs_01JCQRZHQT9F4WY2JYPDV546K7"
ALUMNO = "a18577e2-e005-4a49-a29e-755dbf08f5b6"
ALUMNO_2 = "b28577e2-e005-4a49-a29e-755dbf08f5b6"
DOCENTE = "c62d9930-b473-4b1d-adec-72fdda7cf599"


@pytest.fixture(autouse=True)
def aws(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("TABLA_NOTIFICACIONES", "test-t_notificaciones")
    monkeypatch.setenv("AUTH_MODE", "mock")
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="test-t_notificaciones",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "tenant_id", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "tenant_id", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )
        sns = boto3.client("sns")
        sqs = boto3.client("sqs")
        topic = sns.create_topic(Name="test-notificaciones")["TopicArn"]
        cola = sqs.create_queue(QueueName="correos")["QueueUrl"]
        arn = sqs.get_queue_attributes(QueueUrl=cola, AttributeNames=["QueueArn"])["Attributes"][
            "QueueArn"
        ]
        sns.subscribe(TopicArn=topic, Protocol="sqs", Endpoint=arn)
        monkeypatch.setenv("TOPIC_EMAIL", topic)
        t.reiniciar()
        envio.reiniciar()
        yield {"cola_correos": cola}
        t.reiniciar()
        envio.reiniciar()


@pytest.fixture
def correos(aws):
    """Devuelve los emails publicados en SNS (los lee de la cola suscrita al topic)."""

    def leer():
        sqs = boto3.client("sqs")
        mensajes = []
        while True:
            lote = sqs.receive_message(QueueUrl=aws["cola_correos"], MaxNumberOfMessages=10).get(
                "Messages", []
            )
            if not lote:
                return mensajes
            for mensaje in lote:
                mensajes.append(json.loads(mensaje["Body"]))
                sqs.delete_message(QueueUrl=aws["cola_correos"], ReceiptHandle=mensaje["ReceiptHandle"])

    return leer


_contador = {"n": 0}


def evento(detail_type, data, *, tipo="enrollment", agregado=None, version=1, curso=CURSO, event_id=None):
    """Evento de EventBridge completo, como lo deja la regla del bus en SQS."""
    _contador["n"] += 1
    metadata = {
        "eventId": event_id or f"01JCMK0PDR72NVMBVR2W{_contador['n']:06d}",
        "tenantId": TENANT,
        "occurredAt": f"2026-11-15T15:{_contador['n'] % 60:02d}:00Z",
        "aggregateType": tipo,
        "aggregateId": agregado or f"{tipo}_{_contador['n']}",
        "aggregateVersion": version,
        "actorId": DOCENTE,
        "campoNuevoQueNoConozco": "lector tolerante",
    }
    if curso:
        metadata["courseId"] = curso
    return {
        "version": "0",
        "detail-type": detail_type,
        "source": "lms." + detail_type.split(".")[1],
        "detail": {"metadata": metadata, "data": data},
    }


def sqs_evento(*eventos):
    return {
        "Records": [
            {"messageId": f"m{i}", "body": json.dumps(e)} for i, e in enumerate(eventos)
        ]
    }
