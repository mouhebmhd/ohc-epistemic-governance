# OHC Epistemic Governance

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.XXXXXXX-blue)](https://doi.org/10.5281/zenodo.XXXXXXX)

**Data collection and analysis pipeline for studying algorithmic and written epistemic governance in online health communities (OHCs).**

This repository contains the code, data schemas, and analysis notebooks for the manuscript:

> Mehdoui, M. et al. (2026). *Algorithmic and Written Governance in Online Health Forums: Epistemic Asymmetry Beyond Rules.* International Journal on Digital Libraries. [under review]

The work extends the ISKO 2026 paper:

> Mehdoui, M. (2026). *Between Censorship and Curation: The Legitimacy Dilemma of Knowledge Organization in Online Health Forums.* Proceedings of the International ISKO Conference 2026. ISSN 0938-5495.

---

## Table of Contents

- [Overview](#overview)
- [Key Concepts](#key-concepts)
- [Repository Structure](#repository-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [1. Data Collection](#1-data-collection)
  - [2. Preprocessing and Coding](#2-preprocessing-and-coding)
  - [3. Algorithmic Analysis](#3-algorithmic-analysis)
  - [4. Statistical Analysis](#4-statistical-analysis)
  - [5. Multilingual Comparison](#5-multilingual-comparison)
- [Data Dictionary](#data-dictionary)
- [Ethical and Legal Notes](#ethical-and-legal-notes)
- [Reproducibility](#reproducibility)
- [Citation](#citation)
- [License](#license)
- [Contact](#contact)

---

## Overview

Online health communities (OHCs) are vital for peer support, yet their governance remains underexamined. Our previous work analysed **738 rule statements** across **117 Reddit health communities** and found a systematic asymmetry: high-health-literacy (HHL) contributions are legitimised through credentialing and infrastructure, while low-health-literacy (LHL) narratives are contained through prohibitive rules and channeling mechanisms. We termed this **Governance-Induced Epistemic Silencing**.

This repository extends that work by:

1. **Modelling algorithmic governance** — Reddit's upvote/downvote algorithm as a second, invisible layer of Knowledge Organization.
2. **Reframing LHL** as a lack of *institutional biomedical fluency* rather than a deficit in health knowledge.
3. **Introducing experiential literacy** as a legitimate epistemic competency.
4. **Examining epistemic community formation** — how patient-led collectives generate, validate, and circulate knowledge outside formal biomedical institutions.
5. **Addressing methodological circularity** through blind coding, inter-rater reliability, and external validation.

The pipeline supports:

- Collection of **written rules**, **wikis**, **pinned posts**, and **algorithmic metrics** from Reddit.
- **Multilingual sampling** (English, Spanish, French, Hindi, Arabic).
- **Transparent measurement** of the Legitimacy Asymmetry Ratio (LAR).
- **Cluster analysis** with rigorous justification (silhouette, gap statistic, bootstrap stability).
- **Qualitative coding** of experiential literacy and epistemic community formation.

---

## Key Concepts

| Concept | Definition |
|---|---|
| **Epistemic Governance** | The rules, infrastructure, and algorithmic affordances that determine what counts as legitimate knowledge in a community. |
| **Dual-Layer Governance** | Written rules (Layer 1) + algorithmic affordances (Layer 2). |
| **Experiential Literacy** | High competency in embodied, narrative, and community-based knowledge. |
| **Epistemic Community** | A patient-led collective that generates, validates, and circulates knowledge outside formal biomedical institutions. |
| **Legitimacy Dilemma** | The tension between validating user narratives and managing informational risk. |
| **KO-Equity Spectrum** | A continuum from Pre-emptive Censorship to Participatory Curation. |
| **Epistemic Risk-Calibration** | Governance posture as a function of perceived epistemic risk. |
| **Governance-Induced Epistemic Silencing** | The systematic containment of LHL contributions and credentialing of HHL contributions. |
| **Infodemic Equity Gap** | Patterned disparities in exposure to and resilience against health misinformation across languages. |

---

## Repository Structure
