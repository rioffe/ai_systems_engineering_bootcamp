## Day 13 — Testing AI systems

Traditional testing:

```text
input → deterministic output
```

AI testing:

```text
input → distribution of possible outputs
```

Study:

* unit tests
* integration tests
* property-based tests
* regression tests
* evals
* adversarial tests
* fuzzing
* red teaming

Create:

### AI regression suite

Every change to the system automatically runs:

```text
100 test cases
       ↓
quality
latency
cost
safety
tool accuracy
       ↓
PASS / FAIL
```

---