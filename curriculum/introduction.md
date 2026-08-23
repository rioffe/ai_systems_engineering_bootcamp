# Introduction

To my wife, Ellen, for her patience and support throughout this project.

Software engineering is entering a fundamental transition.

For decades, the dominant model of software development was relatively straightforward: understand the requirements, design the architecture, write the code, test it, and deploy it. AI does not eliminate this discipline, but it changes where much of the work happens. Large language models can now write substantial amounts of code, reason over repositories, operate development tools, generate tests, diagnose failures, and increasingly work through entire software-development loops.

The question is therefore no longer simply **how to write software**. It is increasingly **how to engineer systems in which humans and AI work together to produce reliable software**.

This book, ***AI Systems Engineering: A Practical Bootcamp***, is an intensive **30-working-day deep dive for professional software engineers**. That is an ambitious schedule, and it is not intended to make a reader an expert in every aspect of AI in one month. Rather, it is designed to give an experienced engineer a coherent mental model, hands-on practice, and a solid foundation from which to keep learning.

The curriculum draws in part on Andrew Ng's *AI Engineering Skills Map*, which identifies four capabilities becoming central to modern software development:

1. **Building and deploying AI applications**
2. **Software engineering fundamentals**
3. **Using coding agents**
4. **Shaping the build**

These four areas provide the organizing principles for this book, but the goal here is to go beyond a skills checklist and turn them into a practical engineering curriculum.

The book therefore progresses from **AI application development**, through **architecture, reliability, security, performance, and testing**, into **coding agents, specification engineering, agentic development, and multi-agent systems**, and finally into **product thinking and shaping what gets built**.

The central premise is:

> **AI makes implementation cheaper. It makes engineering judgment more valuable.**

As coding agents become increasingly capable of implementing well-defined specifications, the engineer's role moves upstream. Engineers must understand the problem, shape the specification, design the system, provide the right context, establish verification mechanisms, evaluate the result, and decide when to intervene and when to let the agent proceed autonomously.

That requires a combination of skills that traditionally lived in separate disciplines: software architecture, distributed systems, machine learning, evaluation, security, product thinking, and now **agent supervision**.

## How This Book Was Made

There is a certain symmetry in writing a book about AI-assisted software engineering using AI-assisted engineering itself.

**All of the substantive content in this book was initially written by ChatGPT.** I then thoroughly reviewed and edited the material as an experienced software engineer.

The final editing pass was performed locally using a **Qwen3.8:27B-MLX model**, served through **Ollama** and operated by the **Pi coding agent**.

This was significant for me personally: it was the **first time I had used a local model productively as part of a real engineering workflow**, rather than simply experimenting with local inference as a technical exercise. It was a small but meaningful milestone in my own transition toward the kind of AI-assisted engineering workflow this book describes.

And there is one more detail worth recording.

This book was written on a **16-inch MacBook Pro with an M5 Max chip** — a retirement gift to myself, purchased with a little help from Apple. I worked on a preproduction version of this machine while serving as a Systems Performance Architect at Apple, and I loved every minute of it. It became both the writing environment and the local AI workstation on which the final editing workflow ran. In that sense, the computer, the models, and the agents were not abstract technologies being discussed from a distance — they were the actual tools used to produce this book.

There is, therefore, a certain circularity to the project:

> **A book about the emerging AI engineering workflow, written using the emerging AI engineering workflow, on the hardware that made running a capable local model practical.**

This book is not merely **about** the transition it describes.

**It is also a small experiment in living through it.**

The objective, after thirty working days, is not mastery. It is something more useful: **a working foundation for becoming an AI systems engineer** — someone capable of building AI-powered systems, reasoning about their behavior, directing AI coding agents, evaluating what they produce, and making sound engineering and product decisions in a rapidly changing technical environment.

— *Robert Ioffe*

  Portland, Oregon

  August 23, 2026
