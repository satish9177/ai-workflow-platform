from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.llm.registry import LLMRegistry
from app.models.user import User
from app.schemas.llm import ProviderModelsRead, ProviderRead


router = APIRouter(tags=["llm"])


@router.get("/providers", response_model=list[ProviderRead])
async def list_providers(
    current_user: User = Depends(get_current_user),
) -> list[ProviderRead]:
    providers: list[ProviderRead] = []
    for name in LLMRegistry.available():
        provider = LLMRegistry.get(name)
        if provider is not None:
            providers.append(ProviderRead(id=name, name=provider.display_name))
    return providers


@router.get("/providers/{provider_id}/models", response_model=ProviderModelsRead)
async def list_provider_models(
    provider_id: str,
    current_user: User = Depends(get_current_user),
) -> ProviderModelsRead:
    available = LLMRegistry.available()
    provider = LLMRegistry.get(provider_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found. Available: {available}",
        )

    return ProviderModelsRead(provider=provider_id, models=provider.supported_models())
