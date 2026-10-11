# Reddit Health Communities: Exploratory Report

- Input file: `reddit_health_communities.json`
- Communities: **95**
- Languages: **5**
- Extracted rule objects: **925**

## 1. Dataset-level summary

- Communities missing a subreddit name: 0
- Communities with unknown language: 0
- Communities with no valid rules: 3
- Rules with empty titles: 18
- Rules with empty descriptions: 151
- Rules flagged for possible navigation/footer noise: 74

## 2. Language-level summary

| language   |   n_communities |   n_rules |   mean_rules_per_community |   median_rules_per_community |   min_rules |   max_rules |   communities_without_rules |   communities_with_duplicates |   empty_descriptions |   duplicate_rules |   total_links |
|:-----------|----------------:|----------:|---------------------------:|-----------------------------:|------------:|------------:|----------------------------:|------------------------------:|---------------------:|------------------:|--------------:|
| English    |              49 |       590 |                   12.0408  |                         12   |           1 |          29 |                           0 |                             0 |                   81 |                 0 |           970 |
| Arabic     |              12 |       118 |                    9.83333 |                          9.5 |           2 |          20 |                           0 |                             0 |                   17 |                 0 |           140 |
| French     |              12 |        85 |                    7.08333 |                          2   |           0 |          23 |                           1 |                             0 |                   22 |                 0 |           174 |
| Spanish    |              12 |        31 |                    2.58333 |                          2   |           0 |          10 |                           2 |                             0 |                   12 |                 0 |            85 |
| Hindi      |              10 |       101 |                   10.1     |                          6.5 |           2 |          27 |                           0 |                             0 |                   19 |                 0 |           175 |

## 3. Extraction status

| language   | status         |   n_communities |
|:-----------|:---------------|----------------:|
| English    | ok             |              49 |
| Arabic     | ok             |              12 |
| French     | ok             |              11 |
| Hindi      | ok             |              10 |
| Spanish    | ok             |              10 |
| Spanish    | no_rules_found |               2 |
| French     | no_rules_found |               1 |

## 4. Data-quality notes

- Communities with potential data issues: 69
- Duplicate subreddit-name records: 0
- Repeated rule-text groups: 9

## 5. Interpretation cautions

- An extracted rule is not necessarily a genuine moderation rule.
- Empty descriptions may be legitimate, for example, title-only rules.
- Repeated rules can reflect common moderation practices rather than errors.
- Navigation/footer flags are heuristics and require manual validation.
- Community counts and rule counts should be interpreted alongside extraction status.

## 6. Generated visualizations

- `01_communities_per_language.png`
- `02_rules_per_language.png`
- `03_rule_count_distribution.png`
- `04_mean_rules_per_community.png`
- `05_top_30_communities.png`
- `06_empty_descriptions_by_language.png`
- `07_possible_noise_by_language.png`
- `08_status_by_language.png`