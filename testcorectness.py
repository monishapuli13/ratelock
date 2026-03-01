"""
Correctness Tests
-----------------
These tests don't use HTTP. They call the algorithm functions directly.
Fast, deterministic, and prove the math is right.

Run: python tests/test_correctness.py
"""

import sys
import time
import threading
sys.path.insert(0, '.')

from store import store
import fixed_window
import slidingwindow as sliding_window
import token_bucket
# ─── Test runner ─────────────────────────────────────────────────

passed = 0
failed = 0

def test(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
        failed += 1

def section(name: str):
    print(f"\n{'─'*50}")
    print(f"  {name}")
    print(f"{'─'*50}")

def reset():
    store.flush()


# ─── Fixed Window Tests ──────────────────────────────────────────

section("Fixed Window — Basic")
reset()

# Should allow up to limit
results = [fixed_window.check("user1:api", limit=5, window_seconds=60) for _ in range(5)]
test("Allows exactly 5 requests", all(r["allowed"] for r in results))
test("Count reaches 5", results[-1]["count"] == 5)
test("Remaining reaches 0", results[-1]["remaining"] == 0)

# 6th should be rejected
r6 = fixed_window.check("user1:api", limit=5, window_seconds=60)
test("Rejects 6th request", not r6["allowed"])
test("retry_after is set", r6["retry_after"] is not None and r6["retry_after"] > 0)
test("remaining is 0 when rejected", r6["remaining"] == 0)

section("Fixed Window — Cost")
reset()

# Cost=3 should use 3 tokens per request
r1 = fixed_window.check("user2:api", limit=10, window_seconds=60, cost=3)
test("Cost=3 first request allowed", r1["allowed"])
test("Cost=3 remaining=7", r1["remaining"] == 7)

r2 = fixed_window.check("user2:api", limit=10, window_seconds=60, cost=3)
test("Cost=3 second request allowed", r2["allowed"])
test("Cost=3 remaining=4", r2["remaining"] == 4)

r3 = fixed_window.check("user2:api", limit=10, window_seconds=60, cost=3)
test("Cost=3 third request allowed (uses 9/10)", r3["allowed"])

r4 = fixed_window.check("user2:api", limit=10, window_seconds=60, cost=3)
test("Cost=3 fourth request rejected (would need 12/10)", not r4["allowed"])

section("Fixed Window — Different users don't interfere")
reset()

for _ in range(5):
    fixed_window.check("userA:api", limit=5, window_seconds=60)

# userA is maxed out — userB should be unaffected
rB = fixed_window.check("userB:api", limit=5, window_seconds=60)
test("UserB unaffected by UserA's limit", rB["allowed"])
test("UserB remaining=4", rB["remaining"] == 4)


# ─── Sliding Window Tests ────────────────────────────────────────

section("Sliding Window — Basic")
reset()

results = [sliding_window.check("user3:email", limit=10, window_seconds=60) for _ in range(10)]
test("Allows exactly 10 requests", all(r["allowed"] for r in results))

r11 = sliding_window.check("user3:email", limit=10, window_seconds=60)
test("Rejects 11th request", not r11["allowed"])

section("Sliding Window — Debug fields present")
reset()
r = sliding_window.check("user4:api", limit=100, window_seconds=60)
test("Debug field present", "debug" in r)
test("Debug has current_count", "current_count" in r["debug"])
test("Debug has prev_weight", "prev_weight" in r["debug"])
test("prev_weight between 0 and 1", 0 <= r["debug"]["prev_weight"] <= 1)

section("Sliding Window — No previous window = full limit available")
reset()
# Fresh start — no previous window data
r = sliding_window.check("user5:api", limit=100, window_seconds=60)
test("Full limit available on first request", r["remaining"] == 99)
test("prev_count is 0", r["debug"]["prev_count"] == 0)


# ─── Token Bucket Tests ──────────────────────────────────────────

section("Token Bucket — Basic")
reset()

# Capacity=5, refill=1/sec
results = [token_bucket.check("user6:api", capacity=5, refill_rate=1.0) for _ in range(5)]
test("Allows 5 burst requests", all(r["allowed"] for r in results))
test("Tokens reach 0", results[-1]["tokens_remaining"] == 0.0)

r6 = token_bucket.check("user6:api", capacity=5, refill_rate=1.0)
test("Rejects when empty", not r6["allowed"])
test("retry_after set when empty", r6["retry_after"] is not None)

section("Token Bucket — Refill over time")
reset()

# Drain the bucket
for _ in range(3):
    token_bucket.check("user7:api", capacity=3, refill_rate=10.0)

r = token_bucket.check("user7:api", capacity=3, refill_rate=10.0)
test("Bucket drained", not r["allowed"])

# Wait for refill (10 tokens/sec → 0.15s = 1.5 tokens)
time.sleep(0.2)

r_after = token_bucket.check("user7:api", capacity=3, refill_rate=10.0)
test("Allowed after refill wait", r_after["allowed"],
     f"tokens_remaining={r_after.get('tokens_remaining')}")

section("Token Bucket — Cost > 1")
reset()

r1 = token_bucket.check("user8:api", capacity=10, refill_rate=1.0, cost=4)
test("Cost=4 allowed from full bucket", r1["allowed"])
test("6 tokens remaining after cost=4", r1["tokens_remaining"] == 6.0)

r2 = token_bucket.check("user8:api", capacity=10, refill_rate=1.0, cost=4)
test("Cost=4 second request allowed (6 tokens)", r2["allowed"])
test("2 tokens remaining", r2["tokens_remaining"] == 2.0)

r3 = token_bucket.check("user8:api", capacity=10, refill_rate=1.0, cost=4)
test("Cost=4 third request rejected (only 2 tokens)", not r3["allowed"])


# ─── Concurrency Test ────────────────────────────────────────────

section("Concurrency — Threading stress test (THE IMPORTANT ONE)")
reset()

LIMIT = 100
THREADS = 150
results_list = []
lock = threading.Lock()

def fire_request():
    result = sliding_window.check(
        key="concurrent_user:api",
        limit=LIMIT,
        window_seconds=60,
    )
    with lock:
        results_list.append(result["allowed"])

threads = [threading.Thread(target=fire_request) for _ in range(THREADS)]

# Fire all threads simultaneously
for t in threads:
    t.start()
for t in threads:
    t.join()

allowed_count = sum(1 for r in results_list if r)
rejected_count = sum(1 for r in results_list if not r)

test(
    f"Never exceeds limit ({allowed_count} allowed, {rejected_count} rejected)",
    allowed_count <= LIMIT,
    f"allowed={allowed_count} but limit={LIMIT}"
)
test("Total responses = total threads", len(results_list) == THREADS)
test(
    "Rejected count is correct",
    rejected_count >= THREADS - LIMIT,
    f"expected at least {THREADS - LIMIT} rejected, got {rejected_count}"
)

# Run concurrency test 5 more times to prove it's consistent
print("\n  Running 5 more concurrency rounds...")
all_passed = True
for round_num in range(5):
    store.flush()
    results_list.clear()
    threads = [threading.Thread(target=fire_request) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    allowed = sum(1 for r in results_list if r)
    if allowed > LIMIT:
        all_passed = False
        print(f"  ❌ Round {round_num + 1}: allowed={allowed} exceeded limit={LIMIT}")
    else:
        print(f"  ✅ Round {round_num + 1}: allowed={allowed}/{LIMIT}")

test("All 5 rounds stayed within limit", all_passed)


# ─── Results ─────────────────────────────────────────────────────

print(f"\n{'═'*50}")
print(f"  Results: {passed} passed, {failed} failed")
print(f"{'═'*50}\n")

if failed > 0:
    print("  ❌ Some tests failed. Fix before moving to Phase 2.")
    sys.exit(1)
else:
    print("  ✅ All tests passed. Algorithms are correct.")
    print("  Ready for Phase 2 — swap MemoryStore for Redis.\n")
    sys.exit(0)