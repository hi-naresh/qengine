#!/usr/bin/env python3
"""Pivot 05 evidence: visualize the sibling-only ring migration topology.

Renders three small graphs: (a) fully-connected (all islands talk to all),
(b) random ring (independent of regime structure), (c) sibling-only ring
(islands sharing a macro-cluster form a local ring). The third is what
IslandPilot uses; the first two are what we considered and rejected.
"""
import os
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
os.makedirs(RESULTS, exist_ok=True)

# Toy structure: 3 macros, 4 leaves each = 12 islands.
N_MACROS = 3
LEAVES_PER_MACRO = 4
N_ISLANDS = N_MACROS * LEAVES_PER_MACRO


def position(i):
    """Place island i at a position grouped by macro-cluster."""
    macro = i // LEAVES_PER_MACRO
    leaf = i % LEAVES_PER_MACRO
    macro_angle = 2 * math.pi * macro / N_MACROS
    macro_x = 3 * math.cos(macro_angle)
    macro_y = 3 * math.sin(macro_angle)
    leaf_angle = 2 * math.pi * leaf / LEAVES_PER_MACRO
    return macro_x + math.cos(leaf_angle), macro_y + math.sin(leaf_angle)


def draw(ax, edges, title):
    pts = [position(i) for i in range(N_ISLANDS)]
    # cluster shading
    for m in range(N_MACROS):
        cx, cy = 3 * math.cos(2 * math.pi * m / N_MACROS), 3 * math.sin(2 * math.pi * m / N_MACROS)
        ax.add_patch(plt.Circle((cx, cy), 1.6, alpha=0.08, color=f'C{m}'))
    for u, v in edges:
        ax.plot([pts[u][0], pts[v][0]], [pts[u][1], pts[v][1]], '-', color='gray', alpha=0.5, linewidth=0.8)
    for i, (x, y) in enumerate(pts):
        macro = i // LEAVES_PER_MACRO
        ax.plot(x, y, 'o', color=f'C{macro}', markersize=12)
        ax.annotate(f'L{i}', (x, y), textcoords='offset points', xytext=(8, 0), fontsize=8)
    ax.set_xlim(-5, 5)
    ax.set_ylim(-5, 5)
    ax.set_aspect('equal')
    ax.set_title(title)
    ax.axis('off')


fully_connected = [(i, j) for i in range(N_ISLANDS) for j in range(i + 1, N_ISLANDS)]
random_ring = [(i, (i + 1) % N_ISLANDS) for i in range(N_ISLANDS)]
sibling_ring = []
for m in range(N_MACROS):
    for k in range(LEAVES_PER_MACRO):
        u = m * LEAVES_PER_MACRO + k
        v = m * LEAVES_PER_MACRO + (k + 1) % LEAVES_PER_MACRO
        sibling_ring.append((u, v))

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
draw(axes[0], fully_connected, '(a) Fully connected\nrejected: ignores regime structure')
draw(axes[1], random_ring, '(b) Single global ring\nrejected: cross-cluster migration unjustified')
draw(axes[2], sibling_ring, '(c) Sibling-only ring (chosen)\ntopology = clustering hierarchy')
fig.suptitle('Pivot 05: Migration topology options', fontsize=14)
fig.tight_layout()
out = os.path.join(RESULTS, 'topology_options.png')
fig.savefig(out, dpi=120)
plt.close(fig)
print(f'Saved {out}')
print(f'Edge counts: fully_connected={len(fully_connected)}, single_ring={len(random_ring)}, sibling_ring={len(sibling_ring)}')
