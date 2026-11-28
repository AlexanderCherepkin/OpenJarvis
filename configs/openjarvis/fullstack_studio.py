"""Мультиагентная сборка Full-Stack Studio поверх OpenJarvis SystemBuilder."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from openjarvis.core.config import load_config
from openjarvis.core.events import EventBus
from openjarvis.system.builder import SystemBuilder

logger = logging.getLogger(__name__)

RoleName = Literal["researcher", "builder", "orchestrator"]


@dataclass
class FullStackStudio:
    """Связка агентов с общей шиной событий EventBus."""

    bus: EventBus
    researcher: Any
    builder: Any
    orchestrator: Any

    def route(self, role: RoleName, prompt: str) -> str:
        """Выполнить запрос через роль (researcher | builder | orchestrator)."""
        targets: Dict[RoleName, Any] = {
            "researcher": self.researcher,
            "builder": self.builder,
            "orchestrator": self.orchestrator,
        }
        if role not in targets:
            raise ValueError(f"Unsupported role: {role}")

        result = targets[role].ask(prompt)
        return getattr(result, "content", str(result))

    def close(self) -> None:
        """Корректно закрыть MCP-сессии всех трёх подсистем."""
        for system in (self.researcher, self.builder, self.orchestrator):
            close_fn = getattr(system, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    logger.exception("Ошибка при закрытии подсистемы %r", system)


def _create_agent(
    cfg: Any,
    bus: EventBus,
    agent_name: str,
    tools: list[str],
) -> Any:
    return (
        SystemBuilder(cfg)
        .engine("lmstudio")
        .model("google/gemma-4-12b")
        .agent(agent_name)
        .tools(tools)
        .traces(True)
        .event_bus(bus)
        .build()
    )


def build_studio() -> FullStackStudio:
    """Собрать 3 изолированных контура SystemBuilder на базе LM Studio и MCP."""
    cfg = load_config()
    bus = EventBus()

    researcher = _create_agent(
        cfg,
        bus,
        "deep_research",
        ["resolve-library-id", "query-docs", "tavily_search", "fetch"],
    )
    builder = _create_agent(
        cfg,
        bus,
        "native_openhands",
        [
            "file_read",
            "file_write",
            "apply_patch",
            "shell_exec",
            "git_status",
            "git_diff",
        ],
    )
    orchestrator = _create_agent(
        cfg,
        bus,
        "orchestrator",
        [
            "think",
            "sequentialthinking",
            "file_read",
            "file_write",
            "query-docs",
            "tavily_search",
            "git_status",
        ],
    )

    return FullStackStudio(
        bus=bus,
        researcher=researcher,
        builder=builder,
        orchestrator=orchestrator,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    studio = build_studio()
    app.state.studio = studio
    try:
        yield
    finally:
        studio.close()


app = FastAPI(
    title="OpenJarvis Full-Stack Studio API",
    version="1.0.0",
    lifespan=lifespan,
)


class StudioTaskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Текст задачи для агента")
    role: RoleName = Field(
        default="orchestrator",
        description="Целевой агент: researcher, builder или orchestrator",
    )


@app.get("/health")
def health() -> Dict[str, Any]:
    studio: FullStackStudio | None = getattr(app.state, "studio", None)
    return {
        "status": "ok",
        "studio_ready": studio is not None,
        "roles": ["researcher", "builder", "orchestrator"],
    }


@app.post("/v1/studio/ask")
def studio_ask(req: StudioTaskRequest) -> Dict[str, str]:
    studio: FullStackStudio | None = getattr(app.state, "studio", None)
    if studio is None:
        raise HTTPException(status_code=503, detail="Studio is not initialized")

    try:
        answer = studio.route(req.role, req.prompt)
    except Exception as exc:
        logger.exception("Ошибка выполнения задачи для роли %s", req.role)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"role": req.role, "answer": answer}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
