## Day 12 — Performance and economics

This should be particularly interesting given your systems background.

Study:

* latency
* throughput
* batching
* caching
* concurrency
* context length
* model routing
* quantization
* inference cost
* GPU utilization

Build a simple cost model:

$C = N_{requests} \times (T_{input}P_{input}+T_{output}P_{output})$

Then optimize it.

For example:

**Model A**

* cheap
* slow
* high quality

**Model B**

* expensive
* fast
* high quality

Design a routing strategy.

---