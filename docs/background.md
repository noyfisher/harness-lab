# Background and external caveats

These are the external facts the protocol was designed around. They are context for the
results, not measurements from this study. Sources are linked.

## Noise on agentic evals

On SWE-bench Verified, single-run pass@1 estimates vary by 2.2 to 6.0 percentage points
depending on which run you pick, and run-to-run standard deviations exceed 1.5 points even at
temperature 0. Reported improvements of 2 to 3 points can be evaluation noise. This is why the
protocol uses repeats, paired comparisons, and a held-out split, and why the k=1 screens are
filters rather than tests. Source: Bjarnason, Silva, Monperrus, "On Randomness in Agentic Evals",
arXiv 2602.07150.

## Benchmark saturation and contamination

Frontier labs stopped headlining SWE-bench Verified in 2026 launch posts, and OpenAI published a
note titled "Why we no longer evaluate SWE-bench Verified". Nearly all Verified issues and their
fixes predate current model training cutoffs, so memorization cannot be excluded, and one
analysis found the solution present in the issue text for roughly a third of resolved
instances. This study therefore claims nothing about absolute capability. It uses the benchmark
as a fixed, comparable substrate to compare conditions that share the same model and the same
contamination exposure. Sources: https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/ ,
SWE-bench+ (arXiv 2410.06992).

## Environment coverage

Epoch AI publishes arm64 images for 420 of the 500 Verified instances; the gaps concentrate in
xarray (0 of 22), matplotlib (7 of 34), and scikit-learn (7 of 32). The subset is drawn from
gold-validated arm64-available instances only, which tilts it toward pure-Python repositories.
Source: https://epoch.ai/latest/swebench-docker , https://github.com/epoch-research/SWE-bench.

## Prior work on self-improving harnesses

The improver loop's archive-not-greedy design follows the Darwin Gödel Machine (arXiv
2505.22954); its reliance on rich trace feedback with few samples follows the GEPA line of work.
The accept rule and the screening asymmetry (k=1 filters against k=3 base classes) are this
study's own.
