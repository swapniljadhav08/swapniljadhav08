# Setup, Regeneration, and Publishing Guide

This guide details how to publish your developer profile, configure the **contribution grid snake animation**, and manage third-party analytics widgets.

---

## 📂 Repository Contents

| File / Folder | Purpose |
| :--- | :--- |
| `README.md` | Profile dashboard featuring your banner, snake animation, statistics, tech stack, and projects |
| `.github/workflows/snake.yml` | GitHub Actions workflow to generate daily contribution grid snake SVGs to branch `output` |
| `profile.svg` | Custom animated particle banner (14,000 vector particles, ~180 KB) |
| `generate_portrait.py` | Deterministic photo-to-particle generator script |
| `requirements.txt` | Python dependencies for local portrait regeneration |
| `assets/` | Original photo source and visual reference previews |

---

## 🚀 Publishing to GitHub

Your GitHub profile README lives in a special repository named identically to your username: [`swapniljadhav08/swapniljadhav08`](https://github.com/swapniljadhav08/swapniljadhav08).

### 1. Initialize & Push to `main`

Run the following commands in this directory:

```bash
git init
git branch -M main
git add .
git commit -m "feat: complete developer dashboard with animated snake and analytics"
git remote add origin https://github.com/swapniljadhav08/swapniljadhav08.git
git push -u origin main
```

*(If the remote repository already contains an initial commit or default README, run `git pull origin main --allow-unrelated-histories` before pushing).*

---

## 🐍 Activating the Animated Contribution Snake

The contribution snake runs on GitHub Actions and automatically saves the light and dark SVG animations to an orphan branch named `output`.

### Step 1: Enable GitHub Actions Workflow Permissions

1. Go to your repository on GitHub: `https://github.com/swapniljadhav08/swapniljadhav08`.
2. Click **Settings** (top navigation tab).
3. In the left sidebar, expand **Actions** → click **General**.
4. Scroll down to **Workflow permissions**.
5. Select **Read and write permissions** (this allows the action to push generated SVGs to the `output` branch).
6. Check the box **Allow GitHub Actions to create and approve pull requests**.
7. Click **Save**.

### Step 2: Trigger the Workflow Manually

1. Click on the **Actions** tab in your repository.
2. In the left sidebar, click **github-snake**.
3. Click the **Run workflow** dropdown button on the right.
4. Keep the branch as `main` and click the green **Run workflow** button.
5. Wait ~30–45 seconds for the workflow run to turn green (completed).

### Step 3: Verify the Generated Files

Once the workflow succeeds:
1. An orphan branch named **`output`** is automatically created.
2. The following files will now exist at the root of the `output` branch:
   - `github-contribution-grid-snake.svg`
   - `github-contribution-grid-snake-dark.svg`
3. Your profile `README.md` will immediately render the snake eating your contribution squares in both light and dark themes.

> **Scheduled Automation:** The workflow is set to run automatically every night at 00:00 UTC (`cron: "0 0 * * *"`), keeping your animation up-to-date with your latest commits.

---

## 📊 Analytics & External Services

| Service | Endpoint | Notes |
| :--- | :--- | :--- |
| **Platane/snk** | GitHub Actions (`.github/workflows/snake.yml`) | Runs directly in your repo; zero dependency on third-party API servers |
| **GitHub Readme Stats** | `github-readme-stats.vercel.app` | Displays public repository stars, commits, PRs, and top languages |
| **GitHub Streak Stats** | `streak-stats.demolab.com` | Tracks active streak days, longest streak, and total contributions |
| **Profile Summary Cards** | `github-profile-summary-cards.vercel.app` | Renders a 12-month contribution waveform curve and profile summary |

> **Private Repositories:** By default, third-party statistics cards only count activity on **public repositories**. If you want private contributions included in GitHub Readme Stats, you can deploy your own instance of `github-readme-stats` on Vercel with a Personal Access Token (`PAT_1`) having `repo` scope.
>
> **GitHub Camo Image Cache:** GitHub caches external images via its `camo.githubusercontent.com` proxy. After running your snake workflow or pushing new changes, images may take 2–5 minutes to refresh.
