## Day 6 — Production AI

Now move from prototype to engineering.

Study:

* API architecture
* authentication
* rate limiting
* caching
* queues
* retries
* observability
* logging
* tracing
* secrets
* privacy
* security
* prompt injection
* data exfiltration
* cost controls

Architecture exercise:

```text
                  +-------------+
                  |    User     |
                  +------+------+
                         ↓
                  +-------------+
                  |     API     |
                  +------+------+
                         ↓
               +-------------------+
               | AI Orchestration  |
               +--------+----------+
                        ↓
          +-------------+-------------+
          ↓             ↓             ↓
       Model          RAG           Tools
          ↓             ↓             ↓
          +-------------+-------------+
                        ↓
                     Evals
                        ↓
                   Observability
```

---