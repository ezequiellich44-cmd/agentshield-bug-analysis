"""
Reproduce all 4 AgentShield rules-engine bugs described in README.md.
Requires the agentshield source tree on sys.path (core/engine.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'vendored'))
from core.engine import SpendControlEngine

e = SpendControlEngine()

FAILURES = []


def check(name, actual, expected):
    ok = actual == expected
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {actual!r}, expected {expected!r}")
    if not ok:
        FAILURES.append(name)


# Bug 1 — agent_id omission bypasses daily_total
priors = [{'agent_id': 'agent-7', 'amount': '90', 'merchant': 'm', 'category': 'c',
           'timestamp': '2026-08-18T08:00:00Z'}]
rules = [{'id': 'daily', 'type': 'daily_total', 'priority': 1,
          'params': {'max_daily': '100'}, 'action': 'BLOCK'}]
t_with = {'agent_id': 'agent-7', 'amount': '20', 'merchant': 'm', 'category': 'c',
          'timestamp': '2026-08-18T10:00:00Z'}
t_wo = {'amount': '20', 'merchant': 'm', 'category': 'c',
        'timestamp': '2026-08-18T10:00:00Z'}
check('Bug1 daily_total blocks when agent_id present (110>100)',
      e.evaluate(t_with, rules, priors)['decision'], 'BLOCKED')
check('Bug1 daily_total bypassed when agent_id omitted',
      e.evaluate(t_wo, rules, priors)['decision'], 'APPROVED')

# Bug 2 — missing timestamp bypasses daily_total
t_no_ts = {'agent_id': 'agent-7', 'amount': '20', 'merchant': 'm', 'category': 'c'}
check('Bug2 daily_total blocks with timestamp',
      e.evaluate(t_with, rules, priors)['decision'], 'BLOCKED')
check('Bug2 daily_total bypassed without timestamp',
      e.evaluate(t_no_ts, rules, priors)['decision'], 'APPROVED')

# Bug 3 — missing timestamp bypasses velocity
vrules = [{'id': 'vel', 'type': 'velocity', 'priority': 1,
           'params': {'window_minutes': 60, 'max_count': 3}, 'action': 'BLOCK'}]
vpriors = [
    {'agent_id': 'a1', 'amount': '1', 'merchant': 'm', 'category': 'c',
     'timestamp': '2026-08-18T09:30:00Z'},
    {'agent_id': 'a1', 'amount': '1', 'merchant': 'm', 'category': 'c',
     'timestamp': '2026-08-18T09:40:00Z'},
    {'agent_id': 'a1', 'amount': '1', 'merchant': 'm', 'category': 'c',
     'timestamp': '2026-08-18T09:50:00Z'},
]
v_ts = {'agent_id': 'a1', 'amount': '1', 'merchant': 'm', 'category': 'c',
        'timestamp': '2026-08-18T10:00:00Z'}
v_nots = {'agent_id': 'a1', 'amount': '1', 'merchant': 'm', 'category': 'c'}
check('Bug3 velocity blocks with timestamp (4>3)',
      e.evaluate(v_ts, vrules, vpriors)['decision'], 'BLOCKED')
check('Bug3 velocity bypassed without timestamp',
      e.evaluate(v_nots, vrules, vpriors)['decision'], 'APPROVED')

# Bug 4 — session_id int/str type confusion
srules = [{'id': 'sess', 'type': 'session_budget', 'priority': 1,
           'params': {'max_session': '10'}, 'action': 'BLOCK'}]
spriors = [{'agent_id': 'a1', 'session_id': '123', 'amount': '8',
            'merchant': 'm', 'category': 'c'}]
s1 = {'agent_id': 'a1', 'session_id': '123', 'amount': '3', 'merchant': 'm', 'category': 'c'}
s2 = {'agent_id': 'a1', 'session_id': 123, 'amount': '3', 'merchant': 'm', 'category': 'c'}
check('Bug4 session_budget blocks same str session (11>10)',
      e.evaluate(s1, srules, spriors)['decision'], 'BLOCKED')
check('Bug4 session_budget bypassed via int session_id',
      e.evaluate(s2, srules, spriors)['decision'], 'APPROVED')

print()
if FAILURES:
    print(f'{len(FAILURES)} reproductions FAILED (engine behavior differs): {FAILURES}')
    sys.exit(1)
print('All 4 bug reproductions verified against the engine.')
