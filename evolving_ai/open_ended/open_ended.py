from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import json
import random
import uuid

import numpy as np

from evolving_ai.core import (
    EvolutionEngine,
    EvolutionConfig,
    EvaluatedCandidate,
    GenerationSummary,
    Genome,
    Task,
    Archive,
    NoveltyArchive,
)
from evolving_ai.core.genome import DenseGenome


class OpenEndedTask(Task):
    """Task that generates its own challenges (open-ended)."""

    def __init__(self, name: str = "open_ended"):
        self.name = name
        self.challenges: List[Dict[str, Any]] = []
        self.challenge_history: List[Dict[str, Any]] = []

    @abstractmethod
    def generate_challenge(self, genome: Genome) -> Dict[str, Any]:
        """Generate a new challenge based on current genome."""
        pass

    @abstractmethod
    def evaluate_on_challenge(self, genome: Genome, challenge: Dict[str, Any]) -> float:
        """Evaluate genome on a specific challenge."""
        pass

    def evaluate(self, genome: Genome) -> float:
        # Evaluate on all known challenges
        if not self.challenges:
            challenge = self.generate_challenge(genome)
            self.challenges.append(challenge)
            return self.evaluate_on_challenge(genome, challenge)

        scores = []
        for challenge in self.challenges:
            scores.append(self.evaluate_on_challenge(genome, challenge))
        return np.mean(scores)

    def behavior_descriptor(self, genome: Genome) -> Tuple[float, ...]:
        # Behavior = performance vector across challenges
        return tuple(self.evaluate_on_challenge(genome, c) for c in self.challenges)


class LLMMutationEngine(EvolutionEngine):
    """Evolution engine with LLM-guided mutations."""

    def __init__(
        self,
        config: EvolutionConfig,
        task: Task,
        archive: Archive,
        llm_client: Any,  # OpenAI, Anthropic, local LLM, etc.
        mutation_prompt_template: str = None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(config, task, archive, rng)
        self.llm_client = llm_client
        self.mutation_prompt_template = mutation_prompt_template or self._default_prompt()

    def _default_prompt(self) -> str:
        return """You are an AI assisting in neuroevolution. Given a neural network genome and its performance, suggest specific mutations to improve it.

Genome: {genome_desc}
Fitness: {fitness:.4f}
Novelty: {novelty:.4f}
Task: {task_name}

Suggest 1-3 specific mutations (weight changes, architecture changes, hyperparameter changes) in JSON format:
{{"mutations": [{{"type": "weight_perturb", "layer": 0, "magnitude": 0.1}}, {{"type": "add_neuron", "layer": 1}}, {{"type": "change_activation", "layer": 2, "activation": "gelu"}}]}}"""

    def _build_prompt(self, genome: Genome, fitness: float, novelty: float) -> str:
        genome_desc = self._describe_genome(genome)
        return self.mutation_prompt_template.format(
            genome_desc=genome_desc,
            fitness=fitness,
            novelty=novelty,
            task_name=self.task.name,
        )

    def _describe_genome(self, genome: Genome) -> str:
        if hasattr(genome, 'weights'):
            w = np.array(genome.weights)
            return f"Shape: {w.shape}, Mean: {w.mean():.4f}, Std: {w.std():.4f}, Sparsity: {(w==0).mean():.4f}"
        return str(genome.to_dict())

    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        try:
            data = json.loads(response)
            return data.get("mutations", [])
        except:
            return []

    def _apply_llm_mutations(self, genome: Genome, mutations: List[Dict[str, Any]]) -> Genome:
        if not hasattr(genome, 'weights'):
            return genome.mutate(self.config, self.rng)

        new_weights = np.array(genome.weights, copy=True)

        for mut in mutations:
            mtype = mut.get("type")
            if mtype == "weight_perturb":
                layer = mut.get("layer", 0)
                magnitude = mut.get("magnitude", 0.1)
                # Apply to all weights (simplified)
                new_weights += self.rng.normal(0, magnitude, new_weights.shape)
            elif mtype == "add_neuron":
                # Would need architecture modification
                pass
            elif mtype == "change_activation":
                # Would need activation modification
                pass

        return DenseGenome(
            weights=new_weights.tolist(),
            mutation_scale=genome.mutation_scale,
            lineage_id=f"{genome.lineage_id}_llm",
        )

    def _next_generation(self, scored: List[EvaluatedCandidate]) -> List[Genome]:
        # Standard evolution + LLM-guided mutations for top candidates
        scored.sort(key=lambda c: c.score, reverse=True)
        n = len(scored)
        elite_count = max(1, int(self.config.elite_fraction * n))
        elites = [c.genome.clone() for c in scored[:elite_count]]

        new_pop = elites[:]

        # Apply LLM mutations to top 10%
        llm_candidates = scored[:max(1, n // 10)]
        for candidate in llm_candidates:
            if self.llm_client:
                prompt = self._build_prompt(candidate.genome, candidate.fitness, candidate.novelty)
                try:
                    response = self.llm_client.complete(prompt)
                    mutations = self._parse_llm_response(response)
                    if mutations:
                        child = self._apply_llm_mutations(candidate.genome, mutations)
                        new_pop.append(child)
                except Exception:
                    pass

        # Fill rest with standard evolution
        def tournament() -> Genome:
            candidates = self.rng.sample(scored, min(self.config.tournament_size, len(scored)))
            return max(candidates, key=lambda c: c.score).genome

        mut_config = self.config.to_mutation_config() if hasattr(self.config, 'to_mutation_config') else None

        while len(new_pop) < n:
            parent1 = tournament()
            parent2 = tournament()
            child = parent1.crossover(parent2, self.rng)
            if self.rng.random() < self.config.mutation_rate:
                if mut_config:
                    child = child.mutate(mut_config, self.rng)
                else:
                    child = child.mutate(self.rng)
            new_pop.append(child)

        return new_pop[:n]


class EvolutionaryPromptingEngine(EvolutionEngine):
    """Evolve prompts for frozen LLMs."""

    def __init__(
        self,
        config: EvolutionConfig,
        llm_client: Any,
        base_prompt: str,
        evaluation_fn: Callable[[str], float],  # prompt -> score
        archive: Archive,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(config, None, archive, rng)
        self.llm_client = llm_client
        self.base_prompt = base_prompt
        self.evaluation_fn = evaluation_fn

    class PromptGenome(Genome):
        def __init__(self, prompt: str, mutation_scale: float = 0.1):
            self.prompt = prompt
            self.mutation_scale = mutation_scale
            self.lineage_id = str(uuid.uuid4())[:8]
            self.age = 0

        def mutate(self, config: Any, rng: random.Random) -> "PromptGenome":
            # Use LLM to mutate prompt
            mutations = [
                "Add more detail to the instruction",
                "Make the instruction more concise",
                "Add a few-shot example",
                "Change the persona",
                "Add chain-of-thought prompting",
                "Add constraints",
                "Rephrase for clarity",
            ]
            mutation = rng.choice(mutations)
            prompt = f"{self.prompt}\n\n[Mutation: {mutation}]"
            return EvolutionaryPromptingEngine.PromptGenome(prompt, self.mutation_scale)

        def crossover(self, other: "PromptGenome", rng: random.Random) -> "PromptGenome":
            # Combine prompts
            combined = f"{self.prompt}\n---\n{other.prompt}"
            return EvolutionaryPromptingEngine.PromptGenome(combined, (self.mutation_scale + other.mutation_scale) / 2)

        def clone(self) -> "PromptGenome":
            return EvolutionaryPromptingEngine.PromptGenome(self.prompt, self.mutation_scale)

        def distance(self, other: "PromptGenome") -> float:
            # Edit distance
            return abs(len(self.prompt) - len(other.prompt)) / max(len(self.prompt), len(other.prompt))

        def to_dict(self) -> Dict[str, Any]:
            return {"type": "prompt", "prompt": self.prompt, "mutation_scale": self.mutation_scale}

        @classmethod
        def from_dict(cls, data: Dict[str, Any]) -> "PromptGenome":
            return cls(data["prompt"], data["mutation_scale"])

        @classmethod
        def random(cls, shape: Any, rng: random.Random, mutation_scale: float) -> "PromptGenome":
            return cls("Solve this task:", mutation_scale)

    def evaluate(self, genome: PromptGenome) -> float:
        return self.evaluation_fn(genome.prompt)

    def behavior_descriptor(self, genome: PromptGenome) -> Tuple[float, ...]:
        # Behavior = LLM response embedding (simplified)
        return (len(genome.prompt), genome.prompt.count('\n'), genome.prompt.count('?'))

    def run(
        self,
        initial_population: List[PromptGenome],
        progress_callback: Callable[[GenerationSummary], None] | None = None,
    ) -> EvaluatedCandidate[PromptGenome]:
        return super().run(initial_population, progress_callback)


class EmergentCommunicationTask(Task):
    """Task where agents evolve communication protocol."""

    def __init__(
        self,
        num_agents: int = 2,
        vocab_size: int = 10,
        max_message_len: int = 5,
        grid_size: int = 5,
    ) -> None:
        self.num_agents = num_agents
        self.vocab_size = vocab_size
        self.max_message_len = max_message_len
        self.grid_size = grid_size
        self.name = "emergent_communication"

    def evaluate(self, genomes: List[Genome]) -> float:
        # Cooperative referential game
        # Speaker sees target, sends message, listener acts
        if len(genomes) < 2:
            return 0.0

        speaker, listener = genomes[0], genomes[1]
        total_reward = 0.0
        num_episodes = 20

        for _ in range(num_episodes):
            # Random target position
            target = (random.randint(0, self.grid_size - 1), random.randint(0, self.grid_size - 1))

            # Speaker generates message
            speaker_obs = np.array([target[0] / self.grid_size, target[1] / self.grid_size])
            if hasattr(speaker, 'evaluate'):
                message_logits = speaker.evaluate(speaker_obs)
            else:
                message_logits = np.random.randn(self.vocab_size)

            message = np.argmax(message_logits)

            # Listener receives message and acts
            listener_obs = np.array([message / self.vocab_size])
            if hasattr(listener, 'evaluate'):
                action_logits = listener.evaluate(listener_obs)
            else:
                action_logits = np.random.randn(self.grid_size * self.grid_size)

            action = np.argmax(action_logits)
            pred_pos = (action // self.grid_size, action % self.grid_size)

            reward = 1.0 if pred_pos == target else 0.0
            total_reward += reward

        return total_reward / num_episodes

    def behavior_descriptor(self, genome: Genome) -> Tuple[float, ...]:
        return (0.0,)


class QuantumInspiredGenome(Genome):
    """Genome with quantum-inspired superposition of states."""

    def __init__(
        self,
        amplitudes: np.ndarray,
        basis_states: List[Genome],
        measurement_prob: float = 0.1,
    ):
        self.amplitudes = amplitudes / np.linalg.norm(amplitudes)
        self.basis_states = basis_states
        self.measurement_prob = measurement_prob
        self.lineage_id = str(uuid.uuid4())[:8]
        self.age = 0

    def measure(self) -> Genome:
        """Collapse to a basis state."""
        idx = np.random.choice(len(self.basis_states), p=np.abs(self.amplitudes) ** 2)
        return self.basis_states[idx]

    def mutate(self, config: Any, rng: random.Random) -> "QuantumInspiredGenome":
        # Mutate amplitudes
        new_amplitudes = self.amplitudes + rng.normal(0, 0.1, self.amplitudes.shape)
        new_amplitudes = new_amplitudes / np.linalg.norm(new_amplitudes)

        # Mutate basis states
        new_basis = []
        for state in self.basis_states:
            if rng.random() < self.measurement_prob:
                new_basis.append(state.mutate(config, rng))
            else:
                new_basis.append(state)

        return QuantumInspiredGenome(new_amplitudes, new_basis, self.measurement_prob)

    def crossover(self, other: "QuantumInspiredGenome", rng: random.Random) -> "QuantumInspiredGenome":
        # Superposition crossover
        combined_amplitudes = (self.amplitudes + other.amplitudes) / 2
        combined_amplitudes = combined_amplitudes / np.linalg.norm(combined_amplitudes)

        combined_basis = self.basis_states + other.basis_states
        return QuantumInspiredGenome(combined_amplitudes, combined_basis, self.measurement_prob)

    def clone(self) -> "QuantumInspiredGenome":
        return QuantumInspiredGenome(self.amplitudes.copy(), self.basis_states.copy(), self.measurement_prob)

    def distance(self, other: "QuantumInspiredGenome") -> float:
        return float(np.linalg.norm(self.amplitudes - other.amplitudes))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "quantum",
            "amplitudes": self.amplitudes.tolist(),
            "basis_states": [s.to_dict() for s in self.basis_states],
            "measurement_prob": self.measurement_prob,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuantumInspiredGenome":
        from .core.genome import DenseGenome
        basis = [DenseGenome.from_dict(s) for s in data["basis_states"]]
        return cls(np.array(data["amplitudes"]), basis, data["measurement_prob"])

    @classmethod
    def random(cls, shape: Any, rng: random.Random, mutation_scale: float) -> "QuantumInspiredGenome":
        from .core.genome import DenseGenome
        num_basis = 4
        basis = [DenseGenome.random(100, mutation_scale, rng) for _ in range(num_basis)]
        amplitudes = np.ones(num_basis) / np.sqrt(num_basis)
        return cls(amplitudes, basis)


class OpenEndedEvolutionEngine:
    """Engine for open-ended evolution with no fixed objective."""

    def __init__(
        self,
        config: EvolutionConfig,
        task_generator: Callable[[], OpenEndedTask],
        archive: Archive,
        novelty_threshold: float = 0.1,
        max_challenges: int = 50,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config
        self.task_generator = task_generator
        self.archive = archive
        self.novelty_threshold = novelty_threshold
        self.max_challenges = max_challenges
        self.rng = rng or random.Random(config.seed)
        self.current_task = task_generator()
        self.challenge_archive: List[Dict[str, Any]] = []
        self.generation = 0

    def run(
        self,
        initial_population: List[Genome],
        progress_callback: Callable[[GenerationSummary], None] | None = None,
        max_generations: int = 1000,
    ) -> Dict[str, Any]:
        population = initial_population
        best_genome = None
        best_fitness = -float('inf')

        for gen in range(max_generations):
            self.generation = gen

            # Evaluate on current task
            scored = []
            for genome in population:
                fitness = self.current_task.evaluate(genome)
                descriptor = self.current_task.behavior_descriptor(genome)
                novelty = self.archive.novelty(descriptor)
                combined = (1.0 - self.config.novelty_weight) * fitness + \
                           self.config.novelty_weight * novelty
                self.archive.add(descriptor, fitness, genome)
                scored.append(EvaluatedCandidate(
                    genome=genome,
                    fitness=fitness,
                    novelty=novelty,
                    score=combined,
                    descriptor=descriptor,
                ))

            scored.sort(key=lambda c: c.score, reverse=True)

            if scored[0].fitness > best_fitness:
                best_fitness = scored[0].fitness
                best_genome = scored[0].genome.clone()

            # Generate new challenge if population solves current one
            avg_fitness = np.mean([s.fitness for s in scored])
            if avg_fitness > 0.9 and len(self.current_task.challenges) < self.max_challenges:
                new_challenge = self.current_task.generate_challenge(scored[0].genome)
                self.current_task.challenges.append(new_challenge)
                self.challenge_archive.append(new_challenge)

            # Standard evolution step
            population = self._next_generation(scored)

            if progress_callback:
                avg_nov = np.mean([s.novelty for s in scored])
                summary = GenerationSummary(
                    generation=gen,
                    best_fitness=scored[0].fitness,
                    best_score=scored[0].score,
                    avg_fitness=avg_fitness,
                    avg_novelty=avg_nov,
                    archive_size=len(self.archive.entries) if hasattr(self.archive, 'entries') else 0,
                )
                progress_callback(summary)

        return {
            "best_genome": best_genome,
            "best_fitness": best_fitness,
            "num_challenges": len(self.current_task.challenges),
            "challenges": self.challenge_archive,
        }

    def _next_generation(self, scored: List[EvaluatedCandidate]) -> List[Genome]:
        scored.sort(key=lambda c: c.score, reverse=True)
        n = len(scored)
        elite_count = max(1, int(self.config.elite_fraction * n))
        elites = [c.genome.clone() for c in scored[:elite_count]]

        def tournament() -> Genome:
            candidates = self.rng.sample(scored, min(self.config.tournament_size, len(scored)))
            return max(candidates, key=lambda c: c.score).genome

        new_pop = elites[:]
        mut_config = self.config.to_mutation_config() if hasattr(self.config, 'to_mutation_config') else None

        while len(new_pop) < n:
            parent1 = tournament()
            parent2 = tournament()
            child = parent1.crossover(parent2, self.rng)
            if self.rng.random() < self.config.mutation_rate:
                if mut_config:
                    child = child.mutate(mut_config, self.rng)
                else:
                    child = child.mutate(self.rng)
            new_pop.append(child)

        return new_pop[:n]


def create_llm_engine(
    config: EvolutionConfig,
    task: Task,
    archive: Archive,
    llm_client: Any,
) -> LLMMutationEngine:
    return LLMMutationEngine(config, task, archive, llm_client)


def create_prompt_engine(
    config: EvolutionConfig,
    llm_client: Any,
    base_prompt: str,
    evaluation_fn: Callable[[str], float],
    archive: Archive,
) -> EvolutionaryPromptingEngine:
    return EvolutionaryPromptingEngine(config, llm_client, base_prompt, evaluation_fn, archive)


def create_open_ended_engine(
    config: EvolutionConfig,
    task_generator: Callable[[], OpenEndedTask],
    archive: Archive,
) -> OpenEndedEvolutionEngine:
    return OpenEndedEvolutionEngine(config, task_generator, archive)