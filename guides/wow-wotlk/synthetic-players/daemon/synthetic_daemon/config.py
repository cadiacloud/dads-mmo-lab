"""Configuration module for Synthetic Players Daemon."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """Configuration for LLM API (vLLM / Ollama / OpenAI-compatible)."""
    api_base: str = Field(default="http://127.0.0.1:8000/v1", description="Base URL of vLLM / OpenAI endpoint")
    api_key: str = Field(default="EMPTY", description="API key (if required)")
    model: str = Field(default="your-served-model", description="Model name served by vLLM")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    max_tokens: int = Field(default=150, ge=16, le=2048)
    timeout_seconds: float = Field(default=15.0, ge=1.0)


class DatabaseConfig(BaseModel):
    """MySQL Database connection settings (AzerothCore characters DB)."""
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=3306)
    user: str = Field(default="root")
    password: str = Field(default="password")
    database: str = Field(default="acore_characters")
    pool_min_size: int = Field(default=1)
    pool_max_size: int = Field(default=5)


class DirectorConfig(BaseModel):
    """High-level Playerbots director settings."""

    enabled: bool = Field(default=True)
    intent_ttl_seconds: int = Field(default=30, ge=5, le=120)
    result_batch_size: int = Field(default=5, ge=1, le=50)


class DaemonSettings(BaseSettings):
    """Global daemon settings."""
    model_config = SettingsConfigDict(
        env_prefix="SYNTHETIC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm: LLMConfig = Field(default_factory=LLMConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    director: DirectorConfig = Field(default_factory=DirectorConfig)
    poll_interval_ms: int = Field(default=500, description="Inbox polling interval in ms")
    max_batch_size: int = Field(default=5, description="Max inbox events processed per tick")
    personas_file: str = Field(default="personas.yaml", description="Path to custom personas YAML")
    profession_guides_file: str = Field(
        default="config/profession-guides.yaml",
        description="Validated WotLK gathering guide catalog used by the one-shot LLM planner",
    )
    material_kits_file: str = Field(
        default="config/material-kits.yaml",
        description="Source-backed material quantities for real-player profession leveling kits",
    )
    controlled_personas: List[str] = Field(
        default_factory=lambda: ["Lyra", "Celene", "Ray", "Browntown"],
        description="Only these canonical Playerbots may enter the LLM/action pipeline",
    )
    debug: bool = Field(default=False)


def load_settings(config_path: Optional[str] = None) -> DaemonSettings:
    """Load settings from optional YAML file merged with environment variables."""
    yaml_data: Dict[str, Any] = {}

    if config_path and Path(config_path).is_file():
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

    return DaemonSettings(**yaml_data)
