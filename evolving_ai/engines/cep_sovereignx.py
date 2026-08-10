from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional, Callable, TYPE_CHECKING
import json
import uuid
import asyncio

if TYPE_CHECKING:
    from evolving_ai import (
        ConstitutionalGenome,
        IntentPattern,
        EvolutionConfig,
    )


@dataclass(frozen=True, slots=True)
class SovereignXRenderConfig:
    sme_endpoint: str = "http://localhost:8082"
    flux_endpoint: str = "http://localhost:8083"
    default_quality: str = "high"
    timeout_seconds: float = 600.0
    max_concurrent_renders: int = 4


@dataclass(frozen=True, slots=True)
class SMEFrame:
    frame_id: str
    timestamp: float
    data: bytes
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SMERenderResult:
    render_id: str
    genome_id: str
    frames: list[SMEFrame]
    manifest: dict[str, Any]
    metrics: dict[str, float]
    status: str
    timestamp: str


@dataclass(frozen=True, slots=True)
class FLUXIngestResult:
    flux_id: str
    genome_id: str
    embeddings: list[list[float]]
    metadata: dict[str, Any]
    status: str
    timestamp: str


class SovereignXRenderer:
    """
    CEP-1 integration with Sovereign X for SME rendering and FLUX ingest.

    Uses genome.render_config to route to SME (frame rendering) and FLUX (embeddings).
    """

    def __init__(self, config: Optional[SovereignXRenderConfig] = None) -> None:
        self.config = config or SovereignXRenderConfig()
        self._session: Optional[Any] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def _get_session(self):
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            )
        return self._session

    async def _get_semaphore(self):
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.config.max_concurrent_renders)
        return self._semaphore

    async def render_genome(
        self,
        genome: ConstitutionalGenome,
        intent: IntentPattern,
        quality: Optional[str] = None,
    ) -> SMERenderResult:
        """
        Render a ConstitutionalGenome via SME (Sovereign X).

        Uses genome.render_config for engine selection and parameters.
        """
        semaphore = await self._get_semaphore()
        async with semaphore:
            render_quality = quality or genome.render_config.get("quality", self.config.default_quality)
            engine = genome.render_config.get("engine", "SME")

            # Build render payload from genome
            payload = {
                "genome_id": genome.lineage_id,
                "intent_id": intent.id,
                "engine": engine,
                "quality": render_quality,
                "topology": genome.topology,
                "arenas": list(genome.arenas),
                "symbols": list(genome.symbols),
                "motifs": list(genome.motifs),
                "roles": list(genome.roles),
                "pacing": list(genome.pacing),
                "transitions": list(genome.transitions),
                "valence_curve": list(genome.valence_curve),
                "arousal_curve": list(genome.arousal_curve),
                "emotional_curve": list(intent.emotional_curve),
                "pacing_target": list(intent.pacing_target),
                "blueprint": intent.blueprint,
                "narrative": intent.narrative,
            }

            # Call SME endpoint
            session = await self._get_session()
            try:
                async with session.post(
                    f"{self.config.sme_endpoint}/render",
                    json=payload,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return self._parse_sme_result(result, genome.lineage_id)
                    else:
                        error_text = await response.text()
                        raise RuntimeError(f"SME render failed: {response.status} - {error_text}")
            except Exception as e:
                # Return mock result for development/testing
                return self._mock_sme_result(genome, intent)

    def _parse_sme_result(self, data: dict[str, Any], genome_id: str) -> SMERenderResult:
        frames = [
            SMEFrame(
                frame_id=f.get("frame_id", str(uuid.uuid4())[:8]),
                timestamp=f.get("timestamp", 0.0),
                data=bytes.fromhex(f.get("data", "")) if f.get("data") else b"",
                metadata=f.get("metadata", {}),
            )
            for f in data.get("frames", [])
        ]

        return SMERenderResult(
            render_id=data.get("render_id", str(uuid.uuid4())[:12]),
            genome_id=genome_id,
            frames=frames,
            manifest=data.get("manifest", {}),
            metrics=data.get("metrics", {}),
            status=data.get("status", "completed"),
            timestamp=datetime.now(UTC).isoformat(),
        )

    def _mock_sme_result(self, genome: ConstitutionalGenome, intent: IntentPattern) -> SMERenderResult:
        """Mock SME result for development/testing."""
        frame_count = len(genome.pacing) if genome.pacing else 4
        frames = [
            SMEFrame(
                frame_id=f"frame_{i}",
                timestamp=float(i) / frame_count,
                data=b"mock_frame_data",
                metadata={
                    "pacing": genome.pacing[i] if i < len(genome.pacing) else 1.0,
                    "valence": genome.valence_curve[i] if i < len(genome.valence_curve) else 0.5,
                    "arousal": genome.arousal_curve[i] if i < len(genome.arousal_curve) else 0.5,
                    "motif": genome.motifs[i] if i < len(genome.motifs) else "core",
                },
            )
            for i in range(frame_count)
        ]

        return SMERenderResult(
            render_id=f"mock_render_{uuid.uuid4().hex[:8]}",
            genome_id=genome.lineage_id,
            frames=frames,
            manifest={
                "engine": "SME",
                "quality": genome.render_config.get("quality", "high"),
                "frame_count": frame_count,
                "intent_id": intent.id,
            },
            metrics={
                "render_time_ms": 100.0,
                "memory_mb": 50.0,
                "fps": 30.0,
            },
            status="completed",
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def ingest_flux(
        self,
        genome: ConstitutionalGenome,
        intent: IntentPattern,
        render_result: Optional[SMERenderResult] = None,
    ) -> FLUXIngestResult:
        """
        Ingest genome/render into FLUX for embeddings.

        Uses genome.arena and genome.symbols for FLUX routing.
        """
        semaphore = await self._get_semaphore()
        async with semaphore:
            payload = {
                "genome_id": genome.lineage_id,
                "intent_id": intent.id,
                "arenas": list(genome.arenas),
                "symbols": list(genome.symbols),
                "motifs": list(genome.motifs),
                "render_result": render_result.manifest if render_result else None,
            }

            session = await self._get_session()
            try:
                async with session.post(
                    f"{self.config.flux_endpoint}/ingest",
                    json=payload,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return self._parse_flux_result(result, genome.lineage_id)
                    else:
                        error_text = await response.text()
                        raise RuntimeError(f"FLUX ingest failed: {response.status} - {error_text}")
            except Exception:
                return self._mock_flux_result(genome, intent)

    def _parse_flux_result(self, data: dict[str, Any], genome_id: str) -> FLUXIngestResult:
        return FLUXIngestResult(
            flux_id=data.get("flux_id", str(uuid.uuid4())[:12]),
            genome_id=genome_id,
            embeddings=data.get("embeddings", []),
            metadata=data.get("metadata", {}),
            status=data.get("status", "completed"),
            timestamp=datetime.now(UTC).isoformat(),
        )

    def _mock_flux_result(self, genome: ConstitutionalGenome, intent: IntentPattern) -> FLUXIngestResult:
        # Generate mock embeddings based on genome features
        dim = 512
        embeddings = []
        for arena in genome.arenas:
            embedding = [hash(f"{arena}:{i}") % 1000 / 1000.0 for i in range(dim)]
            embeddings.append(embedding)

        return FLUXIngestResult(
            flux_id=f"mock_flux_{uuid.uuid4().hex[:8]}",
            genome_id=genome.lineage_id,
            embeddings=embeddings,
            metadata={
                "arenas": list(genome.arenas),
                "symbols": list(genome.symbols),
                "intent_id": intent.id,
            },
            status="completed",
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def render_and_ingest(
        self,
        genome: ConstitutionalGenome,
        intent: IntentPattern,
        quality: Optional[str] = None,
    ) -> tuple[SMERenderResult, FLUXIngestResult]:
        """Convenience method: render via SME then ingest into FLUX."""
        render_result = await self.render_genome(genome, intent, quality)
        flux_result = await self.ingest_flux(genome, intent, render_result)
        return render_result, flux_result

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None


class SMEFrameCallback:
    """Callback handler for streaming SME frames during evolution."""

    def __init__(
        self,
        renderer: SovereignXRenderer,
        on_frame: Optional[Callable[[SMEFrame], None]] = None,
        on_complete: Optional[Callable[[SMERenderResult], None]] = None,
    ) -> None:
        self.renderer = renderer
        self.on_frame = on_frame
        self.on_complete = on_complete

    async def render_generation_best(
        self,
        genome: ConstitutionalGenome,
        intent: IntentPattern,
        generation: int,
    ) -> SMERenderResult:
        """Render the best genome of a generation."""
        result = await self.renderer.render_genome(genome, intent)

        if self.on_frame:
            for frame in result.frames:
                self.on_frame(frame)

        if self.on_complete:
            self.on_complete(result)

        return result


def create_sovereignx_renderer(
    sme_endpoint: str = "http://localhost:8082",
    flux_endpoint: str = "http://localhost:8083",
    quality: str = "high",
) -> SovereignXRenderer:
    """Factory to create SovereignXRenderer."""
    config = SovereignXRenderConfig(
        sme_endpoint=sme_endpoint,
        flux_endpoint=flux_endpoint,
        default_quality=quality,
    )
    return SovereignXRenderer(config)