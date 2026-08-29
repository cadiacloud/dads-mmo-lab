"""CLI Entry point for Synthetic Players Daemon."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
import typer
from .config import load_settings
from .db import DatabaseManager
from .engine import SyntheticEngine
from .llm_client import SyntheticLLMClient
from .persona import PersonaManager
from .profession_planner import ProfessionPlanner
from .material_kit_planner import MaterialKitPlanner

app = typer.Typer(help="Dad's MMO Lab: Synthetic Players Persona Bridge")
console = Console()


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


@app.command()
def run(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override LLM model name (e.g. gemma-4)"),
    api_base: Optional[str] = typer.Option(None, "--api-base", help="Override vLLM / LLM base URL"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
) -> None:
    """Run the background persona bridge for WoW synthetic players."""
    setup_logging(debug)
    settings = load_settings(config)

    if model:
        settings.llm.model = model
    if api_base:
        settings.llm.api_base = api_base
    if debug:
        settings.debug = True

    console.print(
        Panel.fit(
            f"[bold cyan]Dad's MMO Lab — Synthetic Players Daemon[/bold cyan]\n"
            f"[green]• vLLM Endpoint:[/green] {settings.llm.api_base}\n"
            f"[green]• Model:[/green] {settings.llm.model}\n"
            f"[green]• Database:[/green] {settings.db.host}:{settings.db.port}/{settings.db.database}\n"
            f"[green]• Polling Interval:[/green] {settings.poll_interval_ms}ms",
            title="🎮 AzerothCore Persona Bridge",
            border_style="cyan",
        )
    )

    engine = SyntheticEngine(settings)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def handle_signal(*_: object) -> None:
        console.print("\n[yellow]Shutting down daemon...[/yellow]")
        loop.create_task(engine.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(engine.start())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        loop.run_until_complete(engine.stop())
        loop.close()


@app.command()
def health(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
) -> None:
    """Check connectivity to MySQL Database and vLLM / LLM server."""
    setup_logging(False)
    settings = load_settings(config)

    async def _check() -> None:
        table = Table(title="Synthetic Players Component Health")
        table.add_column("Component", style="cyan")
        table.add_column("Target", style="magenta")
        table.add_column("Status", style="bold")

        # Check DB
        db = DatabaseManager(settings.db)
        try:
            await db.connect()
            table.add_row("Database (MySQL)", f"{settings.db.host}:{settings.db.port}/{settings.db.database}", "[green]ONLINE[/green]")
            await db.close()
        except Exception as e:
            table.add_row("Database (MySQL)", f"{settings.db.host}:{settings.db.port}/{settings.db.database}", f"[red]OFFLINE ({e})[/red]")

        # Check LLM
        llm = SyntheticLLMClient(settings.llm)
        is_llm_ok = await llm.health_check()
        status_llm = "[green]ONLINE[/green]" if is_llm_ok else "[red]OFFLINE[/red]"
        table.add_row("LLM Server (vLLM)", f"{settings.llm.api_base} ({settings.llm.model})", status_llm)
        await llm.close()

        console.print(table)

    asyncio.run(_check())


@app.command()
def test_chat(
    bot: str = typer.Option(
        "Lyra",
        "--bot",
        "-b",
        help="Controlled bot name (Lyra, Celene, Ray, or Browntown)",
    ),
    message: str = typer.Argument(..., help="Message to send to the bot"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model name"),
    api_base: Optional[str] = typer.Option(None, "--api-base", help="Override LLM endpoint"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
) -> None:
    """Test persona prompt and response generation directly in terminal."""
    setup_logging(False)
    settings = load_settings(config)
    if model:
        settings.llm.model = model
    if api_base:
        settings.llm.api_base = api_base

    async def _test() -> None:
        llm = SyntheticLLMClient(settings.llm)
        persona_mgr = PersonaManager(personas_file=settings.personas_file)
        persona = persona_mgr.get_or_create_persona(bot)
        system_prompt = persona_mgr.build_system_prompt(persona, current_zone="Dalaran")

        console.print(f"\n[bold yellow]Testing Persona:[/bold yellow] [bold cyan]{persona.name}[/bold cyan] ({persona.race_name} {persona.class_name})")
        console.print(f"[bold green]Player:[/bold green] {message}")
        console.print("[dim]Querying LLM endpoint...[/dim]")

        try:
            resp = await llm.generate_response(system_prompt, [], message)
            console.print(f"\n[bold cyan]{persona.name}:[/bold cyan] {resp.content}")
            if resp.action_command:
                console.print(f"[bold magenta]Action Triggered:[/bold magenta] {resp.action_command}")
            console.print(f"[dim]Latency: {resp.latency_ms:.1f}ms[/dim]\n")
        except Exception as e:
            console.print(f"[bold red]Error calling LLM:[/bold red] {e}")
        finally:
            await llm.close()

    asyncio.run(_test())


@app.command()
def init_db(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
) -> None:
    """Initialize database tables for Synthetic Players."""
    setup_logging(False)
    settings = load_settings(config)

    async def _init() -> None:
        db = DatabaseManager(settings.db)
        try:
            await db.connect()
            console.print("[bold green]✓ Database tables initialized successfully![/bold green]")
            await db.close()
        except Exception as e:
            console.print(f"[bold red]✗ Database initialization failed:[/bold red] {e}")

    asyncio.run(_init())


@app.command("plan-professions")
def plan_professions(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    guides: Optional[str] = typer.Option(None, "--guides", help="Path to profession-guides.yaml"),
    bot: list[str] = typer.Option([], "--bot", help="Limit planning to one or more controlled bot names"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override LLM model name"),
    api_base: Optional[str] = typer.Option(None, "--api-base", help="Override vLLM / LLM endpoint"),
    activate: bool = typer.Option(False, "--activate", help="Persist and activate validated objectives"),
) -> None:
    """Have the local LLM choose allowlisted 1-450 routes and activate objectives."""
    setup_logging(False)
    if not activate:
        raise typer.BadParameter("--activate is required because this command writes live objectives")

    settings = load_settings(config)
    if model:
        settings.llm.model = model
    if api_base:
        settings.llm.api_base = api_base
    guides_file = guides or settings.profession_guides_file

    async def _plan() -> None:
        planner = ProfessionPlanner(settings, guides_file)
        try:
            plan_id, assignments, objective_count = await planner.create_and_activate(bot or None)
            table = Table(title=f"Activated Profession Plan #{plan_id}")
            table.add_column("Bot", style="cyan")
            table.add_column("Profession", style="magenta")
            table.add_column("Current", justify="right")
            table.add_column("Stages", justify="right")
            for assignment in assignments:
                table.add_row(
                    assignment.bot_name,
                    assignment.profession_name,
                    str(assignment.current_skill),
                    str(len(assignment.stage_zones)),
                )
            console.print(table)
            console.print(
                f"[green]Activated {objective_count} validated objectives.[/green] "
                "The worldserver executor will pause for character-level gates, gather with "
                "the party, route only unattended bots, and deposit eligible materials."
            )
        finally:
            await planner.close()

    asyncio.run(_plan())


@app.command("plan-material-kits")
def plan_material_kits(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    catalog: Optional[str] = typer.Option(None, "--catalog", help="Path to material-kits.yaml"),
    profession: list[str] = typer.Option(
        [], "--profession", help="One or more 1-450 kits (alchemy, inscription, jewelcrafting, engineering, tailoring)"
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override LLM model name"),
    api_base: Optional[str] = typer.Option(None, "--api-base", help="Override vLLM / LLM endpoint"),
    activate: bool = typer.Option(False, "--activate", help="Persist and activate validated targets"),
) -> None:
    """Allocate and activate source-backed material kits for real players."""
    setup_logging(False)
    if not activate:
        raise typer.BadParameter("--activate is required because this command writes live targets")

    selected = profession or ["alchemy", "inscription", "jewelcrafting", "engineering", "tailoring"]
    settings = load_settings(config)
    if model:
        settings.llm.model = model
    if api_base:
        settings.llm.api_base = api_base
    catalog_file = catalog or settings.material_kits_file

    async def _plan() -> None:
        planner = MaterialKitPlanner(settings, catalog_file)
        try:
            plan_id, assignment, target_count = await planner.create_and_activate(selected)
            table = Table(title=f"Activated Material Kit Plan #{plan_id}")
            table.add_column("Mode", style="magenta")
            table.add_column("Qualified work order", style="cyan")
            for route in assignment.routes:
                table.add_row(route.mode, ", ".join(route.bot_names))
            console.print(table)
            console.print(
                f"[green]Activated {target_count} validated material targets.[/green] "
                "Fixed catalog quantities and real guild-bank counts remain authoritative."
            )
        finally:
            await planner.close()

    asyncio.run(_plan())


if __name__ == "__main__":
    app()
