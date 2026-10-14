#!/usr/bin/env python3
"""Build configuration.csv from a Reddit community metadata dump.

Usage:
    python build_configuration.py [input.json] [configuration.csv] [logs/build_configuration.log]
"""
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

INPUT = sys.argv[1] if len(sys.argv) > 1 else "reddit_health_communities_metadata.json"
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else "configuration.csv"
LOGFILE = sys.argv[3] if len(sys.argv) > 3 else "logs/build_configuration.log"
TARGET_LANGS = {
    # Existing core languages
    "en",  # English
    "fr",  # French: france, Quebec, annuaire, AskMec, askmeuf
    "es",  # Spanish: espanol, Espana, ColombiaReddit, mexico, Chile
    "pt",  # Portuguese: brasil, brasilivre, Conversas, brdev
    "ar",  # Arabic: Arabs, Egypt, saudiarabia, learn_arabic
    "hi",  # Hindi: India-related communities; validate actual language

    # Western and Northern Europe
    "de",  # German: de, ich_iel, finanzen
    "nl",  # Dutch: nederlands, dutch, thenetherlands
    "it",  # Italian: italy, italia, ADHDitalia
    "fi",  # Finnish: suomi, arkisuomi
    "da",  # Danish: danish, dankmark
    "sv",  # Swedish: Svenska, MentalHealthSweden, BipolarSverige
    "no",  # Norwegian: norsk
    "is",  # Icelandic; country-specific communities may use it

    # Central, Eastern and Southeastern Europe
    "ru",  # Russian: russian, pikabu
    "uk",  # Ukrainian: ukraina, reddit_ukr, Ukraine_ua
    "pl",  # Polish: polska
    "cs",  # Czech; possible regional language
    "sk",  # Slovak; possible regional language
    "sl",  # Slovenian: slovenia
    "hr",  # Croatian: croatia
    "sr",  # Serbian: serbia
    "bg",  # Bulgarian: bulgaria
    "ro",  # Romanian: romanian, EchilibruMentalRO
    "hu",  # Hungarian: hungary
    "el",  # Greek: ellada
    "hy",  # Armenian: Armenia, hayeren
    "lv",  # Latvian: latvia
    "lt",  # Lithuanian: lithuania
    "ga",  # Irish: mina_irl is not sufficient evidence by itself

    # Middle East and Central Asia
    "fa",  # Persian: iran
    "he",  # Hebrew: hebrew, Israel
    "tr",  # Turkish: Turkey, turkish
    "az",  # Azerbaijani; not directly confirmed by a community name
    "ku",  # Kurdish; not directly confirmed by a community name

    # South Asia
    "bn",  # Bengali: Bangladesh-related communities
    "ur",  # Urdu; possible in Pakistan-related communities
    "ta",  # Tamil: tamil
    "te",  # Telugu: telugu
    "ml",  # Malayalam: malayalam
    "pa",  # Punjabi; possible in India-related communities
    "ne",  # Nepali; not directly confirmed

    # East Asia
    "ja",  # Japanese: LearnJapanese, japanese, newsokur
    "zh",  # Chinese: ChineseLanguage, Taiwan-related communities
    "yue", # Cantonese; three-letter code, depending on detector
    "ko",  # Korean: Korean

    # Southeast Asia
    "vi",  # Vietnamese: Vietnamese
    "th",  # Thai: thai
    "id",  # Indonesian: indonesian
    "ms",  # Malay: bahasamelayu
    "tl",  # Tagalog: Tagalog
    "fil", # Filipino; three-letter code, depending on detector

    # Africa
    "am",  # Amharic: amharic
    "so",  # Somali: LearnSomali
    "af",  # Afrikaans: afrikaans
    "sw",  # Swahili; not directly confirmed by a community name
}
GOVERNANCE_FIELDS = [
    # Access
    "subreddit_type", "restrict_posting", "restrict_commenting",
    "disable_contributor_requests", "accept_followers", "allow_discovery", "quarantine",
    # Content
    "allow_images", "allow_videos", "allow_galleries", "allow_videogifs",
    "allow_polls", "allow_predictions", "allow_talks", "submission_type", "over18",
    "all_original_content",
    # Classification
    "link_flair_enabled", "link_flair_position", "user_flair_enabled_in_sr",
    "can_assign_link_flair", "can_assign_user_flair", "original_content_tag_enabled",
    "spoilers_enabled",
    # Knowledge
    "wiki_enabled", "submit_text", "description", "public_description",
    # Visibility
    "comment_score_hide_mins", "collapse_deleted_comments", "suggested_comment_sort",
    "hide_ads", "show_media", "show_media_preview",
    # Scale
    "subscribers", "created_utc",
]

COLUMNS = (
    ["subreddit_name", "language", "disease_category", "sample_group"]
    + GOVERNANCE_FIELDS
    + ["community_age_days"]
)

# Order matters: first matching category wins.
KEYWORDS = [
    (
        "chronic",
        [
            # Chronic illness and persistent symptoms
            "chronic", "chron", "longcovid", "long_covid", "long-haul",
            "longhauler", "longhaulers", "longhauler", "postviral",
            "post-viral", "postviral", "persistent", "fatigue",
            "cfs", "me_cfs", "myalgic", "encephalomyelitis",
            "fibro", "fibromyalgia", "lupus", "pots", "dysautonomia",
            "eds", "ehlers", "hypermobile", "hypermobility",
            "mecfs", "pem", "mcas", "mitochondrial", "mitochondria",
            "gulfwarillness", "gulf_war_illness",

            # Pain, neurological, and musculoskeletal conditions
            "pain", "chronicpain", "migraine", "headache",
            "neuropath", "neuralgia", "arthritis", "arthrit",
            "osteoarthritis", "rheumatoid", "rheumat",
            "spondylitis", "scolio", "sclerosis", "multiple_sclerosis",
            "parkinson", "huntington", "epilepsy", "seizure",
            "neurologicaldisease", "neurological", "neurolog",
            "brainfog", "brain_fog", "vertigo", "tinnitus",
            "spine", "backpain", "sciatica", "discdegeneration",
            "disc_disease", "jointpain", "joint", "osteoporosis",
            "fibrom", "muscular", "musclepain",

            # Autoimmune and inflammatory diseases
            "autoimmune", "autoimmun", "immunedisease",
            "immunology", "immunocompromised", "immunodeficiency",
            "hashimoto", "gravesdisease", "graves_disease",
            "thyroid", "hypothyroid", "hyperthyroid",
            "celiac", "coeliac", "crohn", "colitis",
            "ulcerativecolitis", "ulcerative_colitis", "ibd",
            "ibs", "sibo", "guthealth", "gut_health",
            "inflammatory", "psoriasis", "psoriatic",
            "sjogren", "scleroderma", "vasculitis", "sarcoidosis",
            "ankylosing", "behcet", "addison", "adrenal",
            "endometriosis", "endo", "adenomyosis", "pcos",
            "polycystic", "premenstrual", "pmdd", "menopause",
            "pelvicpain", "pelvic_pain", "vulvodynia",
            "interstitialcystitis", "interstitial_cystitis",

            # Metabolic, cardiovascular, respiratory conditions
            "diabetes", "diabetic", "diabet", "t1d", "t2d",
            "type1diabetes", "type2diabetes", "prediabetes",
            "insulinresistance", "insulin_resistance", "glucose",
            "hypoglycemia", "hyperglycemia", "neuropathy",
            "obesity", "metabolic", "lipedema", "lymphedema",
            "hypertension", "hypotension", "dysautonomia",
            "pots", "tachycardia", "arrhythmia", "cardiomyopathy",
            "heartfailure", "heart_failure", "heartdisease",
            "heart_disease", "cardiovascular", "cardio",
            "asthma", "copd", "emphysema", "bronchiectasis",
            "pulmonaryfibrosis", "pulmonary_fibrosis",
            "sleepapnea", "sleep_apnea", "narcolepsy",
            "kidneydisease", "kidney_disease", "ckd",
            "renal", "dialysis", "liverdisease", "liver_disease",
            "cirrhosis", "hepatitis", "fattyliver", "fatty_liver",

            # Cancer and rare diseases
            "cancer", "cancers", "oncology", "oncolog",
            "tumor", "tumour", "carcinoma", "lymphoma",
            "leukemia", "leukaemia", "melanoma", "sarcoma",
            "myeloma", "metastatic", "metastasis", "chemotherapy",
            "radiotherapy", "immunotherapy", "oncological",
            "raredisease", "rare_disease", "rarediseases",
            "geneticdisease", "genetic_disease", "geneticdisorder",
            "genetic_disorder", "huntingtonsdisease",
            "cysticfibrosis", "cystic_fibrosis",
            "musculardystrophy", "muscular_dystrophy",
            "sicklecell", "sickle_cell", "thalassemia",
            "hemophilia", "haemophilia", "marfan",
            "wilsonsdisease", "wilsons_disease",
            "pompe", "mitochondrialdisease", "mitochondrial_disease",

            # French
            "maladiechronique", "maladieschroniques",
            "douleurchronique", "douleurschroniques",
            "fatiguechronique", "maladierare", "maladiesrares",
            "diabete", "diabétique", "diabetique",
            "fibromyalgie", "sclérose", "sclerose",
            "endometriose", "endométriose", "lupusfr",
            "cancerfr", "thyroide", "thyroïde",
            "crohnfr", "polyarthrite", "arthrose",
            "migrainefr", "maladieautoimmune",

            # Spanish
            "enfermedadcronica", "enfermedad_cronica",
            "enfermedadescronicas", "dolorcronico",
            "fibromialgia", "diabetes", "endometriosis",
            "esclerosis", "lupus", "artritis", "crohn",
            "colitis", "enfermedadrara", "enfermedad_rara",

            # Portuguese
            "doencacronica", "doenca_cronica",
            "doencascronicas", "dorcronica", "fibromialgia",
            "diabetes", "endometriose", "esclerose",
            "artrite", "doencarara", "doenca_rara",

            # German
            "chronischekrankheit", "chronischeschmerzen",
            "fibromyalgie", "diabetes", "endometriose",
            "multiple_sklerose", "mskrankheit", "rheuma",
            "seltenekrankheit", "seltene_krankheit",

            # Italian
            "malattiacronica", "malattia_cronica",
            "dolorecronico", "fibromialgia",
            "diabete", "endometriosi", "sclerosi",
            "malattiarara", "malattia_rara",

            # Dutch
            "chronischeziekte", "chronische_ziekte",
            "chronischepijn", "fibromyalgie",
            "suikerziekte", "endometriose", "reuma",

            # Nordic and Slavic
            "kronisk", "kronisksjukdom", "kroniskesmerter",
            "krooninen", "pitkäaikaissairaus", "pitkaaikaissairaus",
            "przewlek", "chorobaprzewlek", "cukrzyc",
            "reumaty", "stwardnienierozsiane",
            "hronich", "diabetesru", "fibromialgia",

            # Arabic transliterations
            "maradmuzmin", "marad_muzmin", "amradmuzmina",
            "sukkar", "sukkari", "diabetesarab",
        ],
    ),

    (
        "mental_health",
        [
            # Common conditions
            "mentalhealth", "mental_health", "mentalillness",
            "mental_illness", "mentalill", "mentalwellness",
            "mentalwellbeing", "psychologicalhealth",
            "psychological", "psychiatr", "psychiatry",
            "psychosis", "psychotic", "schizo", "schizophrenia",
            "schizoaffective", "paranoia", "delusion",
            "bipolar", "mania", "manic", "depress",
            "depression", "depressive", "dysthymia",
            "anx", "anxiety", "anxious", "panic",
            "panicattack", "panic_attack", "phobia",
            "ocd", "obsessive", "compulsive",
            "ptsd", "cptsd", "trauma", "traumatic",
            "adhd", "add_", "addsupport", "attentiondeficit",
            "autism", "autistic", "neurodivergent",
            "neurodiversity", "bpd", "borderlinepersonality",
            "personalitydisorder", "dissociation", "did",
            "dissociative", "eatingdisorder", "eating_disorder",
            "anorexia", "bulimia", "binge_eating",
            "ocdpositive", "bodydysmorphia", "dysmorphia",
            "insomnia", "sleepdisorder", "sleep_disorder",
            "burnout", "stress", "overwhelm", "rumination",
            "suicid", "selfharm", "self_harm",
            "loneliness", "lonely", "grief", "bereavement",
            "addiction", "substanceuse", "substance_use",
            "dualdiagnosis", "dual_diagnosis",
            "psychotherapy", "psycholog", "therapy",
            "therapist", "counseling", "counselling",
            "psychoeducation", "psychoanalysis",
            "behavioralhealth", "behavioral_health",
            "emotionalhealth", "emotional_health",
            "mentaldisorder", "mental_disorder",
            "psychiatric", "psychosomatic",

            # Neurodevelopment and related support
            "adhdwomen", "adhdteen", "adhdteenagers",
            "adhdparent", "adhdparents", "adhdsupport",
            "adhdadvice", "adhdhelp", "adhdcombined",
            "adhdandocd", "adhdx", "autismadhd",
            "autismadhd", "executivedysfunction",
            "executive_dysfunction", "sensoryprocessing",
            "sensory_processing", "neurospicy",

            # French
            "santementale", "sante_mentale", "santémentale",
            "santé_mentale", "psychologie", "psychiatrie",
            "dépression", "depressionfr", "anxiété",
            "anxiete", "troubleanxieux", "troublesanxieux",
            "troublebipolaire", "bipolaire", "schizophrenie",
            "schizophrénie", "toc", "troubleobsessionnel",
            "stressposttraumatique", "tdah", "autisme",
            "neuroatypique", "neurodivergent", "burnoutfr",
            "épuisement", "epuisement", "phobie",
            "troublealimentaire", "troublesalimentaires",
            "psychothérapie", "psychotherapie",

            # Spanish
            "saludmental", "salud_mental", "depresion",
            "depresión", "ansiedad", "trastornobipolar",
            "trastorno_bipolar", "esquizofrenia",
            "toc", "tdah", "autismo", "trauma",
            "estres", "estrés", "psicologia", "psicología",
            "psiquiatria", "psiquiatría", "fobias",
            "trastornoalimentario", "trastorno_alimentario",

            # Portuguese
            "saudemental", "saude_mental", "saúde_mental",
            "depressao", "depressão", "ansiedade",
            "transtornobipolar", "transtorno_bipolar",
            "esquizofrenia", "tdah", "autismo",
            "psicologia", "psiquiatria", "toc",
            "estresse", "stress", "trauma",

            # German
            "psychischegesundheit", "psychische_gesundheit",
            "depression", "angststörung", "angststoerung",
            "bipolar", "schizophrenie", "zwangsstörung",
            "zwangsstoerung", "adhs", "autismus",
            "psychologie", "psychotherapie", "seelisch",
            "trauma", "burnout", "essstörung", "essstoerung",

            # Italian
            "salutementale", "salute_mentale",
            "depressione", "ansia", "bipolare",
            "schizofrenia", "psicologia", "psichiatria",
            "autismo", "disturbodansia", "disturbo_dansia",
            "ossessivocompulsivo", "trauma", "stress",

            # Dutch
            "geestelijkegezondheid", "geestelijke_gezondheid",
            "depressie", "angststoornis", "bipolair",
            "schizofrenie", "psychologie", "psychotherapie",
            "adhd", "autisme", "trauma", "burnout",

            # Nordic and Slavic
            "psykisk", "mielenterveys", "masennus",
            "ahdistus", "kaksisuuntainen", "skitsofrenia",
            "depresjon", "angstlidelse", "psykiskhelse",
            "depression", "ångest", "angest",
            "depresja", "zaburzenialekowe", "zaburzenia",
            "schizofrenia", "zdrowiepsychiczne",
            "dusevnezdravlje", "dusevnozdravlje",

            # Arabic transliterations
            "sihhanafsia", "siha_nafsiya", "sihhanafsiya",
            "nafsia", "nafsi", "iktieab", "iktiab",
            "qalaq", "waswas", "tawahhud",
        ],
    ),

    (
        "infectious",
        [
            # Respiratory and emerging infections
            "covid", "covid19", "covid-19", "coronavirus",
            "corona_virus", "sarscov", "sars-cov",
            "longcovid", "long_covid", "postcovid",
            "post_covid", "pandemic", "epidemic",
            "infect", "infection", "infectious",
            "communicabledisease", "communicable_disease",
            "virus", "viral", "virology", "viruses",
            "bacteria", "bacterial", "bacteriology",
            "fungal", "fungus", "fungi", "mycosis",
            "sepsis", "septic", "pathogen", "pathogens",
            "outbreak", "contagious", "transmission",
            "zoonotic", "zoonosis", "antiviral",
            "antibiotic", "antimicrobial", "antimicrobialresistance",
            "antimicrobial_resistance", "mrsa", "c_diff",
            "cdiff", "norovirus", "rotavirus", "adenovirus",
            "rsv", "influenza", "fluvirus", "birdflu",
            "swineflu", "mpox", "mpxvirus", "monkeypox",
            "zikavirus", "zika", "ebola", "marburg",
            "langyavirus", "langya", "nipah", "hantavirus",
            "westnile", "west_nile", "dengue", "chikungunya",
            "malaria", "tuberculosis", "tuberculosis",
            "tb_", "whoopingcough", "pertussis",
            "measles", "mumps", "rubella", "chickenpox",
            "shingles", "herpes", "coldsores", "varicella",
            "hiv", "aids", "std", "sti", "sexuallytransmitted",
            "sexually_transmitted", "gonorrhea", "gonorrhoea",
            "chlamydia", "syphilis", "hpv", "hepatitis",
            "hepatitisa", "hepatitisb", "hepatitisc",
            "lyme", "lymedisease", "lyme_disease",
            "tickborne", "tick_borne", "ticktokcancer",
            "toxoplasmosis", "candida", "candidiasis",
            "aspergillus", "aspergillosis", "cryptococcus",
            "parasit", "parasite", "parasitic",
            "worminfection", "worm_infection", "intestinalparasite",
            "intestinal_parasite", "ringworm", "scabies",
            "impetigo", "cellulitis", "uti", "urinaryinfection",
            "urinary_infection", "kidneyinfection",
            "kidney_infection", "pneumonia", "meningitis",
            "encephalitis", "endocarditis", "osteomyelitis",
            "infectiveendocarditis", "infective_endocarditis",
            "covidanosmia", "anosmia", "postviral",

            # French
            "maladieinfectieuse", "maladiesinfectieuses",
            "infectionvirale", "infectionbacterienne",
            "infectionbactérienne", "virusfr", "coronavirusfr",
            "covidfr", "grippe", "vih", "sida",
            "herpes", "herpès", "ist", "mst",
            "tuberculose", "maladiedeLyme", "maladie_lyme",
            "paludisme", "dengue", "rougeole",
            "coqueluche", "varicelle", "zona",
            "hepatite", "hépatite", "hepatiteb",
            "hepatitec", "infectionurinaire",

            # Spanish
            "enfermedadinfecciosa", "enfermedad_infecciosa",
            "infeccion", "infección", "virus", "viral",
            "coronavirus", "gripe", "vih", "sida",
            "herpes", "its", "ets", "tuberculosis",
            "paludismo", "malaria", "dengue", "sarampion",
            "sarampión", "hepatitis", "varicela", "culebrilla",

            # Portuguese
            "doencainfecciosa", "doenca_infecciosa",
            "infecção", "infeccao", "infecciosa",
            "coronavirus", "gripe", "hiv", "aids",
            "herpes", "ist", "tuberculose", "malaria",
            "dengue", "sarampo", "hepatite", "catapora",

            # German
            "infektionskrankheit", "infektionskrankheiten",
            "infektion", "virus", "coronavirus",
            "grippe", "hiv", "aids", "herpes",
            "sexuellübertragbar", "sexuelluebertragbar",
            "tuberkulose", "borreliose", "zecken",
            "masern", "windpocken", "gürtelrose", "guertelrose",

            # Italian
            "malattiainfettiva", "malattia_infettiva",
            "infezione", "virus", "coronavirus",
            "influenza", "hiv", "aids", "herpes",
            "malattiatrasmissibile", "malattia_trasmissibile",
            "tubercolosi", "malaria", "dengue", "morbillo",

            # Dutch
            "infectieziekte", "infectieziekten",
            "infectie", "virus", "coronavirus",
            "griep", "hiv", "aids", "herpes",
            "soa", "tuberculose", "lyme", "mazelen",

            # Nordic and Slavic
            "infektion", "smittsam", "virussjukdom",
            "tartuntatauti", "virusinfektion", "influensa",
            "tuberkuloosi", "borrelia", "zakaź", "zakaz",
            "chorobazakazna", "choroba_zakazna",
            "zakazenie", "zakażenie", "grypa", "odra",
            "ospawietrzna", "wirus", "covid",

            # Arabic transliterations
            "maradmaad", "marad_maadi", "amradmaadia",
            "adwa", "virusarab", "coronaarab",
            "korona", "taoon", "taun", "malariaarab",
        ],
    ),

    (
        "surgical",
        [
            # Surgery and procedures
            "surg", "surgery", "surgeon", "surgical",
            "postsurgery", "post_surgery", "presurgery",
            "pre_surgery", "aftersurgery", "after_surgery",
            "recovery", "postoperative", "post-operative",
            "perioperative", "peri-operative", "operation",
            "operatingroom", "operating_room", "theatre",
            "anesthesia", "anaesthesia", "anesthesiology",
            "anaesthesiology", "transplant", "transplantation",
            "organtransplant", "organ_transplant",
            "bariatric", "gastricbypass", "gastric_bypass",
            "sleevegastrectomy", "sleeve_gastrectomy",
            "appendectomy", "appendicectomy", "cholecystectomy",
            "hysterectomy", "mastectomy", "prostatectomy",
            "colectomy", "ileostomy", "colostomy",
            "laparoscopy", "laparoscopic", "endoscopy",
            "arthroscopy", "neurosurgery", "cardiac_surgery",
            "heartsurgery", "heartsurgery", "plasticsurgery",
            "plastic_surgery", "cosmeticsurgery", "cosmetic_surgery",
            "reconstructive", "orthopedic", "orthopaedic",
            "orthopaedicsurgery", "spinalsurgery", "spinal_surgery",
            "scoliosis", "scolio", "spine", "backpain",
            "back_pain", "back", "disc", "herniateddisc",
            "herniated_disc", "laminectomy", "fusion",
            "shoulder", "rotatorcuff", "rotator_cuff",
            "kneesurgery", "knee_surgery", "hipreplacement",
            "hip_replacement", "jointreplacement", "joint_replacement",
            "acl", "meniscus", "ligament", "tendon",
            "fracture", "orthopedic", "orthopaedic",
            "amputation", "woundcare", "wound_care",
            "burnsurgery", "burn_surgery", "ey esurgery",
            "lasik", "cataractsurgery", "cataract_surgery",
            "dentalimplant", "dental_implant", "oral_surgery",
            "maxillofacial", "periodontal", "gum_surgery",
            "tonsillectomy", "septoplasty", "rhinoplasty",
            "thyroidectomy", "nephrectomy", "prolapse",
            "pelvicfloor", "pelvic_floor", "hernia",
            "herniarepair", "hernia_repair", "womenssurgery",
            "genderaffirming", "gender_affirming",
            "genderconfirmation", "gender_confirmation",
            "top_surgery", "bottom_surgery",
            "genderreassignment", "gender_reassignment",

            # Rehabilitation and physical medicine
            "physiotherapy", "physicaltherapy", "physical_therapy",
            "rehabilitation", "rehab", "occupationaltherapy",
            "occupational_therapy", "chiropractic", "myotherapy",
            "cardiopulmonaryrehab", "cardiopulmonary_rehab",
            "postop", "post_op", "surgeryrecovery",
            "surgery_recovery", "surgerycomplications",
            "surgery_complications", "surgicalcomplications",
            "surgical_complications", "surgerysupport",

            # French
            "chirurgie", "chirurgical", "chirurgien",
            "postoperatoire", "postopératoire", "operation",
            "opération", "intervention", "reeducation",
            "rééducation", "physiotherapie", "physiothérapie",
            "orthopedie", "orthopédie", "rachis",
            "colonnevertebrale", "colonne_vertébrale",
            "scoliose", "prothese", "prothèse",
            "genou", "hanche", "epaule", "épaule",
            "hernie", "greffe", "transplantation",
            "chirurgieplastique", "chirurgie_plastique",

            # Spanish
            "cirugia", "cirugía", "quirurg", "quirúrg",
            "postoperatorio", "postoperatoria",
            "rehabilitacion", "rehabilitación",
            "fisioterapia", "ortopedia", "escoliosis",
            "columna", "rodilla", "hombro", "cadera",
            "protesis", "prótesis", "trasplante",
            "cirugiaplastica", "cirugia_plastica",

            # Portuguese
            "cirurgia", "cirurgiao", "cirurgião",
            "posoperatorio", "pós-operatório",
            "reabilitacao", "reabilitação",
            "fisioterapia", "ortopedia", "escoliose",
            "coluna", "joelho", "ombro", "quadril",
            "proteses", "próteses", "transplante",
            "cirurgiaplastica", "cirurgia_plastica",

            # German
            "chirurgie", "chirurgisch", "operation",
            "nachoperation", "postoperativ", "rehabilitation",
            "physiotherapie", "orthopädie", "orthopaedie",
            "skoliose", "wirbelsäule", "wirbelsaeule",
            "knieoperation", "hüftoperation", "hueftoperation",
            "schulter", "transplantation", "plastischechirurgie",

            # Italian
            "chirurgia", "chirurgico", "postoperatorio",
            "riabilitazione", "fisioterapia", "ortopedia",
            "scoliosi", "colonna", "ginocchio", "spalla",
            "anca", "trapianto", "chirurgiaplastica",

            # Dutch
            "chirurgie", "operatie", "postoperatief",
            "revalidatie", "fysiotherapie", "orthopedie",
            "scoliose", "wervelkolom", "knieoperatie",
            "schouder", "heupprothese", "transplantatie",

            # Nordic and Slavic
            "kirurgi", "operation", "rehabilitering",
            "fysioterapi", "rygg", "skolios",
            "leikkaus", "leikkauksen", "kuntoutus",
            "chirurgia", "operacja", "pooperacyj",
            "rehabilitacja", "fizjoterapia", "ortopedia",
            "skolioza", "kregoslup", "kręgosłup",
            "kolano", "bark", "transplantacja",

            # Arabic transliterations
            "jiraha", "jirahi", "amaliyya", "amaliya",
            "taheel", "taehil", "orthopedic_arab",
        ],
    ),

    (
        "general",
        [
            # Healthcare and medicine
            "health", "healthcare", "health_care", "healthy",
            "medicine", "medical", "medic", "doctor", "doctors",
            "doctorer", "askdocs", "askdoctor", "askadoctor",
            "diagnos", "diagnose", "diagnosis", "misdiagnosis",
            "patient", "patients", "patientcare", "patient_care",
            "hospital", "hospitals", "clinic", "clinical",
            "nurse", "nursing", "nurses", "pharmacy",
            "pharmacist", "pharmaceutical", "pharma",
            "biopharma", "biotech", "telehealth", "telemedicine",
            "publichealth", "public_health", "globalhealth",
            "global_health", "communityhealth", "community_health",
            "primarycare", "primary_care", "familymedicine",
            "family_medicine", "internalmedicine", "internal_medicine",
            "emergencymedicine", "emergency_medicine",
            "urgentcare", "urgent_care", "healthsystem",
            "health_system", "healthpolicy", "health_policy",
            "healthinsurance", "health_insurance", "healthcarecost",
            "healthcare_cost", "medicalbill", "medical_bill",
            "healthdata", "health_data", "healthinformatics",
            "health_informatics", "healthanalytics",
            "health_analytics", "digitalhealth", "digital_health",
            "ehealth", "mhealth", "healthtech", "health_tech",
            "medtech", "medicaltechnology", "medical_technology",
            "medicalresearch", "medical_research", "clinicalresearch",
            "clinical_research", "medicaleducation",
            "medical_education", "medicalschool", "medical_school",
            "medstudent", "medstudents", "premed", "premedical",
            "residency", "residentdoctor", "resident_doctor",
            "foundationdoctor", "foundation_doctor",
            "internship", "physician", "physicians",
            "generalpractice", "general_practice",
            "healthtips", "healthadvice", "health_advice",
            "healthquestions", "health_questions", "healthsupport",
            "health_support", "healthconcern", "health_concern",
            "wellness", "wellbeing", "well_being",
            "selfcare", "self_care", "prevention",
            "preventive", "screening", "checkup", "check_up",
            "vaccine", "vaccines", "vaccination", "immunization",
            "immunisation", "nutrition", "dietitian",
            "dietician", "clinicalnutrition", "clinical_nutrition",
            "firstaid", "first_aid", "cpr", "medicalemergency",
            "medical_emergency", "symptom", "symptoms",
            "medicaladvice", "medical_advice", "medicalhelp",
            "medical_help", "medicalquestion", "medical_question",
            "medicalcondition", "medical_condition",
            "healthcondition", "health_condition",
            "healthdepartment", "health_department",
            "healthministry", "health_ministry",
            "healthliteracy", "health_literacy",
            "patienteducation", "patient_education",
            "medicalinformation", "medical_information",
            "medicalcommunication", "medical_communication",
            "evidencebased", "evidence_based",
            "evidencebasedmedicine", "evidence_based_medicine",
            "healthresearch", "health_research",
            "medicineapplication", "medicine_applications",
            "medicalcoding", "medical_coding",
            "diagnostic", "diagnostics", "radiology",
            "radiography", "pathology", "laboratorymedicine",
            "laboratory_medicine", "labmedicine",
            "medicalimaging", "medical_imaging",
            "ultrasound", "mri", "ctscan", "ct_scan",
            "bloodtest", "blood_test", "bloodwork",
            "biomarker", "biomarkers", "genomics",
            "precisionmedicine", "precision_medicine",
            "personalizedmedicine", "personalized_medicine",
            "personalisedmedicine", "personalised_medicine",
            "integrativemedicine", "integrative_medicine",
            "holisticmedicine", "holistic_medicine",
            "alternativemedicine", "alternative_medicine",
            "orientalmedicine", "oriental_medicine",
            "naturopath", "herbalmedicine", "herbal_medicine",
            "pharmacology", "toxicology", "epidemiology",
            "biostatistics", "medicalethics", "medical_ethics",
            "bioethics", "healthcareworker", "healthcare_worker",
            "healthcareworkers", "healthcare_workers",
            "hospitalworker", "hospital_worker",
            "hospitalstaff", "hospital_staff",
            "healthcarejobs", "healthcare_jobs",
            "healthcarecareer", "healthcare_career",
            "nursingstudent", "nursing_student",
            "nursingstudents", "nursing_students",
            "pharmacytech", "pharmacy_tech",
            "healthinsurance", "insurancemedical",
            "medicaldebt", "medical_debt",
            "healthcareaccess", "healthcare_access",
            "universalhealthcare", "universal_healthcare",
            "healthcarequality", "healthcare_quality",
            "healthdisparities", "health_disparities",
            "healthinequality", "health_inequality",
            "healthcarefraud", "healthcare_fraud",
            "medicalerror", "medical_error",
            "medicalerrors", "medical_errors",
            "patientrights", "patient_rights",
            "patientadvocacy", "patient_advocacy",
            "patientexperience", "patient_experience",
            "patientstories", "patient_stories",
            "healthforum", "health_forum",
            "healthcommunity", "health_community",
            "medicalcommunity", "medical_community",
            "askpharmacy", "asknurses", "asknurse",
            "askmedical", "youshouldseeadoctor",
            "imnodoctor", "notadoctor", "not_a_doctor",

            # French
            "sante", "santé", "medicalfr", "médical",
            "medecine", "médecine", "medecin", "médecin",
            "docteur", "hopital", "hôpital", "hopitaux",
            "clinique", "infirmier", "infirmiere",
            "infirmière", "pharmacie", "pharmacien",
            "soins", "soinsdesante", "soins_de_sante",
            "santépublique", "santepublique", "sante_publique",
            "santé_publique", "patientfr", "patientsfr",
            "diagnostic", "diagnostique", "symptome",
            "symptôme", "symptomes", "symptômes",
            "conseilmedical", "conseil_medical",
            "questionmedicale", "question_medicale",
            "urgence", "urgences", "prevention",
            "prévention", "vaccination", "vaccin",
            "recherchemedicale", "recherche_medicale",
            "litteratiesante", "litteratie_sante",
            "littératiesanté", "littératie_santé",
            "informationmedicale", "information_medicale",
            "assurancemaladie", "assurance_maladie",
            "mutuelle", "securitesociale", "securite_sociale",
            "sécuritésociale", "sécurité_sociale",

            # Spanish
            "salud", "medicina", "medico", "médico",
            "medica", "médica", "doctor", "doctores",
            "hospital", "hospitales", "clinica", "clínica",
            "enfermeria", "enfermería", "enfermero",
            "farmacia", "farmaceutico", "farmacéutico",
            "saludpublica", "salud_publica", "paciente",
            "pacientes", "diagnostico", "diagnóstico",
            "sintoma", "síntoma", "sintomas", "síntomas",
            "consejomedico", "consejo_medico",
            "atencionprimaria", "atencion_primaria",
            "prevencion", "prevención", "vacunacion",
            "vacunación", "investigacionmedica",
            "investigacion_medica", "seguridadsocial",
            "segurodesalud", "seguro_de_salud",

            # Portuguese
            "saude", "saúde", "medicina", "medico",
            "médico", "medica", "médica", "doutor",
            "hospital", "clinica", "clínica",
            "enfermagem", "enfermeiro", "farmacia",
            "farmácia", "farmaceutico", "farmacêutico",
            "saudepublica", "saude_publica", "saúde_pública",
            "paciente", "pacientes", "diagnostico",
            "diagnóstico", "sintoma", "sintomas",
            "conselhomedico", "conselho_medico",
            "atencaoprimaria", "atencao_primaria",
            "prevencao", "prevenção", "vacinacao",
            "vacinação", "pesquisamedica", "pesquisa_medica",
            "planodesaude", "plano_de_saude",

            # German
            "gesundheit", "medizin", "mediziner",
            "arzt", "ärzte", "aerzte", "ärztin",
            "aerztin", "krankenhaus", "klinik",
            "pflege", "krankenpflege", "apotheke",
            "apotheker", "gesundheitswesen",
            "gesundheitswesen", "öffentlichegesundheit",
            "oeffentlichegesundheit", "patient",
            "patienten", "diagnose", "symptom",
            "symptome", "medizinischeberatung",
            "medizinische_beratung", "krankenversicherung",
            "krankenversicherung", "vorsorge", "impfung",
            "impfungen", "gesundheitssystem",
            "gesundheitssystem", "medizinischeforschung",

            # Italian
            "salute", "medicina", "medico", "medici",
            "ospedale", "ospedali", "clinica",
            "infermier", "farmacia", "farmacista",
            "salutepubblica", "salute_pubblica",
            "paziente", "pazienti", "diagnosi",
            "sintomo", "sintomi", "consigliomedico",
            "consiglio_medico", "prevenzione",
            "vaccinazione", "ricercamedica", "ricerca_medica",
            "assicurazionesanitaria", "assicurazione_sanitaria",

            # Dutch
            "gezondheid", "geneeskunde", "medisch",
            "arts", "dokter", "ziekenhuis", "kliniek",
            "verpleegkunde", "verpleegkundige", "apotheek",
            "apotheker", "volksgezondheid", "patient",
            "patiënt", "patienten", "patiënten",
            "diagnose", "symptoom", "symptomen",
            "medischadvies", "medisch_advies",
            "zorgverzekering", "zorg", "preventie",
            "vaccinatie", "medischonderzoek",

            # Nordic
            "hälsa", "halsa", "sjukvård", "sjukvard",
            "medicin", "läkare", "lakare", "sjukhus",
            "vård", "vard", "sykehus", "helse",
            "helsetjeneste", "lege", "sykepleie",
            "terveydenhuolto", "terveys", "lääkäri",
            "laakari", "sairaala", "potilas",
            "terveystieto", "sundhed", "læge", "laege",
            "hospital", "sundhedsvæsen", "sundhedsvaesen",

            # Slavic
            "zdrowie", "medycyna", "lekarz", "lekarze",
            "szpital", "pielegniar", "pielęgniar",
            "apteka", "pacjent", "pacjenci",
            "diagnoza", "objawy", "profilaktyka",
            "zdrowiepubliczne", "zdrowie_publiczne",
            "zdravlje", "medicina", "lekar", "bolnica",
            "zdravotnictvo", "zdravotnictví",
            "zdravotnictvi", "nemocnica", "nemocnice",
            "zdravotnictwo", "zdravotní", "zdravotni",
            "zdravookhranenie", "zdorovie",
            "meditsina", "vrach", "bolnitsa",
            "zdorovye", "apteka", "pacient",

            # Arabic transliterations
            "siha", "sihha", "sihiya", "tibb",
            "tabib", "doctorarab", "atibba",
            "mustashfa", "mustashfaa", "marid",
            "maridun", "amrad", "dawa", "adwiya",
            "saydaliya", "saydali", "riaya_sihiya",
            "riayasihiya", "tibbi", "seha",
            "saglik", "saglık", "doktor", "hastane",
            "ilac", "ilaclar",
        ],
    ),
]


def map_language(raw):
    if not isinstance(raw, str) or not raw.strip():
        return "non-english"
    code = raw.strip().lower().replace("_", "-").split("-")[0]
    return code if code in TARGET_LANGS and code=="en" else "non-english"


def assign_category(name_lc):
    for category, words in KEYWORDS:
        if any(w in name_lc for w in words):
            return category
    return "general"


def assign_sample_group(language, data):
    if data.get("subreddit_type") in ("private", "archived") or data.get("quarantine") is True:
        return "governance_vacuum"
    if language == "en":
        return "english_core"
    if language in ("es", "fr", "hi", "ar"):
        return "multilingual"
    return "non-english-core"  # language unknown: spec doesn't say; flagged for review


def iter_records(path):
    """Yield (line_no, record_or_None, error_or_None).

    Primary mode: JSONL (one record per line). Tolerates trailing commas and
    stray '[' / ']' lines. If the file turns out to be pretty-printed
    multi-line JSON, falls back to a streaming decoder.
    """
    text = Path(path).read_text(encoding="utf-8")
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    jsonl = False
    if first.rstrip(",").startswith("{"):
        try:
            json.loads(first.rstrip(","))
            jsonl = True
        except json.JSONDecodeError:
            pass

    if jsonl:
        for n, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if not s:
                yield n, None, "blank line"
                continue
            if s in ("[", "]", ","):
                yield n, None, "array bracket/separator line"
                continue
            try:
                yield n, json.loads(s.rstrip(",")), None
            except json.JSONDecodeError as e:
                yield n, None, f"invalid JSON ({e.msg})"
    else:
        dec = json.JSONDecoder()
        i, n = 0, 0
        while i < len(text):
            while i < len(text) and text[i] in " \t\r\n,[]":
                i += 1
            if i >= len(text):
                break
            n += 1
            try:
                obj, i = dec.raw_decode(text, i)
                yield n, obj, None
            except json.JSONDecodeError as e:
                yield n, None, f"invalid JSON ({e.msg}) near char {i}"
                break  # cannot resync reliably


def main():
    now = time.time()
    total = parsed = 0
    skipped = []  # (line_no, reason)
    rows = {}  # lowercased name -> row dict

    for line_no, rec, err in iter_records(INPUT):
        total += 1
        if err:
            skipped.append((line_no, err))
            continue
        if not isinstance(rec, dict):
            skipped.append((line_no, "record is not a JSON object"))
            continue

        data = ((rec.get("metadata") or {}).get("data")) if isinstance(rec.get("metadata"), dict) else None
        if not isinstance(data, dict):
            skipped.append((line_no, "missing metadata.data" +
                            (f" (collection_error={rec.get('collection_error')})" if rec.get("collection_error") else "")))
            continue
        name = data.get("display_name")
        if not isinstance(name, str) or not name.strip():
            skipped.append((line_no, "missing display_name"))
            continue
        parsed += 1

        key = name.lower()
        if key in rows:
            skipped.append((line_no, f"duplicate community '{name}' (kept first occurrence)"))
            continue

        language = map_language(data.get("lang"))
        row = {
            "subreddit_name": name,
            "language": language,
            "disease_category": assign_category(key),
            "sample_group": assign_sample_group(language, data),
        }
        for f in GOVERNANCE_FIELDS:
            row[f] = data.get(f)  # None if missing

        created = data.get("created_utc")
        row["community_age_days"] = (
            int((now - created) // 86400) if isinstance(created, (int, float)) else None
        )
        rows[key] = row

    ordered = sorted(
        rows.values(),
        key=lambda r: (r["language"], r["disease_category"], r["subreddit_name"].lower()),
    )

    with open(OUTPUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in ordered:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})

    Path(LOGFILE).parent.mkdir(parents=True, exist_ok=True)
    lang_c = Counter(r["language"] for r in ordered)
    cat_c = Counter(r["disease_category"] for r in ordered)
    grp_c = Counter(r["sample_group"] for r in ordered)
    with open(LOGFILE, "w", encoding="utf-8") as lg:
        lg.write(f"Run at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}\n")
        lg.write(f"Input: {INPUT}\nOutput: {OUTPUT}\n\n")
        lg.write(f"Total lines read: {total}\n")
        lg.write(f"Lines parsed successfully: {parsed}\n")
        lg.write(f"Lines skipped: {len(skipped)}\n")
        for ln, reason in skipped:
            lg.write(f"  - line {ln}: {reason}\n")
        lg.write(f"\nUnique communities: {len(ordered)}\n")
        for title, c in (("Count per language", lang_c),
                         ("Count per disease category", cat_c),
                         ("Count per sample group", grp_c)):
            lg.write(f"\n{title}:\n")
            for k, v in sorted(c.items()):
                lg.write(f"  {k}: {v}\n")

    print(f"Wrote {len(ordered)} rows to {OUTPUT}; log at {LOGFILE}")


if __name__ == "__main__":
    main()