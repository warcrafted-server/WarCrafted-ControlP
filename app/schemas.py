from typing import Literal

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    is_admin: bool

    class Config:
        from_attributes = True


class CommandRequest(BaseModel):
    command: str


class GithubTokenRequest(BaseModel):
    token: str


class ScheduledStopRequest(BaseModel):
    delay_seconds: int
    message: str


class CommandResult(BaseModel):
    output: str


class ServerSummary(BaseModel):
    id: str
    name: str
    type: str
    enabled: bool
    state: Literal["offline", "starting", "online", "stopping"]
    pid: int | None = None
    cpu_percent: float | None = None
    cpu_percent_host: float | None = None
    memory_mb: float | None = None
    players_online: int | None = None
    update_diff_ms: int | None = None
    auth_service_id: str | None = None
    error: str | None = None


class AuthServiceSummary(BaseModel):
    id: str
    name: str
    enabled: bool
    state: Literal["offline", "online", "stopping"]
    accounts_total: int | None = None
    accounts_online: int | None = None
    linked_instances: list[str] = []


class LogRun(BaseModel):
    filename: str
    category: str
    started_at: str
    size_bytes: int
    source: str


class LogContent(BaseModel):
    content: str
    truncated: bool
    total_size_bytes: int


class SystemStats(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
