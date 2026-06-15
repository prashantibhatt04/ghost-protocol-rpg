"""
Ghost Protocol — Session Metrics Store
Thread-safe in-memory metrics for the telemetry dashboard.
Resets on new session; no persistence needed.
"""
import re
import threading
from collections import defaultdict, Counter
from datetime import datetime


_IQ_FILE_MAP = {
    'WORLD': 'world_overview.md',
    'CORPORATIONS': 'corporations.md',
    'DISTRICTS': 'districts.md',
    'CREW': 'crew_profiles.md',
    'HEISTS': 'heist_targets.md',
    'FACTIONS': 'factions.md',
    'GEAR': 'items_and_gear.md',
    'RULES': 'homebrew_rules.md',
}

_STOPWORDS = {
    'that', 'this', 'with', 'from', 'have', 'they', 'will', 'your', 'what',
    'into', 'their', 'when', 'been', 'some', 'which', 'were', 'more', 'then',
    'than', 'just', 'also', 'there', 'where', 'here', 'about', 'over', 'after',
}


class MetricsStore:
    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self._agent = defaultdict(lambda: {
                'calls': 0, 'tokens': 0, 'elapsed': 0.0, 'success': 0,
            })
            self._iq_queries = []          # [{query, files, elapsed_ms}]
            self._iq_file_hits = Counter()
            self._phase_history = []       # [{phase, turn, ts}]
            self._alert_history = []       # [{level, reason, turn, ts}]
            self._dice = []                # [{total, sides, label}]
            self._inputs_validated = 0
            self._blocked = []             # [str]
            self._output_checks = 0
            self._session_start = datetime.now().isoformat()

    # ── Recording helpers ──────────────────────────────────────────────────────

    def record_agent_call(self, name: str, tokens: int, elapsed: float, success: bool):
        with self._lock:
            m = self._agent[name]
            m['calls']   += 1
            m['tokens']  += tokens
            m['elapsed'] += elapsed
            m['success'] += int(success)

    def record_iq_query(self, query: str, file_keys: list[str], elapsed_ms: float):
        files = [
            _IQ_FILE_MAP.get(k.split('_')[0].upper(), k.lower() + '.md')
            for k in file_keys
        ]
        with self._lock:
            self._iq_queries.append({
                'query': query[:60],
                'files': files,
                'elapsed_ms': round(elapsed_ms, 1),
            })
            for f in files:
                self._iq_file_hits[f] += 1

    def record_phase_change(self, phase: str, turn: int):
        with self._lock:
            self._phase_history.append({
                'phase': phase,
                'turn': turn,
                'ts': datetime.now().strftime('%H:%M:%S'),
            })

    def record_alert_change(self, from_level: str, to_level: str, reason: str, turn: int):
        with self._lock:
            self._alert_history.append({
                'from': from_level,
                'level': to_level,
                'reason': reason[:60],
                'turn': turn,
                'ts': datetime.now().strftime('%H:%M:%S'),
            })

    def record_dice(self, total: int, sides: int, label: str):
        with self._lock:
            self._dice.append({'total': total, 'sides': sides, 'label': label})

    def record_input_validated(self):
        with self._lock:
            self._inputs_validated += 1

    def record_blocked(self, reason: str):
        with self._lock:
            self._blocked.append(reason[:80])

    # ── Snapshot ───────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a JSON-serialisable snapshot of all current metrics."""
        with self._lock:
            agents = {}
            for name, m in self._agent.items():
                calls = m['calls']
                agents[name] = {
                    'calls':        calls,
                    'tokens':       m['tokens'],
                    'avg_elapsed':  round(m['elapsed'] / calls, 2) if calls else 0,
                    'success_rate': round(m['success'] / calls * 100, 1) if calls else 0,
                }

            # Top IQ query terms
            term_counter = Counter()
            for q in self._iq_queries:
                words = re.findall(r'\b[a-z]{4,}\b', q['query'].lower())
                term_counter.update(w for w in words if w not in _STOPWORDS)
            top_terms = [[w, c] for w, c in term_counter.most_common(8)]

            avg_iq_ms = 0.0
            if self._iq_queries:
                avg_iq_ms = round(
                    sum(q['elapsed_ms'] for q in self._iq_queries) / len(self._iq_queries), 1
                )

            dice_summary = dict(Counter(d['label'] for d in self._dice))

            return {
                'session_start': self._session_start,
                'agents': agents,
                'iq': {
                    'total_queries':  len(self._iq_queries),
                    'file_hits':      dict(self._iq_file_hits.most_common()),
                    'top_terms':      top_terms,
                    'avg_elapsed_ms': avg_iq_ms,
                    'recent':         list(self._iq_queries[-5:]),
                },
                'game': {
                    'phase_history': list(self._phase_history),
                    'alert_history': list(self._alert_history),
                    'dice_history':  list(self._dice),
                    'dice_summary':  dice_summary,
                },
                'safety': {
                    'inputs_validated': self._inputs_validated,
                    'blocked_count':    len(self._blocked),
                    'blocked_inputs':   list(self._blocked),
                    'output_checks':    self._inputs_validated,  # one check per validated input
                },
            }
