# RateLock — Centralized Rate Limiting Service

## Overview
RateLock is a standalone HTTP rate-limiting microservice designed to protect APIs from abuse such as brute-force attacks, scraping, and excessive client requests.  
Instead of embedding rate limiting into every backend service, applications can call RateLock before processing requests.

## Motivation
Traditional per-service middleware causes:
- duplicated logic
- inconsistent enforcement
- difficult scaling
- no centralized visibility

RateLock centralizes traffic control into a single service backed by Redis.

## Supported Algorithms
- Sliding Window
- Fixed Window
- Token Bucket

## Key Features
- Redis-backed persistence
- Atomic Lua scripts (race-condition safe)
- Concurrency-safe under multi-threaded load
- Cost-based requests
- Retry-After calculation
- HTTP API for service-to-service communication
- Works as external infrastructure service

## Architecture
Client → Application Service → RateLock → Redis → Decision → Application Response

## Demo
A protected authentication server is included (`auth_app.py`).  
It calls RateLock before validating login credentials and blocks brute-force attempts after 5 failed logins.

## How to Run

### 1. Start Redis
(ensure Redis is running on localhost:6379)

### 2. Install dependencies

Live API:
https://ratelock.onrender.com/docs

Live Demo:
https://ratelock-seven.vercel.app/