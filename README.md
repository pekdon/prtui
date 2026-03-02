# prtui

A terminal UI for managing your GitHub pull request inbox, built with [Textual](https://textual.textualize.io/).

Shows your PRs, PRs you've reviewed, and PRs requested via team assignment. Displays comments, reviews, commits, and CI status inline.

## Install

1. Create a Python venv and source it:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

NOTE: the prtui wrapper script is assuming the venv name .venv, update it
if you want to use something else

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `config` file in the project root:

```
username:<github-username>
team:<org>/<team-slug>
token:<github-personal-access-token>
repos:<owner/repo>,<owner/repo2>
jenkins-user:<jenkins-bot-username>
```

4. Add to PATH
Assuming zsh
```
echo 'export PATH="$PATH:/Users/jonathan/scripts/prtui"' >> ~/.zshrc
```

## Usage

```bash
cd py && python prtui.py
```

## Data

PR data is stored in a SQLite database at `/tmp/prtui.db`. Delete it to force a full re-fetch.
