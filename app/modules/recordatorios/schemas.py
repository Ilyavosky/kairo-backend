from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

EstadoEnvio = Literal["pendiente", "enviado", "fallido", "cancelado"]


class RecordatorioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actividad_id: UUID | None = None
    evento_id: UUID | None = None
    meta_id: UUID | None = None
    momento: AwareDatetime

    @model_validator(mode="after")
    def un_solo_objetivo(self) -> Self:
        indicados = [
            v
            for v in (self.actividad_id, self.evento_id, self.meta_id)
            if v is not None
        ]
        if len(indicados) != 1:
            raise ValueError(
                "indica exactamente uno de actividad_id, evento_id o meta_id"
            )
        return self


class RecordatorioPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    momento: AwareDatetime | None = None
    estado_envio: Literal["cancelado"] | None = None


class RecordatorioOut(BaseModel):
    id: UUID
    actividad_id: UUID | None
    evento_id: UUID | None
    meta_id: UUID | None
    momento: datetime
    estado_envio: EstadoEnvio
    intentos: int
    enviado_en: datetime | None
    creado_en: datetime
