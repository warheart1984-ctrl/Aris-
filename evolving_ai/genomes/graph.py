from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Set, Tuple
import random
import uuid

import numpy as np

from evolving_ai.core import Genome, NetworkShape, MutationConfig


@dataclass
class GraphNode:
    node_id: int
    node_type: str  # "input", "hidden", "output"
    activation: str = "tanh"
    bias: float = 0.0
    layer: int = 0  # For feedforward ordering


@dataclass
class GraphConnection:
    source: int
    target: int
    weight: float
    enabled: bool = True
    innovation: int = 0


@dataclass
class GraphGenome(Genome):
    """Graph-based genome with arbitrary topology (NEAT-style)."""
    nodes: Dict[int, GraphNode] = field(default_factory=dict)
    connections: Dict[Tuple[int, int], GraphConnection] = field(default_factory=dict)
    input_nodes: List[int] = field(default_factory=list)
    output_nodes: List[int] = field(default_factory=list)
    next_node_id: int = 0
    next_innovation: int = 0
    mutation_scale: float = 0.1
    lineage_depth: int = 0
    age: int = 0

    def __post_init__(self) -> None:
        self._topological_order: List[int] | None = None

    def _compute_topological_order(self) -> List[int]:
        """Compute topological order for feedforward evaluation."""
        # Kahn's algorithm
        in_degree = {nid: 0 for nid in self.nodes}
        for (src, tgt), conn in self.connections.items():
            if conn.enabled:
                in_degree[tgt] = in_degree.get(tgt, 0) + 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        order = []
        while queue:
            nid = queue.pop(0)
            order.append(nid)
            for (src, tgt), conn in self.connections.items():
                if conn.enabled and src == nid:
                    in_degree[tgt] -= 1
                    if in_degree[tgt] == 0:
                        queue.append(tgt)

        # Add any remaining (cycles)
        for nid in self.nodes:
            if nid not in order:
                order.append(nid)

        self._topological_order = order
        return order

    def evaluate(self, inputs: List[float]) -> List[float]:
        """Forward pass through graph."""
        if self._topological_order is None:
            self._compute_topological_order()

        values = {}
        for i, nid in enumerate(self.input_nodes):
            values[nid] = inputs[i] if i < len(inputs) else 0.0

        for nid in self._topological_order:
            if nid in self.input_nodes:
                continue
            node = self.nodes[nid]
            total = node.bias
            for (src, tgt), conn in self.connections.items():
                if conn.enabled and tgt == nid and src in values:
                    total += values[src] * conn.weight
            # Activation
            if node.activation == "tanh":
                values[nid] = math.tanh(total)
            elif node.activation == "sigmoid":
                values[nid] = 1.0 / (1.0 + math.exp(-total))
            elif node.activation == "relu":
                values[nid] = max(0.0, total)
            else:
                values[nid] = math.tanh(total)

        return [values.get(nid, 0.0) for nid in self.output_nodes]

    def mutate(self, config: MutationConfig, rng: random.Random) -> "GraphGenome":
        import copy
        new_genome = copy.deepcopy(self)
        new_genome.lineage_depth += 1
        new_genome.age = 0

        # Mutate weights
        for conn in new_genome.connections.values():
            if rng.random() < config.mutation_probability:
                conn.weight += rng.gauss(0.0, new_genome.mutation_scale)

        # Add connection
        if rng.random() < 0.05:
            possible = [
                (src, tgt) for src in new_genome.nodes for tgt in new_genome.nodes
                if src != tgt and (src, tgt) not in new_genome.connections
                and new_genome.nodes[src].layer <= new_genome.nodes[tgt].layer
            ]
            if possible:
                src, tgt = rng.choice(possible)
                new_genome.connections[(src, tgt)] = GraphConnection(
                    src, tgt, rng.gauss(0.0, 1.0), True, new_genome.next_innovation
                )
                new_genome.next_innovation += 1

        # Add node (split connection)
        if rng.random() < 0.03 and new_genome.connections:
            conn = rng.choice(list(new_genome.connections.values()))
            if conn.enabled:
                conn.enabled = False
                new_id = new_genome.next_node_id
                new_genome.next_node_id += 1

                # Determine layer for new node
                src_layer = new_genome.nodes[conn.source].layer
                tgt_layer = new_genome.nodes[conn.target].layer
                new_layer = (src_layer + tgt_layer) / 2

                new_genome.nodes[new_id] = GraphNode(
                    new_id, "hidden", rng.choice(["tanh", "sigmoid", "relu"]), 0.0, new_layer
                )

                # Add connections: source -> new -> target
                new_genome.connections[(conn.source, new_id)] = GraphConnection(
                    conn.source, new_id, 1.0, True, new_genome.next_innovation
                )
                new_genome.next_innovation += 1
                new_genome.connections[(new_id, conn.target)] = GraphConnection(
                    new_id, conn.target, conn.weight, True, new_genome.next_innovation
                )
                new_genome.next_innovation += 1

        # Toggle connection
        if rng.random() < 0.01 and new_genome.connections:
            conn = rng.choice(list(new_genome.connections.values()))
            conn.enabled = not conn.enabled

        # Mutate activation
        for node in new_genome.nodes.values():
            if node.node_type == "hidden" and rng.random() < 0.02:
                node.activation = rng.choice(["tanh", "sigmoid", "relu", "gaussian", "sine"])

        # Update mutation scale
        new_genome.mutation_scale = max(0.01, min(3.0,
            new_genome.mutation_scale * math.exp(rng.gauss(0.0, config.mutation_scale_learning_rate))
        ))

        new_genome._topological_order = None
        return new_genome

    def crossover(self, other: "GraphGenome", rng: random.Random) -> "GraphGenome":
        import copy
        # Match by innovation numbers
        child = GraphGenome(
            mutation_scale=(self.mutation_scale + other.mutation_scale) / 2,
            lineage_depth=max(self.lineage_depth, other.lineage_depth) + 1,
            next_node_id=max(self.next_node_id, other.next_node_id),
            next_innovation=max(self.next_innovation, other.next_innovation),
        )

        # Inherit nodes (union)
        all_innovations = set()
        for conn in self.connections.values():
            all_innovations.add(conn.innovation)
        for conn in other.connections.values():
            all_innovations.add(conn.innovation)

        for innov in sorted(all_innovations):
            c1 = next((c for c in self.connections.values() if c.innovation == innov), None)
            c2 = next((c for c in other.connections.values() if c.innovation == innov), None)

            if c1 and c2:
                chosen = c1 if rng.random() < 0.5 else c2
            elif c1:
                chosen = c1
            else:
                chosen = c2

            if chosen:
                child.connections[(chosen.source, chosen.target)] = copy.deepcopy(chosen)
                # Ensure nodes exist
                for nid in [chosen.source, chosen.target]:
                    if nid not in child.nodes:
                        n1 = self.nodes.get(nid)
                        n2 = other.nodes.get(nid)
                        child.nodes[nid] = copy.deepcopy(n1 if n1 else n2)

        # Inherit input/output nodes
        child.input_nodes = list(set(self.input_nodes) | set(other.input_nodes))
        child.output_nodes = list(set(self.output_nodes) | set(other.output_nodes))

        child._topological_order = None
        return child

    def distance(self, other: "GraphGenome") -> float:
        # NEAT compatibility distance
        innovations1 = {c.innovation for c in self.connections.values()}
        innovations2 = {c.innovation for c in other.connections.values()}

        shared = innovations1 & innovations2
        disjoint = innovations1 ^ innovations2

        if not shared:
            return len(disjoint) * 1.0

        weight_diff = sum(
            abs(self.connections[(next((s, t) for (s, t), c in self.connections.items() if c.innovation == i))].weight -
                other.connections[(next((s, t) for (s, t), c in other.connections.items() if c.innovation == i))].weight)
            for i in shared
        ) / len(shared)

        n = max(len(self.connections), len(other.connections))
        return len(disjoint) / max(1, n) + weight_diff

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "graph",
            "nodes": {
                str(nid): {
                    "node_type": n.node_type,
                    "activation": n.activation,
                    "bias": n.bias,
                    "layer": n.layer,
                }
                for nid, n in self.nodes.items()
            },
            "connections": [
                {"source": s, "target": t, "weight": c.weight, "enabled": c.enabled, "innovation": c.innovation}
                for (s, t), c in self.connections.items()
            ],
            "input_nodes": self.input_nodes,
            "output_nodes": self.output_nodes,
            "next_node_id": self.next_node_id,
            "next_innovation": self.next_innovation,
            "mutation_scale": self.mutation_scale,
            "lineage_depth": self.lineage_depth,
            "age": self.age,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphGenome":
        nodes = {
            int(nid): GraphNode(int(nid), n["node_type"], n["activation"], n["bias"], n["layer"])
            for nid, n in data["nodes"].items()
        }
        connections = {
            (c["source"], c["target"]): GraphConnection(c["source"], c["target"], c["weight"], c["enabled"], c["innovation"])
            for c in data["connections"]
        }
        return cls(
            nodes=nodes,
            connections=connections,
            input_nodes=data["input_nodes"],
            output_nodes=data["output_nodes"],
            next_node_id=data["next_node_id"],
            next_innovation=data["next_innovation"],
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
    ) -> "GraphGenome":
        genome = cls(mutation_scale=mutation_scale)
        node_id = 0

        # Input nodes
        for i in range(shape.input_size):
            genome.nodes[node_id] = GraphNode(node_id, "input", "linear", 0.0, 0)
            genome.input_nodes.append(node_id)
            node_id += 1

        # Hidden nodes
        for layer_idx, layer_size in enumerate(shape.hidden_layers):
            for _ in range(layer_size):
                genome.nodes[node_id] = GraphNode(node_id, "hidden", "tanh", 0.0, layer_idx + 1)
                node_id += 1

        # Output nodes
        for i in range(shape.output_size):
            genome.nodes[node_id] = GraphNode(node_id, "output", shape.output_activation, 0.0, len(shape.hidden_layers) + 1)
            genome.output_nodes.append(node_id)
            node_id += 1

        genome.next_node_id = node_id

        # Connect layers
        layer_nodes = [genome.input_nodes]
        idx = shape.input_size
        for layer_size in shape.hidden_layers:
            layer_nodes.append(list(range(idx, idx + layer_size)))
            idx += layer_size
        layer_nodes.append(genome.output_nodes)

        for li, (src_layer, tgt_layer) in enumerate(zip(layer_nodes[:-1], layer_nodes[1:])):
            for src in src_layer:
                for tgt in tgt_layer:
                    if rng.random() < 0.5:
                        genome.connections[(src, tgt)] = GraphConnection(
                            src, tgt, rng.gauss(0.0, 1.0), True, genome.next_innovation
                        )
                        genome.next_innovation += 1

        return genome


@dataclass
class ModuleGenome(Genome):
    """Modular genome with reusable sub-networks."""
    modules: Dict[str, GraphGenome] = field(default_factory=dict)
    main_genome: GraphGenome = field(default_factory=GraphGenome)
    module_usage: Dict[str, int] = field(default_factory=dict)  # How many times each module is used
    mutation_scale: float = 0.1
    lineage_depth: int = 0
    age: int = 0

    def evaluate(self, inputs: List[float]) -> List[float]:
        # Evaluate main genome, which can call modules
        return self.main_genome.evaluate(inputs)

    def mutate(self, config: MutationConfig, rng: random.Random) -> "ModuleGenome":
        import copy
        new_genome = copy.deepcopy(self)
        new_genome.lineage_depth += 1
        new_genome.age = 0

        # Mutate main genome
        new_genome.main_genome = new_genome.main_genome.mutate(config, rng)

        # Mutate modules
        new_modules = {}
        for name, module in new_genome.modules.items():
            if rng.random() < 0.3:
                new_modules[name] = module.mutate(config, rng)
            else:
                new_modules[name] = module
        new_genome.modules = new_modules

        # Add new module from subgraph of main
        if rng.random() < 0.05 and len(new_genome.main_genome.nodes) > 5:
            # Extract a subgraph as new module
            pass  # Simplified

        # Duplicate module
        if rng.random() < 0.02 and new_genome.modules:
            name, module = rng.choice(list(new_genome.modules.items()))
            new_name = f"{name}_dup_{rng.randint(1000, 9999)}"
            new_genome.modules[new_name] = copy.deepcopy(module)

        new_genome.mutation_scale = max(0.01, min(3.0,
            new_genome.mutation_scale * math.exp(rng.gauss(0.0, config.mutation_scale_learning_rate))
        ))

        return new_genome

    def crossover(self, other: "ModuleGenome", rng: random.Random) -> "ModuleGenome":
        import copy
        child = ModuleGenome(
            mutation_scale=(self.mutation_scale + other.mutation_scale) / 2,
            lineage_depth=max(self.lineage_depth, other.lineage_depth) + 1,
        )
        child.main_genome = self.main_genome.crossover(other.main_genome, rng)

        # Merge modules
        all_modules = {}
        for name, mod in self.modules.items():
            all_modules[name] = mod
        for name, mod in other.modules.items():
            if name not in all_modules or rng.random() < 0.5:
                all_modules[name] = mod
        child.modules = all_modules

        return child

    def distance(self, other: "ModuleGenome") -> float:
        return self.main_genome.distance(other.main_genome) + \
               abs(len(self.modules) - len(other.modules)) * 0.1

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "modular",
            "modules": {name: mod.to_dict() for name, mod in self.modules.items()},
            "main_genome": self.main_genome.to_dict(),
            "mutation_scale": self.mutation_scale,
            "lineage_depth": self.lineage_depth,
            "age": self.age,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleGenome":
        modules = {name: GraphGenome.from_dict(mod) for name, mod in data["modules"].items()}
        return cls(
            modules=modules,
            main_genome=GraphGenome.from_dict(data["main_genome"]),
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
    ) -> "ModuleGenome":
        return cls(
            main_genome=GraphGenome.random(shape, rng, mutation_scale),
            mutation_scale=mutation_scale,
        )


import math