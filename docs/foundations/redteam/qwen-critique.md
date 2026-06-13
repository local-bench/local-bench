<!-- model: qwen3.7-max @ dashscope-intl.aliyuncs.com -->

### VERDICT
**REVISE.** The current direction mimics Artificial Analysis’s SaaS-analytics aesthetic for a dataset that is fundamentally a hardware-testing lab. **Highest-impact change:** Ditch the quality-vs-VRAM scatter plot hero and replace it with a deterministic "VRAM-Constrained Model Finder" utility. 

### Killer homepage lead
**The "Rig-Match Finder" (Utility over Analytics).** 
The current hero (a scatter plot with VRAM tier lines and Confidence Intervals) is an analyst’s chart, not a consumer’s tool. r/LocalLLaMA’s most frequent question is, *"What is the smartest model I can run on my 24GB 4090 at Q4?"* A scatter plot forces the user to visually interpolate dots, which is frustrating and imprecise. 

**The Fix:** Lead with a utility. Two dropdowns: `[My VRAM: 24GB]` and `[Target Quant: Q4_K_M]`. The output is a definitive, ranked list of models that fit, showing their quality score, the frontier-anchor ceiling (e.g., "82% of GPT-4o"), and tokens/s. 
*Why it beats the scatter:* It directly answers the user's primary intent in zero clicks. It survives the cold-start problem because a list of 5 models looks like a "curated lab report," whereas 5 dots on a massive scatter plot looks like an empty ghost town.

### Model-page hero
**Replace the "quant-degradation strip" with a "Quant Decision Matrix."**
The wedge (quant degradation) is brilliant, but a "strip" (presumably a sparkline or bar chart) is too abstract for the primary hero. When a user clicks on *Llama-3-70B*, they don't just want to see the degradation curve; they want to know **which quant to download**.

**The Fix:** A 4-to-5 column decision table (FP16, Q8, Q5, Q4, Q3). 
*   **Columns:** Quant, VRAM Req, Quality Score (with CI), Degradation from FP16, and Tokens/s.
*   **The Kicker:** Visually highlight the **"Pareto Sweet Spot"** (e.g., a green badge on Q5_K_M saying *"Best Tradeoff: 98.5% quality for 55% of the VRAM"*). 
Keep the detailed degradation chart *below* the fold for the nerds who want to inspect the math, but give the 90% of users an immediate, actionable recommendation.

### Biggest risk
**The "Empty Nightclub" Effect & Visual Vomit.**
Artificial Analysis looks good because they plot thousands of API data points, making their scatter plots look like dense, authoritative clouds. You are launching with a handful of runs. 
1. A dark-mode, AA-inspired scatter plot with 9 data points (4 anchors, 5 local) will look like a failed startup. 
2. Plotting **Confidence Intervals on a scatter plot** is a visual nightmare. Error bars on overlapping dots will turn your hero chart into illegible spaghetti, actively destroying the "credible to skeptics" mandate. Skeptics will think you are hiding bad data behind messy charts.

### Cut list
*   **The Quality-vs-VRAM Scatter Plot (as hero):** Move it to a secondary "Research/Explore" tab. It’s a great chart for when you have 100+ models, but fatal for day one.
*   **Hand-rolled SVG charts:** YAGNI. Building accessible, responsive, interactive charts with CI error bars from scratch will burn 30% of your frontend budget. Use ECharts, Recharts, or Plotly.
*   **DiagnosticsPanel on the Homepage:** Overbuilt for day one. Move anchor-spread/discrimination metrics to the Methodology page. Homepage real estate is too precious for meta-statistics.
*   **"Composite sorts" as the default table view:** Local users don't care about a single composite number as much as they care about specific axes (e.g., "I just need it for coding"). Default the table to a specific lane (e.g., Reasoning or Coding) and let them toggle.

### Concrete alternative IA

**1. HOME: The Rig-Match Finder & Lab Report**
*   **Lead:** The VRAM/Quant Finder utility (as described above).
*   **Secondary:** A dense, highly detailed "Lab Report" table. Instead of a sparse leaderboard, show every single run you have in a dense grid. Include hardware, runtime, and tokens/s prominently. Make it look like PassMark or Geekbench, not Stripe. 

**2. MODEL PAGE: The Quant Decision Matrix**
*   **Lead:** The Pareto Sweet-Spot table (FP16 down to Q3). 
*   **Secondary:** The Quant-Degradation chart (below the fold) showing the exact CI-bounded drop per axis. 
*   **Tertiary:** Per-axis radar/breakdown. Keep reasoning and answer-only lanes strictly separated here.

**3. COMPARE PAGE (The Bookmarkable Killer View)**
*   *This is what makes them come back weekly.* When a new model drops, users want to diff it against their current daily driver. 
*   **Lead:** A head-to-head **Model × Quant Diff tool**. (e.g., *Llama-3-70B Q4* vs *Mixtral-8x22B Q3*). 
*   Show a side-by-side axis breakdown, VRAM delta, and speed delta. This directly fuels Reddit arguments and gives users a reason to return every time a new weight is uploaded to HuggingFace.

**4. RUN DETAIL: The Provenance Receipt**
*   Keep as designed. Full hardware manifest, CLI command, transcript hashes. This is your trust anchor. Keep it raw and technical.