"""Dispara uma task Fargate fixada por revisão, sem enviar credenciais da API."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from vx_materials_api.services.batch_runner import LaunchRequest


class EcsFargateRunner:
    name = "ecs_fargate"

    def __init__(self, client=None):
        self.cluster = self._required("ECS_CLUSTER")
        self.definition = self._required("ECS_BATCH_TASK_DEFINITION")
        if not re.fullmatch(r"arn:aws:ecs:[a-z0-9-]+:\d{12}:task-definition/[A-Za-z0-9_-]+:\d+", self.definition):
            raise RuntimeError("ECS_BATCH_TASK_DEFINITION precisa ser um ARN com revisão fixa")
        self.subnets = self._ids("ECS_SUBNET_IDS", "subnet")
        self.groups = self._ids("ECS_SECURITY_GROUP_IDS", "sg")
        self.public_ip = os.environ.get("ECS_ASSIGN_PUBLIC_IP", "ENABLED")
        if self.public_ip not in {"ENABLED", "DISABLED"}:
            raise RuntimeError("ECS_ASSIGN_PUBLIC_IP precisa ser ENABLED ou DISABLED")
        self.client = client or boto3.client(
            "ecs", config=Config(connect_timeout=5, read_timeout=15, retries={"mode": "standard", "max_attempts": 3})
        )

    @staticmethod
    def _required(name):
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(f"Variável obrigatória para ECS batch: {name}")
        return value

    @classmethod
    def _ids(cls, name, prefix):
        values = cls._required(name).split(",")
        if any(not re.fullmatch(rf"{prefix}-[0-9a-f]{{8,17}}", value) for value in values):
            raise RuntimeError(f"IDs inválidos em {name}")
        return values

    def launch(self, request: LaunchRequest) -> str:
        job_id = str(uuid.UUID(request.job_id))
        if request.manifest_key != f"runs/{job_id}/manifest.json":
            raise RuntimeError("Manifesto não pertence ao job solicitado")
        # Repetições da mesma tentativa usam o mesmo token. Resume persiste outra tentativa.
        attempt = request.attempt_id or job_id
        token = hashlib.sha256(f"{job_id}:{attempt}".encode()).hexdigest()
        try:
            response = self.client.run_task(
                cluster=self.cluster,
                taskDefinition=self.definition,
                launchType="FARGATE",
                platformVersion="1.4.0",
                count=1,
                clientToken=token,
                startedBy=f"job-{job_id}",
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": self.subnets,
                        "securityGroups": self.groups,
                        "assignPublicIp": self.public_ip,
                    }
                },
                overrides={
                    "containerOverrides": [
                        {
                            "name": "Batch",
                            "command": [
                                "vx-back",
                                "sanitize",
                                "--job-id",
                                job_id,
                                "--manifest-key",
                                request.manifest_key,
                            ],
                        }
                    ]
                },
            )
        except (BotoCoreError, ClientError):
            raise RuntimeError("ECS_BATCH_LAUNCH_FAILED: consulte o evento ECS e as permissões da task") from None
        if response.get("failures") or len(response.get("tasks", [])) != 1:
            raise RuntimeError("ECS_BATCH_LAUNCH_FAILED: nenhuma task única foi confirmada")
        return response["tasks"][0]["taskArn"]
