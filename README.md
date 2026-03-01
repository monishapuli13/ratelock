RateLock — Centralized Rate Limiting Service

Problem
APIs are vulnerable to brute force and abuse. Per-service rate limiting causes inconsistent enforcement in distributed systems.

Solution
A standalone rate-limiting microservice supporting sliding window, fixed window, and token bucket algorithms backed by Redis with atomic Lua execution.

Key Features
• Thread-safe concurrency guarantees
• Multiple algorithms
• Cost-based requests
• Retry-After support
• HTTP API
• Redis persistence
• Service-to-service protection demo

Architecture
Auth Service → RateLock → Redis