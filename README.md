<!-- PROFILE README TEMPLATE - cleaned & fixed -->

<h1 align="center">Hi 👋, I'm Swapnil Jadhav</h1>
<h3 align="center">💻 CSBS Student | 🧠 AI & Fullstack Developer | 🚀 Open Source Enthusiast</h3>

<p align="center">
  <!-- Typing SVG (stable demo host) -->
  <img src="https://readme-typing-svg.demolab.com?font=Fira%20Code&size=22&pause=1000&color=00C2FF&width=640&lines=Fullstack+Developer;AI+%26+ML+Enthusiast;Problem+Solver;Always+Learning+New+Tech!" alt="Typing SVG" />
</p>

---

### 🚀 About Me
- 🎓 3rd-year CSBS student at **KITS College of Engineering, Kolhapur**  
- 💡 I enjoy building AI-powered and fullstack web apps  
- 🌱 Currently learning **FastAPI**, **ML Model Deployment**, and **Docker**  
- ⚡ Fun fact: I love debugging more than coding 😅  
- 📫 Reach me at: **your.email@example.com**

---

### 🧰 Tech Stack

<p align="center">
  <!-- Skill icons - change list after `i=` to reflect your tools -->
  <img src="https://skillicons.dev/icons?i=python,java,cpp,react,flask,fastapi,nodejs,express,mongodb,html,css,js,tailwind,git,github,docker,vscode,linux" alt="skills" />
</p>

---

### 🧩 Featured Projects

| Project | Description | Tech |
|---------|-------------|------|
| [🛡️ Phishing Detection System](https://github.com/YOUR_USERNAME/phishing-detector) | Detects phishing websites using ML, WHOIS, and URL features | Python · FastAPI · React |
| [🤖 QuickAI](https://github.com/YOUR_USERNAME/quickai) | AI-based tools: text summarizer, meme & caption generator | React · Flask · OpenAI API |
| [🌐 Portfolio Website](https://github.com/YOUR_USERNAME/portfolio) | My personal responsive developer portfolio | React · Tailwind |

> Replace the three project links above with your actual repo links (or remove rows you don't have).

---

### 📊 GitHub Stats (update `YOUR_USERNAME`)

<p align="center">
  <!-- GitHub readme stats -->
  <img src="https://github-readme-stats.vercel.app/api?username=YOUR_USERNAME&show_icons=true&theme=tokyonight" alt="GitHub Stats" height="160"/>
  <!-- Contribution streak (use maintained demo host) -->
  <img src="https://streak-stats.demolab.com?user=YOUR_USERNAME&theme=tokyonight" alt="GitHub Streak" height="160"/>
</p>

<p align="center">
  <!-- Top languages -->
  <img src="https://github-readme-stats.vercel.app/api/top-langs/?username=YOUR_USERNAME&layout=compact&theme=tokyonight" alt="Top Languages" height="160"/>
</p>

---

### 🧠 Contribution Graph (last 31 days)
<p align="center">
  <img src="https://github-readme-activity-graph.vercel.app/graph?username=YOUR_USERNAME&theme=react-dark&hide_border=true" alt="activity graph" />
</p>

---

### 📫 Connect With Me
<p align="center">
  <a href="https://www.linkedin.com/in/YOUR_LINKEDIN/" target="_blank" rel="noopener noreferrer">
    <img src="https://img.shields.io/badge/LinkedIn-0A66C2?logo=linkedin&logoColor=white" alt="LinkedIn" />
  </a>
  <a href="mailto:your.email@example.com">
    <img src="https://img.shields.io/badge/Email-D14836?logo=gmail&logoColor=white" alt="Email" />
  </a>
  <a href="https://github.com/YOUR_USERNAME" target="_blank" rel="noopener noreferrer">
    <img src="https://img.shields.io/badge/GitHub-171515?logo=github&logoColor=white" alt="GitHub" />
  </a>
</p>

---

### 🧩 Fun Quote
> *"Code is like humor. When you have to explain it, it’s bad."* 😄

---

### ✨ Visitors
<p align="center">
  <!-- Profile view counter -->
  <img src="https://komarev.com/ghpvc/?username=YOUR_USERNAME&color=blueviolet&style=for-the-badge" alt="profile views" />
</p>

---

### ⚙️ Optional: Auto Update Workflow
Create `.github/workflows/update-readme.yml` if you want a simple periodic commit (optional):

```yaml
name: Update README

on:
  schedule:
    - cron: '0 0 * * *'  # every day at 00:00 UTC (change if needed)
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Append timestamp (idempotent)
        run: |
          if ! grep -q "<!-- updated:" README.md; then
            echo "<!-- updated: $(date -u) -->" >> README.md
          else
            # replace existing timestamp
            perl -0777 -pe 's/<!-- updated:.*?-->/<!-- updated: $(date -u) -->/s' -i README.md
          fi
      - name: Commit changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "actions@github.com"
          git add README.md
          git commit -m "chore: update README timestamp" || echo "no changes"
          git push
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
