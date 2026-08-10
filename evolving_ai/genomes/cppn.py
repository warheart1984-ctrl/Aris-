from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, List, Tuple
import math
import random
import uuid

import numpy as np

from evolving_ai.core import Genome, NetworkShape, MutationConfig


class CPPNNode:
    """A node in a Compositional Pattern Producing Network."""
    
    def __init__(
        self,
        node_id: int,
        activation: str = "tanh",
        bias: float = 0.0,
    ) -> None:
        self.node_id = node_id
        self.activation = activation
        self.bias = bias
        self.incoming: List[Tuple[int, float]] = []  # (source_id, weight)
        self.outgoing: List[Tuple[int, float]] = []  # (target_id, weight)

    def activate(self, x: float) -> float:
        if self.activation == "tanh":
            return math.tanh(x + self.bias)
        elif self.activation == "sigmoid":
            return 1.0 / (1.0 + math.exp(-(x + self.bias)))
        elif self.activation == "relu":
            return max(0.0, x + self.bias)
        elif self.activation == "gaussian":
            return math.exp(-(x + self.bias) ** 2)
        elif self.activation == "sine":
            return math.sin(x + self.bias)
        elif self.activation == "abs":
            return abs(x + self.bias)
        elif self.activation == "linear":
            return x + self.bias
        else:
            return math.tanh(x + self.bias)


@dataclass
class CPPNGenome(Genome):
    """CPPN genome for indirect encoding of patterns."""
    nodes: List[CPPNNode] = field(default_factory=list)
    connections: List[Tuple[int, int, float]] = field(default_factory=list)  # (source, target, weight)
    input_nodes: List[int] = field(default_factory=list)
    output_nodes: List[int] = field(default_factory=list)
    mutation_scale: float = 0.1
    lineage_depth: int = 0
    age: int = 0

    def __post_init__(self) -> None:
        self._build_node_map()

    def _build_node_map(self) -> None:
        self._node_map = {n.node_id: n for n in self.nodes}
        for n in self.nodes:
            n.incoming = []
            n.outgoing = []
        for src, tgt, w in self.connections:
            if src in self._node_map and tgt in self._node_map:
                self._node_map[src].outgoing.append((tgt, w))
                self._node_map[tgt].incoming.append((src, w))

    def evaluate(self, inputs: List[float]) -> List[float]:
        """Forward pass through CPPN."""
        # Set input node values
        for i, node_id in enumerate(self.input_nodes):
            self._node_map[node_id].bias = inputs[i] if i < len(inputs) else 0.0

        # Topological evaluation (simplified - assumes no cycles)
        evaluated = set(self.input_nodes)
        output_values = {}

        # Simple iterative evaluation
        for _ in range(len(self.nodes)):
            progress = False
            for node in self.nodes:
                if node.node_id in evaluated:
                    continue
                if all(src in evaluated for src, _ in node.incoming):
                    # Compute input
                    total = sum(
                        output_values[src] * w
                        for src, w in node.incoming
                    )
                    output_values[node.node_id] = node.activate(total)
                    evaluated.add(node.node_id)
                    progress = True
            if not progress:
                break

        return [output_values.get(nid, 0.0) for nid in self.output_nodes]

    def query(self, x: float, y: float, z: float = 0.0) -> float:
        """Query CPPN at coordinate (x, y, z) - for HyperNEAT substrate."""
        return self.evaluate([x, y, z])[0] if self.output_nodes else 0.0

    def mutate(self, config: MutationConfig, rng: random.Random) -> "CPPNGenome":
        new_nodes = []
        for node in self.nodes:
            new_node = CPPNNode(node.node_id, node.activation, node.bias)
            if rng.random() < config.mutation_probability:
                new_node.bias += rng.gauss(0.0, self.mutation_scale)
            if rng.random() < 0.05:
                new_node.activation = rng.choice(["tanh", "sigmoid", "relu", "gaussian", "sine", "abs", "linear"])
            new_nodes.append(new_node)

        new_connections = list(self.connections)
        # Add connection
        if rng.random() < 0.1 and len(self.nodes) >= 2:
            src = rng.choice(self.nodes).node_id
            tgt = rng.choice(self.nodes).node_id
            if src != tgt and (src, tgt) not in [(s, t) for s, t, _ in self.connections]:
                new_connections.append((src, tgt, rng.gauss(0.0, self.mutation_scale)))
        # Remove connection
        if rng.random() < 0.05 and new_connections:
            new_connections.pop(rng.randrange(len(new_connections)))
        # Mutate weights
        new_connections = [
            (s, t, w + rng.gauss(0.0, self.mutation_scale) if rng.random() < config.mutation_probability else w)
            for s, t, w in new_connections
        ]

        # Add node
        if rng.random() < 0.03:
            new_id = max(n.node_id for n in new_nodes) + 1 if new_nodes else 0
            new_nodes.append(CPPNNode(new_id, rng.choice(["tanh", "sigmoid", "relu", "gaussian", "sine", "abs", "linear"])))

        next_scale = max(0.01, min(3.0, self.mutation_scale * math.exp(rng.gauss(0.0, config.mutation_scale_learning_rate))))

        return CPPNGenome(
            nodes=new_nodes,
            connections=new_connections,
            input_nodes=self.input_nodes,
            output_nodes=self.output_nodes,
            mutation_scale=next_scale,
            lineage_depth=self.lineage_depth + 1,
            age=0,
        )

    def crossover(self, other: "CPPNGenome", rng: random.Random) -> "CPPNGenome":
        # Simple crossover: merge nodes and connections
        all_nodes = {n.node_id: n for n in self.nodes}
        for n in other.nodes:
            if n.node_id not in all_nodes or rng.random() < 0.5:
                all_nodes[n.node_id] = n

        all_conns = {}
        for s, t, w in self.connections:
            all_conns[(s, t)] = w
        for s, t, w in other.connections:
            if (s, t) not in all_conns or rng.random() < 0.5:
                all_conns[(s, t)] = w

        return CPPNGenome(
            nodes=list(all_nodes.values()),
            connections=[(s, t, w) for (s, t), w in all_conns.items()],
            input_nodes=self.input_nodes,
            output_nodes=self.output_nodes,
            mutation_scale=(self.mutation_scale + other.mutation_scale) / 2,
            lineage_depth=max(self.lineage_depth, other.lineage_depth) + 1,
            age=0,
        )

    def distance(self, other: "CPPNGenome") -> float:
        # Structural distance
        node_diff = abs(len(self.nodes) - len(other.nodes))
        conn_diff = abs(len(self.connections) - len(other.connections))
        return float(node_diff + conn_diff)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "cppn",
            "nodes": [
                {"id": n.node_id, "activation": n.activation, "bias": n.bias}
                for n in self.nodes
            ],
            "connections": [
                {"source": s, "target": t, "weight": w}
                for s, t, w in self.connections
            ],
            "input_nodes": self.input_nodes,
            "output_nodes": self.output_nodes,
            "mutation_scale": self.mutation_scale,
            "lineage_depth": self.lineage_depth,
            "age": self.age,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CPPNGenome":
        nodes = [CPPNNode(n["id"], n["activation"], n["bias"]) for n in data["nodes"]]
        connections = [(c["source"], c["target"], c["weight"]) for c in data["connections"]]
        return cls(
            nodes=nodes,
            connections=connections,
            input_nodes=data["input_nodes"],
            output_nodes=data["output_nodes"],
            mutation_scale=data["mutation_scale"],
            lineage_depth=data.get("lineage_depth", 0),
            age=data.get("age", 0),
        )

    @classmethod
    def random(
        cls,
        shape: NetworkShape,
        rng: random.Random,
        mutation_scale: float,
    ) -> "CPPNGenome":
        # Create minimal CPPN for substrate querying
        input_nodes = []
        output_nodes = []
        
        for i in range(shape.input_size + 2):  # +2 for x, y coordinates
            node_id = i
            input_nodes.append(node_id)
        
        for i in range(shape.output_size):
            node_id = shape.input_size + 2 + i
            output_nodes.append(node_id)

        nodes = []
        for i in range(len(input_nodes) + len(output_nodes)):
            if i < len(input_nodes):
                act = "linear"
            else:
                act = rng.choice(["tanh", "sigmoid", "relu", "gaussian", "sine"])
            nodes.append(CPPNNode(i, act))

        # Connect inputs to outputs with some hidden nodes
        connections = []
        for inp in input_nodes:
            for out in output_nodes:
                if rng.random() < 0.5:
                    connections.append((inp, out, rng.gauss(0.0, 1.0)))

        return cls(
            nodes=nodes,
            connections=connections,
            input_nodes=input_nodes,
            output_nodes=output_nodes,
            mutation_scale=mutation_scale,
        )


class CPPNSubstrate:
    """HyperNEAT substrate for querying CPPN at spatial coordinates."""

    def __init__(
        self,
        input_coords: List[Tuple[float, float]],
        hidden_coords: List[List[Tuple[float, float]]],
        output_coords: List[Tuple[float, float]],
        activation: str = "tanh",
    ) -> None:
        self.input_coords = input_coords
        self.hidden_coords = hidden_coords
        self.output_coords = output_coords
        self.activation = activation
        self.all_coords = input_coords + [c for layer in hidden_coords for c in layer] + output_coords

    def query_weights(self, cppn: CPPNGenome) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """Query CPPN to get weights for each layer connection."""
        weights = []
        biases = []

        layer_sizes = [len(self.input_coords)] + [len(l) for l in self.hidden_coords] + [len(self.output_coords)]
        layer_offsets = [0]
        for s in layer_sizes[:-1]:
            layer_offsets.append(layer_offsets[-1] + s)

        for li, (in_size, out_size) in enumerate(zip(layer_sizes[:-1], layer_sizes[1:])):
            w = np.zeros((out_size, in_size))
            b = np.zeros(out_size)

            in_start = layer_offsets[li]
            out_start = layer_offsets[li + 1]

            for i in range(in_size):
                for j in range(out_size):
                    xi, yi = self.all_coords[in_start + i]
                    xj, yj = self.all_coords[out_start + j]
                    # Query CPPN for weight
                    weight = cppn.query(xi, yi, xj - xi)  # dx as third input
                    w[j, i] = weight

            for j in range(out_size):
                xj, yj = self.all_coords[out_start + j]
                bias = cppn.query(xj, yj, 0.0)
                b[j] = bias

            weights.append(w)
            biases.append(b)

        return weights, biases


def create_hyperneat_substrate(
    input_size: int,
    hidden_layers: List[int],
    output_size: int,
    geometry: str = "grid",
) -> CPPNSubstrate:
    """Create standard HyperNEAT substrate geometries."""
    if geometry == "grid":
        # 2D grid layout
        def grid_coords(n: int) -> List[Tuple[float, float]]:
            cols = int(math.ceil(math.sqrt(n)))
            rows = int(math.ceil(n / cols))
            coords = []
            for i in range(n):
                r = i // cols
                c = i % cols
                x = (c - (cols - 1) / 2) / max(1, cols - 1) * 2
                y = (r - (rows - 1) / 2) / max(1, rows - 1) * 2
                coords.append((x, y))
            return coords

        input_coords = grid_coords(input_size)
        hidden_coords = [grid_coords(h) for h in hidden_layers]
        output_coords = grid_coords(output_size)

        return CPPNSubstrate(input_coords, hidden_coords, output_coords)
    else:
        # Linear layout
        def linear_coords(n: int) -> List[Tuple[float, float]]:
            return [(i / max(1, n - 1) * 2 - 1, 0.0) for i in range(n)]

        input_coords = linear_coords(input_size)
        hidden_coords = [linear_coords(h) for h in hidden_layers]
        output_coords = linear_coords(output_size)

        return CPPNSubstrate(input_coords, hidden_coords, output_coords)