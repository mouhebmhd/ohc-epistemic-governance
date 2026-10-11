# Reddit health-community rules pipeline

## Setup
#### For data colelction 
```bash
pip install -r requirements.txt
# create a "script" app at https://www.reddit.com/prefs/apps, then fill config.yaml (or set env vars)
python collect_reddit.py templates          # codebook, data dictionary, empty annotation files
python collect_reddit.py collect            # rules, subreddits, posts (add --comments for comments)
python collect_reddit.py collect --resume   # continue an interrupted run
```
#### For data visualization 
```bash
python -m pip install pandas matplotlib
python -m pip install tabulate
python analyze_reddit_communities.py

```
## Commands
| command | purpose |
|---|---|
| `collect` | Datasets 1–5 raw (`data/raw/`) then runs `derive` (skip with `--no-derive`) |
| `derive` | Derived fields → `posts_coded.csv`, `algorithmic_interaction.csv`, `coding_validation.csv` template |
| `kappa` | Cohen's kappa between coder_A / coder_B in `coding_validation.csv` |
| `sample-experiential` | Purposive sample for Dataset 8 from LHL-coded communities |
| `snapshot` | Hot-listing snapshot (run repeatedly) → enables `visibility_duration_hours` |
| `discover` | Candidate multilingual subreddits via search → `data/metadata/candidate_subreddits.csv` |
| `templates` | Writes codebook.json, data_dictionary.md, sampling_frame.csv, epistemic_communities.csv |

Multilingual communities: put them in the seed file with `sample_group=multilingual`; they route to
`multilingual_rules.csv` / `multilingual_posts.csv` with the extra translation columns.

## Optional inputs you create
- `data/metadata/community_codes.csv` (`subreddit_name,lhl_or_hhl`) – community-level LHL/HHL assignment per your codebook.
- `data/metadata/rule_violation_labels.csv` (`post_id,rule_violation,rule_violation_type`) – manual labels used for `amplification_flag`.
