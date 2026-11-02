---
name: Mumbai Central demo constraints
description: Target restaurant and public-data rules for the Review Intelligence demo.
---

The owner-facing Review Intelligence demo targets Mumbai Central at 7505 VA-7, Falls Church, VA 22043. Public materials, including the demo video, should use synthetic review data and must not include real guest names or Yelp data.

**Why:** The user wants this demo tailored to the restaurant while protecting real guest and Yelp data in public materials.

**How to apply:** Keep demo examples fictional and clearly labeled as sample data. Do not present them as findings about Mumbai Central.

The product's main value should be turning rising review themes into manager-owned actions and checking later review patterns. Keep action suggestions as offline prompts, not claims about a proven cause, and describe post-action comparisons as trends rather than proof of impact.

**Why:** The user chose “AI that turns guest feedback into action” as the next feature and wants an accurate, credible restaurant demo.

**How to apply:** Keep manager review in the loop, record the action and status, and wait for enough newer reviews before showing a follow-up comparison.

Do not use Ollama for this app. Use the free Offline engine for verification.

**Why:** The user said, “Dont use Ollama its very slow.”

**How to apply:** Do not start Ollama or run review batches through it unless the user explicitly changes this instruction.

The user approved a lightweight custom, local rule-based analyzer as the replacement for Ollama. Describe it as rules, not a self-trained language model, and do not claim accuracy from unlabeled review data.

**Why:** The user asked to self-build a replacement because Ollama is too slow; the approved scope keeps analysis free and suitable for their laptop.

**How to apply:** Keep explanations and manager review visible. Speed measurements are not an accuracy evaluation, and Replit speed is not a laptop performance guarantee.
