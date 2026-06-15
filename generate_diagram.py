#!/usr/bin/env python3
"""Generate Ghost Protocol architecture diagram."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# ─── Colours ──────────────────────────────────────────────────────────────────
BG     = '#0a0a0f'
CYAN   = '#00ff9f'   # specialist agents
BLUE   = '#00b4ff'   # Foundry IQ / Knowledge Base
ORANGE = '#ff9f00'   # Azure OpenAI
PURPLE = '#9f00ff'   # Game State
GOLD   = '#ffd700'   # Game Master
GREY   = '#c8c8c8'   # Player Input / Flask UI
WHITE  = '#ffffff'   # arrows + labels

fig, axes = plt.subplots(figsize=(24, 17))
fig.patch.set_facecolor(BG)
axes.set_facecolor(BG)
axes.set_xlim(0, 24)
axes.set_ylim(0, 17)
axes.axis('off')


# ─── Drawing primitives ───────────────────────────────────────────────────────

def box(cx, cy, w, h, fc, title, s1=None, s2=None, tc='#0a0a0f'):
    """Rounded glow box with title + up to two subtitle lines."""
    # outer glow
    axes.add_patch(FancyBboxPatch(
        (cx - w/2 - 0.20, cy - h/2 - 0.12), w + 0.40, h + 0.24,
        boxstyle='round,pad=0.15', facecolor=fc, edgecolor='none',
        alpha=0.22, zorder=2))
    # filled body
    axes.add_patch(FancyBboxPatch(
        (cx - w/2, cy - h/2), w, h,
        boxstyle='round,pad=0.10', facecolor=fc, edgecolor=fc,
        alpha=0.90, linewidth=2.5, zorder=3))
    # border glow
    axes.add_patch(FancyBboxPatch(
        (cx - w/2, cy - h/2), w, h,
        boxstyle='round,pad=0.10', facecolor='none', edgecolor=fc,
        alpha=0.50, linewidth=6.0, zorder=4))
    # text
    if s1 is None:
        axes.text(cx, cy, title, ha='center', va='center',
                  fontsize=11, fontweight='bold', color=tc, zorder=5)
    elif s2 is None:
        axes.text(cx, cy + 0.16, title, ha='center', va='center',
                  fontsize=11, fontweight='bold', color=tc, zorder=5)
        axes.text(cx, cy - 0.18, s1, ha='center', va='center',
                  fontsize=8.5, color=tc, alpha=0.82, zorder=5)
    else:
        axes.text(cx, cy + 0.26, title, ha='center', va='center',
                  fontsize=11, fontweight='bold', color=tc, zorder=5)
        axes.text(cx, cy + 0.02, s1, ha='center', va='center',
                  fontsize=8.5, color=tc, alpha=0.88, zorder=5)
        axes.text(cx, cy - 0.24, s2, ha='center', va='center',
                  fontsize=7.5, color=tc, alpha=0.72, zorder=5)


def kb_box(cx, cy, w, h, docs):
    """Dark-fill knowledge base box with document list."""
    axes.add_patch(FancyBboxPatch(
        (cx - w/2 - 0.20, cy - h/2 - 0.12), w + 0.40, h + 0.24,
        boxstyle='round,pad=0.15', facecolor='#003a6e', edgecolor='none',
        alpha=0.35, zorder=2))
    axes.add_patch(FancyBboxPatch(
        (cx - w/2, cy - h/2), w, h,
        boxstyle='round,pad=0.10', facecolor='#001e3a', edgecolor=BLUE,
        alpha=0.96, linewidth=2.5, zorder=3))
    axes.add_patch(FancyBboxPatch(
        (cx - w/2, cy - h/2), w, h,
        boxstyle='round,pad=0.10', facecolor='none', edgecolor=BLUE,
        alpha=0.50, linewidth=6.0, zorder=4))
    axes.text(cx, cy + 1.72, 'Knowledge Base', ha='center', va='center',
              fontsize=11, fontweight='bold', color=WHITE, zorder=5)
    axes.text(cx, cy + 1.37, '8 Markdown Documents  ·  Toronto 2047 Lore',
              ha='center', va='center', fontsize=8, color=BLUE, alpha=0.85, zorder=5)
    for i, doc in enumerate(docs):
        axes.text(cx, cy + 1.00 - i * 0.30, f'  ·  {doc}',
                  ha='center', va='center', fontsize=7.5,
                  color='#66ccff', alpha=0.90, zorder=5,
                  fontfamily='monospace')


def arr(x1, y1, x2, y2, bidir=False, col=WHITE, lw=1.9, ms=15, rad=0.0):
    """Arrow (uni- or bidirectional) with optional curvature."""
    style = '<->' if bidir else '->'
    axes.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style, color=col, linewidth=lw,
        connectionstyle=f'arc3,rad={rad}',
        mutation_scale=ms, alpha=0.88, zorder=1))


def lbl(x, y, text, col=WHITE, fs=7.5, fw='bold'):
    """Floating label, dark-background pill."""
    axes.text(x, y, text, ha='center', va='center', fontsize=fs,
              color=col, fontweight=fw, zorder=6,
              bbox=dict(facecolor=BG, edgecolor='none', alpha=0.88,
                        boxstyle='round,pad=0.30'))


# ─── Title ────────────────────────────────────────────────────────────────────
axes.text(12, 16.55, 'GHOST PROTOCOL', ha='center', va='center',
          fontsize=28, fontweight='bold', color=CYAN,
          fontfamily='monospace', zorder=5)
axes.text(12, 16.02, 'Multi-Agent Cyberpunk Heist RPG  ·  System Architecture',
          ha='center', va='center', fontsize=11.5, color=WHITE, alpha=0.52, zorder=5)
axes.plot([1.5, 22.5], [15.66, 15.66], color=CYAN, lw=0.9, alpha=0.28, zorder=1)

# ─── Nodes ────────────────────────────────────────────────────────────────────

# Player Input
box(7.2, 14.4, 3.2, 0.85, GREY, 'Player Input')

# Game Master  (orchestrator — centre stage)
box(12.0, 12.0, 6.0, 1.40, GOLD,
    'Game Master  (Ghost)',
    'Orchestrates all agents  ·  Routes  ·  Synthesises  ·  Narrates')

# Game State (left of GM)
box(3.5, 12.0, 3.8, 1.30, PURPLE,
    'Game State', 'SQLite',
    'Phase · Crew status · World flags', tc=WHITE)

# Azure OpenAI (right of GM)
box(21.0, 12.0, 4.0, 1.30, ORANGE,
    'Azure OpenAI',
    'GPT-4o via Azure Foundry', 'All LLM inference')

# Specialist agents — row across bottom half
AGENTS = [
    (1.8,  8.2, 'Wraith',  'Enforcer'),
    (4.8,  8.2, 'Cipher',  'Hacker'),
    (7.8,  8.2, 'Shadow',  'Infiltrator'),
    (10.8, 8.2, 'Patch',   'Fixer'),
    (13.8, 8.2, 'Vex',     'Rival Operator'),
]
AW, AH = 2.60, 1.05
for xp, yp, name, role in AGENTS:
    box(xp, yp, AW, AH, CYAN, name, role)

# Foundry IQ (right column, aligned with agents)
box(21.0, 8.2, 4.0, 1.30, BLUE,
    'Foundry IQ',
    'Azure AI Search',
    '73 documents · 8 knowledge files')

# Knowledge Base (below Foundry IQ)
KB_DOCS = [
    'world_overview.md', 'corporations.md',
    'districts.md',      'crew_profiles.md',
    'heist_targets.md',  'factions.md',
    'items_and_gear.md', 'homebrew_rules.md',
]
kb_box(21.0, 3.80, 4.20, 4.10, KB_DOCS)

# Flask Web UI (bottom)
box(7.2, 1.40, 5.0, 1.05, GREY,
    'Flask Web UI',
    'Reasoning panel  ·  Crew status  ·  Mission log')

# ─── Arrows ───────────────────────────────────────────────────────────────────

# 1. Player → Game Master
arr(8.2, 13.98, 10.8, 12.70)
lbl(9.8, 13.40, 'Orchestrates all agents', col='#dddddd', fs=7.5)

# 2. Player → Flask UI  (strong left curve, stays outside agent row)
arr(5.6, 13.98, 4.7, 1.93, rad=-0.22, col='#999999')
lbl(1.6, 9.6, 'Web\ninterface', col='#aaaaaa', fs=7.5)

# 3. GM ↔ Game State  (horizontal left)
arr(9.0, 12.0, 5.4, 12.0, bidir=True)

# 4. GM → Azure OpenAI  (horizontal right)
arr(15.0, 12.0, 19.0, 12.0)

# 5. GM → Foundry IQ  (diagonal right-down)
arr(15.0, 11.65, 19.0, 8.85)
lbl(17.4, 10.45, 'Knowledge Retrieval\n+ Citations', col=BLUE, fs=7.5)

# 6. GM ↔ each specialist agent  (fan from GM bottom)
GM_CX, GM_HALF_W = 12.0, 3.0
for i, (xp, yp, name, role) in enumerate(AGENTS):
    t = i / (len(AGENTS) - 1)
    gm_exit_x = GM_CX - GM_HALF_W * 0.82 + t * GM_HALF_W * 1.64
    arr(gm_exit_x, 11.30, xp, yp + AH / 2, bidir=True)

# 7. Foundry IQ → Knowledge Base  (straight down)
arr(21.0, 7.55, 21.0, 5.90)
lbl(22.2, 6.72, 'Documents', col=BLUE, fs=7.5)

# ─── Heist phases footer ─────────────────────────────────────────────────────
axes.text(12, 0.38,
          'RECON  →  INFILTRATION  →  EXECUTION  →  EXTRACTION',
          ha='center', va='center', fontsize=9.5,
          color=CYAN, alpha=0.38, fontfamily='monospace', zorder=5)

# ─── Save ─────────────────────────────────────────────────────────────────────
for fmt in ('png', 'svg'):
    fname = f'architecture_diagram.{fmt}'
    kw = dict(bbox_inches='tight', facecolor=BG, edgecolor='none')
    if fmt == 'png':
        kw['dpi'] = 180
    plt.savefig(fname, format=fmt, **kw)
    print(f'Saved: {fname}')

plt.close()
