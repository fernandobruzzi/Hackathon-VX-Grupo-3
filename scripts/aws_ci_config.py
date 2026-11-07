"""Monta a configuração do deploy automático a partir da variável do repositório.

A variável `AWS_DEPLOY_CONFIG` guarda o mesmo JSON de `aws.local.json` (IDs e ARNs,
nunca segredos). O workflow constrói as imagens X86_64 no runner e passa os digests
publicados; este script troca as imagens, fixa a arquitetura e valida o resultado
com as mesmas regras do deploy manual.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from aws_support import ConfigurationError, load_config


def render(raw, images, destination):
    try:
        config = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise ConfigurationError("AWS_DEPLOY_CONFIG ausente ou inválida") from error
    if set(images) != {"api", "agent", "batch"}:
        raise ConfigurationError("Informe os digests das três imagens")
    config["architecture"] = "X86_64"
    config["images"] = dict(images)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n")
    # Reaplica toda a validação do deploy manual: conta, região, digests e ARNs.
    return load_config(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    images = {target: os.environ.get(f"IMAGE_{target.upper()}", "") for target in ("api", "agent", "batch")}
    config = render(os.environ.get("AWS_DEPLOY_CONFIG"), images, args.output)
    print(f"Configuração pronta para {config['name']} em {config['region']}, origem {config['public_origin']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConfigurationError as error:
        print(f"FAIL config: {error}", file=sys.stderr)
        sys.exit(1)
