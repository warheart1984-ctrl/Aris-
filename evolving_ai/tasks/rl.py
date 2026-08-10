from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np
import math

from evolving_ai.core import Task, Genome


class RLTask(Task):
    """Base class for RL environment tasks."""

    def __init__(
        self,
        env_name: str,
        max_steps: int = 1000,
        num_episodes: int = 3,
        render: bool = False,
    ) -> None:
        self.env_name = env_name
        self.max_steps = max_steps
        self.num_episodes = num_episodes
        self.render = render
        self._env = None
        self._obs_space = None
        self._action_space = None

    @property
    def name(self) -> str:
        return self.env_name

    @abstractmethod
    def _make_env(self):
        pass

    def _get_env(self):
        if self._env is None:
            self._env = self._make_env()
        return self._env

    def evaluate(self, genome: Genome) -> float:
        env = self._get_env()
        total_reward = 0.0

        for _ in range(self.num_episodes):
            obs, _ = env.reset()
            episode_reward = 0.0

            for step in range(self.max_steps):
                action = self._genome_to_action(genome, obs)
                obs, reward, terminated, truncated, _ = env.step(action)
                episode_reward += reward

                if self.render:
                    env.render()

                if terminated or truncated:
                    break

            total_reward += episode_reward

        env.close()
        self._env = None
        return total_reward / self.num_episodes

    def behavior_descriptor(self, genome: Genome) -> Tuple[float, ...]:
        """Return final observation or trajectory statistics as behavior."""
        env = self._get_env()
        obs, _ = env.reset()
        trajectory = []

        for _ in range(min(100, self.max_steps)):
            action = self._genome_to_action(genome, obs)
            obs, _, terminated, truncated, _ = env.step(action)
            trajectory.append(obs)
            if terminated or truncated:
                break

        env.close()
        self._env = None

        # Return mean/std of trajectory as descriptor
        if trajectory:
            arr = np.array(trajectory)
            return tuple(np.concatenate([np.mean(arr, axis=0), np.std(arr, axis=0)]))
        return tuple()

    @abstractmethod
    def _genome_to_action(self, genome: Genome, obs: np.ndarray) -> np.ndarray:
        pass


class GymTask(RLTask):
    """Gym/Gymnasium environment task."""

    def __init__(
        self,
        env_id: str,
        max_steps: int = 1000,
        num_episodes: int = 3,
        render: bool = False,
        wrappers: List[Callable] = None,
    ) -> None:
        super().__init__(env_id, max_steps, num_episodes, render)
        self.env_id = env_id
        self.wrappers = wrappers or []

    def _make_env(self):
        import gymnasium as gym
        env = gym.make(self.env_id, render_mode="human" if self.render else None)
        for wrapper in self.wrappers:
            env = wrapper(env)
        self._obs_space = env.observation_space
        self._action_space = env.action_space
        return env

    def _genome_to_action(self, genome: Genome, obs: np.ndarray) -> np.ndarray:
        # Assume genome has evaluate method that takes obs and returns action
        if hasattr(genome, 'evaluate'):
            action = genome.evaluate(obs)
        elif hasattr(genome, 'to_phenotype'):
            phenotype = genome.to_phenotype()
            action = phenotype.predict(obs)
        else:
            # Fallback: random action
            action = self._get_env().action_space.sample()
        return np.asarray(action, dtype=np.float32)


class ProcgenTask(RLTask):
    """Procgen environment task for generalization testing."""

    def __init__(
        self,
        env_name: str,
        num_levels: int = 100,
        start_level: int = 0,
        distribution_mode: str = "easy",
        max_steps: int = 1000,
        num_episodes: int = 5,
        render: bool = False,
    ) -> None:
        super().__init__(f"procgen_{env_name}", max_steps, num_episodes, render)
        self.env_name = env_name
        self.num_levels = num_levels
        self.start_level = start_level
        self.distribution_mode = distribution_mode

    def _make_env(self):
        import procgen
        import gymnasium as gym
        env = gym.make(
            f"procgen-{self.env_name}-v0",
            num_levels=self.num_levels,
            start_level=self.start_level,
            distribution_mode=self.distribution_mode,
            render_mode="human" if self.render else None,
        )
        self._obs_space = env.observation_space
        self._action_space = env.action_space
        return env

    def _genome_to_action(self, genome: Genome, obs: np.ndarray) -> np.ndarray:
        if hasattr(genome, 'evaluate'):
            action = genome.evaluate(obs)
        elif hasattr(genome, 'to_phenotype'):
            phenotype = genome.to_phenotype()
            action = phenotype.predict(obs)
        else:
            action = self._get_env().action_space.sample()
        return np.asarray(action, dtype=np.float32)


class PyBulletTask(RLTask):
    """PyBullet physics simulation task."""

    def __init__(
        self,
        env_name: str,
        max_steps: int = 1000,
        num_episodes: int = 3,
        render: bool = False,
        **env_kwargs,
    ) -> None:
        super().__init__(env_name, max_steps, num_episodes, render)
        self.env_kwargs = env_kwargs

    def _make_env(self):
        import pybullet_envs
        import gymnasium as gym
        env = gym.make(self.env_name, render_mode="human" if self.render else None, **self.env_kwargs)
        self._obs_space = env.observation_space
        self._action_space = env.action_space
        return env

    def _genome_to_action(self, genome: Genome, obs: np.ndarray) -> np.ndarray:
        if hasattr(genome, 'evaluate'):
            action = genome.evaluate(obs)
        elif hasattr(genome, 'to_phenotype'):
            phenotype = genome.to_phenotype()
            action = phenotype.predict(obs)
        else:
            action = self._get_env().action_space.sample()
        return np.asarray(action, dtype=np.float32)


class IsaacGymTask(RLTask):
    """Isaac Gym high-performance GPU simulation task."""

    def __init__(
        self,
        task_name: str,
        num_envs: int = 4096,
        max_steps: int = 1000,
        headless: bool = True,
        **task_kwargs,
    ) -> None:
        super().__init__(task_name, max_steps, 1, False)
        self.task_name = task_name
        self.num_envs = num_envs
        self.headless = headless
        self.task_kwargs = task_kwargs
        self._vec_env = None

    def _make_env(self):
        # Isaac Gym doesn't use standard gym interface
        # This is a placeholder for the actual Isaac Gym task creation
        raise NotImplementedError("Isaac Gym requires specific setup - use isaacgymenvs package")

    def evaluate(self, genome: Genome) -> float:
        # Vectorized evaluation across many environments
        if self._vec_env is None:
            self._vec_env = self._make_vec_env()

        obs = self._vec_env.reset()
        total_rewards = np.zeros(self.num_envs)

        for _ in range(self.max_steps):
            actions = self._genome_to_action_batch(genome, obs)
            obs, rewards, dones, _ = self._vec_env.step(actions)
            total_rewards += rewards
            if np.all(dones):
                break

        return float(np.mean(total_rewards))

    def _make_vec_env(self):
        raise NotImplementedError("Isaac Gym vectorized env setup required")

    def _genome_to_action_batch(self, genome: Genome, obs_batch: np.ndarray) -> np.ndarray:
        raise NotImplementedError("Batch inference required for Isaac Gym")


class MultiAgentTask(Task):
    """Multi-agent task with coevolution support."""

    def __init__(
        self,
        env_name: str,
        num_agents: int = 2,
        max_steps: int = 1000,
        num_episodes: int = 3,
        competitive: bool = True,
    ) -> None:
        self.env_name = env_name
        self.num_agents = num_agents
        self.max_steps = max_steps
        self.num_episodes = num_episodes
        self.competitive = competitive
        self._env = None

    @property
    def name(self) -> str:
        return f"multiagent_{self.env_name}"

    def _make_env(self):
        import gymnasium as gym
        # Multi-agent environments typically use PettingZoo
        raise NotImplementedError("Use PettingZooEnv for multi-agent")

    def evaluate(self, genomes: List[Genome]) -> List[float]:
        """Evaluate a team of genomes against each other or environment."""
        if len(genomes) != self.num_agents:
            raise ValueError(f"Expected {self.num_agents} genomes, got {len(genomes)}")

        # For competitive: round-robin tournament
        if self.competitive:
            return self._competitive_eval(genomes)
        else:
            return self._cooperative_eval(genomes)

    def _competitive_eval(self, genomes: List[Genome]) -> List[float]:
        # Each pair plays, winner gets fitness
        fitness = [0.0] * self.num_agents
        # Simplified: random for now
        return [float(np.random.random()) for _ in genomes]

    def _cooperative_eval(self, genomes: List[Genome]) -> List[float]:
        # Team shares fitness
        env = self._make_env()
        total_reward = 0.0

        for _ in range(self.num_episodes):
            obs, _ = env.reset()
            episode_reward = 0.0
            for _ in range(self.max_steps):
                actions = {}
                for i, genome in enumerate(genomes):
                    agent_obs = obs[i] if isinstance(obs, (list, tuple)) else obs
                    if hasattr(genome, 'evaluate'):
                        actions[f"agent_{i}"] = genome.evaluate(agent_obs)
                    else:
                        actions[f"agent_{i}"] = env.action_space(f"agent_{i}").sample()

                obs, rewards, terminated, truncated, _ = env.step(actions)
                episode_reward += sum(rewards.values()) if isinstance(rewards, dict) else rewards
                if all(terminated.values()) if isinstance(terminated, dict) else terminated:
                    break

            total_reward += episode_reward

        env.close()
        shared_fitness = total_reward / self.num_episodes
        return [shared_fitness] * self.num_agents

    def behavior_descriptor(self, genome: Genome) -> Tuple[float, ...]:
        return tuple()


class CoevolutionTask(Task):
    """Coevolution task: predator-prey, host-parasite, etc."""

    def __init__(
        self,
        predator_task: Task,
        prey_task: Task,
        num_generations: int = 10,
    ) -> None:
        self.predator_task = predator_task
        self.prey_task = prey_task
        self.num_generations = num_generations
        self.current_gen = 0

    @property
    def name(self) -> str:
        return f"coevolution_{self.predator_task.name}_vs_{self.prey_task.name}"

    def evaluate(self, genome: Genome) -> float:
        # Fitness depends on opponent population
        raise NotImplementedError("Use CoevolutionEngine for this")

    def behavior_descriptor(self, genome: Genome) -> Tuple[float, ...]:
        return tuple()


def make_gym_task(env_id: str, **kwargs) -> GymTask:
    return GymTask(env_id, **kwargs)


def make_procgen_task(env_name: str, **kwargs) -> ProcgenTask:
    return ProcgenTask(env_name, **kwargs)


def make_pybullet_task(env_name: str, **kwargs) -> PyBulletTask:
    return PyBulletTask(env_name, **kwargs)


# Registry
RL_TASK_REGISTRY = {
    "gym": make_gym_task,
    "procgen": make_procgen_task,
    "pybullet": make_pybullet_task,
}


def create_rl_task(task_type: str, *args, **kwargs) -> RLTask:
    if task_type not in RL_TASK_REGISTRY:
        raise ValueError(f"Unknown RL task type: {task_type}. Available: {list(RL_TASK_REGISTRY.keys())}")
    return RL_TASK_REGISTRY[task_type](*args, **kwargs)