# AgentShield Rules Engine — Security Audit

Security analysis of the [AgentShield](https://github.com/kindrat86/agentshield) spend-control
engine (`core/engine.py`). Four reproducible **false-negative** bugs found and verified against
the published source.

> Status: findings were prepared for the "$1,000 Break the AgentShield Rules Engine" bounty
> (kindrat86/agentshield#1). The maintainer **withdrew the bounty** on 2026-08-12
> ("pre-revenue open source, no cash budget"), so no payout exists. The findings remain valid
> against the engine as of the last published commit.

## Summary

| # | Bug | Rule(s) | Class | Root cause |
|---|-----|---------|-------|-----------|
| 1 | `agent_id` omission resets cumulative counters | `daily_total`, `session_budget`, `hitl_threshold` | False negative | Optional `agent_id` gates prior-transaction aggregation; omitting it means priors are never summed |
| 2 | Missing/invalid `timestamp` bypasses daily spend | `daily_total` | False negative | `_extract_date` returns `None`; the `prior_date == txn_date` guard silently skips all priors |
| 3 | Missing/invalid `timestamp` bypasses velocity | `velocity` | False negative | `_parse_ts` returns `None`; `_rule_applicable` marks the rule skipped and it never fires |
| 4 | `session_id` type confusion splits one budget into many | `session_budget` | False negative | `prior.get(session_field) == session_id` uses loose equality, so `123` (int) and `"123"` (str) are different sessions |

## Reproductions

All four are verified with the real engine from the repo (Python 3.11, `decimal.Decimal`).

### Bug 1 — `agent_id` omission (daily_total)

```python
from core.engine import SpendControlEngine
e = SpendControlEngine()
priors = [{'agent_id': 'agent-7', 'amount': '90', 'merchant': 'm',
           'category': 'c', 'timestamp': '2026-08-18T08:00:00Z'}]
rules  = [{'id': 'daily', 'type': 'daily_total', 'priority': 1,
           'params': {'max_daily': '100'}, 'action': 'BLOCK'}]
t_with = {'agent_id': 'agent-7', 'amount': '20', 'merchant': 'm',
          'category': 'c', 'timestamp': '2026-08-18T10:00:00Z'}
t_wo   = {'amount': '20', 'merchant': 'm', 'category': 'c',
          'timestamp': '2026-08-18T10:00:00Z'}
assert e.evaluate(t_with, rules, priors)['decision'] == 'BLOCKED'   # 110 > 100
assert e.evaluate(t_wo,   rules, priors)['decision'] == 'APPROVED'  # bypass
```

The engine documents `agent_id` as optional (`"Optionally 'agent_id', 'timestamp', ..."`), yet
`_check_daily_total` (and `_check_session_budget`, `_check_hitl_threshold`) aggregate priors only
when `prior.get('agent_id') == agent_id`. Omitting `agent_id` on every call therefore makes the
cumulative rules see only the current transaction — the daily/session budget is never enforced.

### Bug 2 — missing `timestamp` bypasses daily_total

```python
t_no_ts = {'agent_id': 'agent-7', 'amount': '20', 'merchant': 'm', 'category': 'c'}
assert e.evaluate(t_no_ts, rules, priors)['decision'] == 'APPROVED'
```

`_extract_date(None)` → `None`; the `if txn_date and prior_date and prior_date == txn_date`
guard short-circuits, so prior spend is never added.

### Bug 3 — missing `timestamp` bypasses velocity

```python
vrules  = [{'id': 'vel', 'type': 'velocity', 'priority': 1,
            'params': {'window_minutes': 60, 'max_count': 3}, 'action': 'BLOCK'}]
vpriors = [{'agent_id': 'a1', 'amount': '1', 'merchant': 'm', 'category': 'c',
            'timestamp': '2026-08-18T09:30:00Z'},
           {'agent_id': 'a1', 'amount': '1', 'merchant': 'm', 'category': 'c',
            'timestamp': '2026-08-18T09:40:00Z'},
           {'agent_id': 'a1', 'amount': '1', 'merchant': 'm', 'category': 'c',
            'timestamp': '2026-08-18T09:50:00Z'}]
v_ts   = {'agent_id': 'a1', 'amount': '1', 'merchant': 'm', 'category': 'c',
          'timestamp': '2026-08-18T10:00:00Z'}
v_nots = {'agent_id': 'a1', 'amount': '1', 'merchant': 'm', 'category': 'c'}
assert e.evaluate(v_ts,   vrules, vpriors)['decision'] == 'BLOCKED'   # 4 > 3
assert e.evaluate(v_nots, vrules, vpriors)['decision'] == 'APPROVED'  # bypass
```

### Bug 4 — `session_id` int/str type confusion

```python
srules  = [{'id': 'sess', 'type': 'session_budget', 'priority': 1,
            'params': {'max_session': '10'}, 'action': 'BLOCK'}]
spriors = [{'agent_id': 'a1', 'session_id': '123', 'amount': '8',
            'merchant': 'm', 'category': 'c'}]
s1 = {'agent_id': 'a1', 'session_id': '123', 'amount': '3', 'merchant': 'm', 'category': 'c'}
s2 = {'agent_id': 'a1', 'session_id': 123,   'amount': '3', 'merchant': 'm', 'category': 'c'}
assert e.evaluate(s1, srules, spriors)['decision'] == 'BLOCKED'   # 11 > 10
assert e.evaluate(s2, srules, spriors)['decision'] == 'APPROVED'  # 3 > 10 -> different bucket
```

## Suggested fixes

1. **Make `agent_id` mandatory** for all agent-scoped rules (or fail-closed when absent).
2. **Fail-closed on missing timestamp** for `daily_total` / `velocity` / `session_budget`:
   treat an unparseable `timestamp` as a blocking condition instead of skipping the rule.
3. **Type-normalize identity fields**: compare `session_id`, `nonce`, and `agent_id` as
   strings (or a stable hash) so `123` and `"123"` never become separate buckets.

## Re-running

```bash
pip install -r requirements.txt        # decimal + datetime only (stdlib)
python reproduce.py                    # runs all 4 reproductions
```

No external dependencies are required beyond the AgentShield source tree (`core/engine.py`).
