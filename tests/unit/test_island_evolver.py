"""Tests for the IslandEvolver GA engine."""

import os
import tempfile

import numpy as np
import pytest

from qengine.framework.components.island_evolver import (
    GENE_BOUNDS,
    Genome,
    IslandEvolver,
    Population,
)


# ---------------------------------------------------------------------------
# Genome tests
# ---------------------------------------------------------------------------

class TestGenome:
    def test_random_in_bounds(self):
        g = Genome.random(seed=42)
        for name, (lo, hi, dtype) in GENE_BOUNDS.items():
            val = g.genes[name]
            assert lo <= val <= hi, f"{name}={val} out of [{lo}, {hi}]"
            assert isinstance(val, dtype), f"{name} should be {dtype}, got {type(val)}"

    def test_crossover_produces_child(self):
        p1 = Genome.random(seed=1)
        p2 = Genome.random(seed=2)
        child = p1.crossover(p2, seed=3)
        assert isinstance(child, Genome)
        # Child genes should come from one parent or the other
        for name in GENE_BOUNDS:
            assert child.genes[name] in (p1.genes[name], p2.genes[name])

    def test_mutate_stays_in_bounds(self):
        g = Genome.random(seed=10)
        for _ in range(20):
            m = g.mutate(sigma_pct=0.3, seed=None)
            for name, (lo, hi, dtype) in GENE_BOUNDS.items():
                assert lo <= m.genes[name] <= hi, f"{name}={m.genes[name]} out of bounds"

    def test_to_dict_roundtrip(self):
        g = Genome.random(seed=7)
        g.fitness = 42.5
        d = g.to_dict()
        # All 6 pipeline genes should be present
        for name in GENE_BOUNDS:
            assert name in d["genes"], f"Missing gene: {name}"

        g2 = Genome.from_dict(d)
        assert g2.id == g.id
        assert g2.fitness == g.fitness
        for name in GENE_BOUNDS:
            assert g2.genes[name] == g.genes[name]

    def test_random_different_seeds(self):
        g1 = Genome.random(seed=1)
        g2 = Genome.random(seed=2)
        # Should differ in at least some genes
        diffs = sum(1 for n in GENE_BOUNDS if g1.genes[n] != g2.genes[n])
        assert diffs > 0


# ---------------------------------------------------------------------------
# Population tests
# ---------------------------------------------------------------------------

class TestPopulation:
    def test_creates_n_individuals(self):
        pop = Population("test_island", size=20, seed=42)
        assert len(pop.individuals) == 20

    def test_evaluate_sets_fitness(self):
        pop = Population("test", size=10, seed=1)
        pop.evaluate(lambda genes: genes["base_size_pct"])
        for ind in pop.individuals:
            assert ind.fitness is not None
            assert ind.fitness == ind.genes["base_size_pct"]

    def test_evolve_preserves_elites(self):
        pop = Population("test", size=10, seed=1)
        pop.evaluate(lambda genes: genes["base_size_pct"])
        # Record top-2 fitness values
        top_fitness = sorted([g.fitness for g in pop.individuals], reverse=True)[:2]
        pop.evolve(elitism=2)
        # Elites should still be present
        new_fitness = sorted([g.fitness for g in pop.individuals if g.fitness is not None], reverse=True)
        for tf in top_fitness:
            assert tf in new_fitness

    def test_evolve_changes_population(self):
        pop = Population("test", size=20, seed=1)
        pop.evaluate(lambda genes: genes["base_size_pct"])
        old_ids = {g.id for g in pop.individuals}
        pop.evolve(elitism=2)
        new_ids = {g.id for g in pop.individuals}
        # At least some new individuals (besides elites)
        assert len(new_ids - old_ids) > 0

    def test_inject_replaces_worst(self):
        pop = Population("test", size=5, seed=1)
        pop.evaluate(lambda genes: genes["base_size_pct"])
        alien = Genome.random(seed=99)
        alien.fitness = 999.0
        pop.inject(alien)
        assert alien in pop.individuals


# ---------------------------------------------------------------------------
# IslandEvolver tests
# ---------------------------------------------------------------------------

class TestIslandEvolver:
    def test_creates_islands(self):
        evolver = IslandEvolver(
            leaf_ids=["R0", "R1", "R2"],
            config={"pop_size": 10, "seed": 42},
        )
        assert set(evolver.populations.keys()) == {"R0", "R1", "R2"}
        for pop in evolver.populations.values():
            assert len(pop.individuals) == 10

    def test_get_best_genome(self):
        evolver = IslandEvolver(
            leaf_ids=["R0"],
            config={"pop_size": 5, "seed": 1},
        )
        # Set fitness
        for g in evolver.populations["R0"].individuals:
            g.fitness = np.random.rand()
        best = evolver.get_best_genome("R0")
        assert "genes" in best
        assert "fitness" in best
        # All 6 pipeline genes should be present
        for name in GENE_BOUNDS:
            assert name in best["genes"], f"Missing gene: {name}"

    def test_migrate_siblings_exchanges(self):
        evolver = IslandEvolver(
            leaf_ids=["R0", "R1"],
            config={"pop_size": 5, "seed": 1},
            sibling_groups={"macro0": ["R0", "R1"]},
        )
        # Set fitness so migration has something to work with
        for lid in ["R0", "R1"]:
            for g in evolver.populations[lid].individuals:
                g.fitness = np.random.rand()

        evolver.migrate_siblings()
        log = evolver.get_migration_log()
        assert len(log) >= 2  # bidirectional ring

    def test_save_load_roundtrip(self):
        evolver = IslandEvolver(
            leaf_ids=["R0", "R1"],
            config={"pop_size": 5, "seed": 42},
            sibling_groups={"macro0": ["R0", "R1"]},
        )
        for lid in evolver.leaf_ids:
            for g in evolver.populations[lid].individuals:
                g.fitness = np.random.rand()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            evolver.save(path)
            loaded = IslandEvolver.load(path)
            assert loaded.leaf_ids == evolver.leaf_ids
            assert len(loaded.populations["R0"].individuals) == 5
            # Genome data preserved
            orig_best = evolver.get_best_genome("R0")
            loaded_best = loaded.get_best_genome("R0")
            assert orig_best["fitness"] == loaded_best["fitness"]
        finally:
            os.unlink(path)

    def test_fitness_summary(self):
        evolver = IslandEvolver(
            leaf_ids=["R0"],
            config={"pop_size": 5, "seed": 1},
        )
        # Evaluate without evolving so all have fitness
        for g in evolver.populations["R0"].individuals:
            g.fitness = g.genes["base_size_pct"]
        summary = evolver.get_fitness_summary()
        assert "R0" in summary
        assert summary["R0"]["n"] == 5
        assert summary["R0"]["best"] is not None

    def test_diversity_stats(self):
        evolver = IslandEvolver(
            leaf_ids=["R0"],
            config={"pop_size": 10, "seed": 1},
        )
        stats = evolver.get_diversity_stats()
        assert "R0" in stats
        # Should have std for each gene
        assert set(stats["R0"].keys()) == set(GENE_BOUNDS.keys())
