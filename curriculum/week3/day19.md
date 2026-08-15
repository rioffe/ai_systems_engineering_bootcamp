## Day 19 — Multi-agent systems

Study when multiple agents actually make sense.

Patterns:

### Parallel

```text
       +→ Agent A
Task → +→ Agent B
       +→ Agent C
```

### Pipeline

```text
A → B → C → D
```

### Manager/worker

```text
       Manager
       /     \
   Worker   Worker
```

### Critic

```text
Developer → Critic → Developer
```

Then build one.

But critically ask:

> **Does adding agents actually improve the system?**

Agent multiplication is often cargo cult.

---