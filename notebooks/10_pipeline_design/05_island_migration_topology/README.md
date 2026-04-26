# Pivot 05 — Island Migration Topology

## Context

Pivot 04 established per-leaf populations (islands). Each island evolves on its own slice of data with its own population of genomes. Without inter-island communication, each population is fully isolated; with too much communication, the islands collapse into one global population and the per-regime-specialisation benefit is lost.

The classical island-model parameter is the *migration topology*: the graph specifying which islands periodically exchange best-genomes.

## Problem

Three reasonable topologies for an N-island model:

1. **Fully connected.** Every island periodically samples top-genomes from every other island. Maximises information transfer but ignores the regime hierarchy — a high-vol-trending island can flood a low-vol-ranging island with genomes whose parameters are inappropriate for the receiving regime.
2. **Single global ring.** Every island is connected to its two neighbours in a single cycle. The ring is independent of the regime structure — neighbour pairs are arbitrary.
3. **Sibling-only ring.** Each macro-cluster forms its own local ring among its leaves. Cross-macro migration is forbidden. Migration only occurs between leaves of the same macro-cluster.

## What we tried

Choice 3 was selected on a structural / first-principles argument rather than on a comparison sweep. The argument:

- **Macro-cluster meaning.** A macro-cluster groups leaves whose feature distributions are mutually closer than they are to any other macro-cluster's leaves. By construction, a sibling pair shares more relevant feature-space structure than a cross-macro pair.
- **Migration utility.** A migrated genome is useful to the receiving island only if the source island's data resembles the receiver's. Sibling pairs satisfy this constraint by clustering construction; cross-macro pairs do not.
- **Domain-derived topology.** Both the choice to evolve per-regime (Pivot 04) and the choice of clustering hierarchy (Pivot 03) commit us to "regime structure carries information about parameter suitability." Migration topology should respect the same structure rather than impose an independent graph on top of it. The topology is *derived* from the clustering hierarchy, not specified independently.

This is a structural distinction relative to prior island-model work (Whitley et al. 1998; Lopes et al. 2012; Chideme et al. 2025) where topology is typically chosen for parallelism / convergence reasons independent of the problem domain.

The script `01_topology_diagram.py` renders the three options on a toy 3-macro × 4-leaf example for quick visual reference.

## Result

The trained pipeline uses sibling-only ring migration (`island_evolver.py`). Each macro-cluster's leaves form a ring; migration occurs every K generations between ring-adjacent siblings. Cross-macro genomes are never exchanged.

This is among the architectural-novelty claims highlighted in the dissertation: the migration graph is *derived* from the regime hierarchy itself rather than being an independent design parameter (`papers/drafts/dist/7_discussion.md`).

## Conclusion

Sibling-only ring migration. Topology derives from the clustering hierarchy.

## Next move

→ **Pivot 06 — Real-Engine Fitness.** Topology resolved, the next architectural choice is what *fitness function* the GA optimises. Early experiments used a fast surrogate simulator; we found this misled the GA into evolving genomes that the production engine refused.

## Sources

- **Pipeline source:** `pipelines/_shared/IslandPilot/island_evolver.py` (migration logic).
- **Paper:** `papers/drafts/dist/3_system_architecture.md` §3.4 and `7_discussion.md` (architectural novelty section). The paper's "domain-derived topology" claim cites this pivot.
- **Related work contrast:** Whitley et al. (1998) — fixed topology; Lopes et al. (2012) — Q-learning adaptive topology; Chideme et al. (2025) — multi-architecture parallel populations. None derive topology from the problem domain.
