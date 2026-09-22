from dataclasses import dataclass

import httpx

from .db import Database, RecordWriter
from .guardrails_client import GuardrailsClient
from .settings import Settings


@dataclass
class Deps:
    settings: Settings
    db: Database
    writer: RecordWriter
    http: httpx.AsyncClient
    client: GuardrailsClient
