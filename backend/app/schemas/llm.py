from pydantic import BaseModel


class ProviderRead(BaseModel):
    id: str
    name: str


class ProviderModelsRead(BaseModel):
    provider: str
    models: list[str]
