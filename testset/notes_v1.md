# Algorithms — sorting and Big-O

## What Big-O is actually saying
- Not "how many seconds". It is **how fast the work grows as the list gets bigger**.
- Constants are dropped: 2n and n are both O(n). Double the input, double the work.
- We mean the worst case unless we say otherwise.

## Vocabulary I keep mixing up
- **O(1)** — the same work whatever the size. Reading `list[0]`.
- **O(n)** — one pass over the list. Finding the largest number.
- **O(n²)** — a loop inside a loop. Bubble sort.
