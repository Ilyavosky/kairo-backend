from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Chat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int


class UsuarioTelegram(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int


class MensajeTelegram(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    chat: Chat
    remitente: UsuarioTelegram | None = Field(default=None, alias="from")
    text: str | None = None


class CallbackTelegram(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    remitente: UsuarioTelegram = Field(alias="from")
    data: str | None = None
    message: MensajeTelegram | None = None


class ActualizacionTelegram(BaseModel):
    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: MensajeTelegram | None = None
    callback_query: CallbackTelegram | None = None


class VinculoOut(BaseModel):
    codigo: str
    comando: str
    expira_en: datetime
