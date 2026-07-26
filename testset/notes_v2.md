# Algorithms — sorting and Big-O

## What Big-O is actually saying
- Not "how many seconds". It is **how fast the work grows as the list gets bigger**.
- Constants are dropped: 2n and n are both O(n). Double the input, double the work.
- We mean the worst case unless we say otherwise.

## Vocabulary I keep mixing up
- **O(1)** — the same work whatever the size. Reading `list[0]`.
- **O(n)** — one pass over the list. Finding the largest number.
- **O(n²)** — a loop inside a loop. Bubble sort.

## Bubble sort — why it is O(n²)
Walk the list comparing neighbours, swapping any pair that is out of order. Each
pass drags the largest remaining item to the end, so you need n passes, and each
pass makes up to n comparisons. n passes × n comparisons = **n² comparisons**.

### Worked example — [5, 1, 4, 2]
| pass | list after | swaps |
|---|---|---|
| 1 | [1, 4, 2, 5] | 3 |
| 2 | [1, 2, 4, 5] | 1 |
| 3 | [1, 2, 4, 5] | 0 (sorted already, but it still checks) |

## Merge sort — why it is O(n log n)
Split the list in half, sort each half, then merge the two sorted halves.

- **Splitting** halves the list each time, so there are **log₂n levels**. 8 items = 3 levels.
- **Merging** at each level touches every item once, so each level costs **n**.
- Total = levels × cost per level = **n log n**.

### The bit that finally made it click
At 1,000 items bubble sort makes about 1,000,000 comparisons and merge sort about
10,000. That is not "a bit faster", it is 100 times, and the gap widens as n grows.
This is why the constants we dropped genuinely do not matter.

### What merge sort costs you
It needs a second array to merge into, so it uses O(n) extra memory. Bubble sort
sorts in place. That is the trade: merge sort buys time with space.
