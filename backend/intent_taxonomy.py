"""The intent taxonomy and its semantic training examples.

This file is DATA, not logic: each intent is defined by example phrasings
that mean it, and classification happens by embedding similarity against
these examples (see semantic_intent.py) rather than by matching keywords in
them. That distinction matters - "how does X stack up against Y" is in the
COMPARE list not because "stack up" becomes a keyword, but because its
embedding sits near the other COMPARE examples, which also makes unseen
phrasings like "how do these two measure up" land in the right place.

Adding a phrasing here improves coverage for everything semantically near
it, which is why the lists are short and deliberately varied (formal,
casual, slang, elliptical) instead of exhaustive.
"""

# Canonical intents. FOLLOWUP/CLARIFICATION are conversational states rather
# than research tasks, so they're detected separately (see intent.py) and
# combined with whichever task intent the resolved question turns out to be.
INTENTS = (
    "FACTUAL",
    "RESEARCH",
    "COMPARE",
    "ANALYZE",
    "SUMMARY",
    "VERIFY",
    "RECOMMEND",
    "CHITCHAT",
)

# Intent -> example phrasings that mean it. Entity names are deliberately
# generic ("X", "the car") so similarity is driven by the *shape* of the
# request rather than by which vehicle is mentioned.
INTENT_EXAMPLES: dict[str, list[str]] = {
    "FACTUAL": [
        "what engine does X use",
        "tell me the engine of X",
        "what is under the hood of X",
        "how many cylinders does it have",
        "give me the engine specification",
        "what is the top speed of X",
        "how much horsepower does X make",
        "what is the weight of X",
        "how many gears does the gearbox have",
        "what is X's fuel tank capacity",
        "what's X packing",
        "how quick is X",
        "does X have all-wheel drive",
        "when was X released",
        "how much does X cost",
    ],
    "RESEARCH": [
        "research X",
        "look into the engineering behind X",
        "do a deep dive into X",
        "investigate how X was engineered",
        "give me a detailed study of X",
        "tell me everything about how X works",
        "find out how the manufacturer built X",
        "i want a full report on X",
        "explore the technology in X",
        "write up the engineering of X",
        "what is the story behind X's development",
        "comprehensive overview of X",
    ],
    "COMPARE": [
        "compare X and Y",
        "X vs Y",
        "how does X stack up against Y",
        "which one is better",
        "put X and Y head to head",
        "what is the difference between X and Y",
        "how do these two differ",
        "which of them performs better",
        "how does X fare against Y",
        "which is faster between the two",
        "put the two against each other",
        "how do these two compare",
        "which one would win",
        "X or Y, which is stronger",
        "how do they measure up to each other",
        "which is lighter",
        "rank these against each other",
        "pros and cons of each",
    ],
    "ANALYZE": [
        "why does the manufacturer use this approach",
        "break down the engineering",
        "what makes this design effective",
        "explain the engineering decisions",
        "what are the trade-offs",
        "why is this thing so fast",
        "how does this system actually work",
        "what is the reasoning behind this choice",
        "break this down for me",
        "what are the implications of this design",
        "explain why this matters",
        "what compromises did this create",
        # Sampled escalations: "analyze the X aerodynamic design" scored
        # FACTUAL over ANALYZE without a phrasing like this in the catalog, and
        # a near-tie between two DIFFERENT tiers is what costs a router call.
        "analyze the aerodynamic design",
        "analyze the design of this",
        "analyze how this was engineered",
        "assess the engineering of this",
    ],
    "SUMMARY": [
        "summarize this",
        "give me a summary of X",
        "tl;dr of the document",
        "sum up the key points",
        "what are the highlights",
        "condense this into the main points",
        "brief me on X",
        "shorten this",
        # The corpus includes quarterly financial filings, and "summarize the
        # Q2 results" was landing on FACTUAL without an example in this register.
        "summarize the quarterly results",
        "summarize the results",
        "give me the key figures from the report",
        "what did the report say",
    ],
    "VERIFY": [
        "is that correct",
        "are you sure",
        "check that again",
        "can you verify this",
        "double-check those claims",
        "is this supported by the documents",
        "cross-check your previous answer",
        "confirm those numbers",
        "did you get that right",
        "is that actually true",
        "prove it with the sources",
        "fact-check what you just said",
        "verify whether the claims are supported by the retrieved documents",
        "does the evidence really back that up",
    ],
    "RECOMMEND": [
        "which one should i buy",
        "what would you recommend",
        "which is the better choice for me",
        "what should i pick",
        "which would you go for",
        "is X worth it",
    ],
    "CHITCHAT": [
        "hello",
        "hi there",
        "thanks",
        "thank you",
        "good morning",
        "goodbye",
        "who are you",
        "what can you do",
    ],
}

# Sub-intent (comparison/analysis dimension) -> example phrasings. Lets
# "which one is faster" become COMPARE + PERFORMANCE, so retrieval and the
# answer can focus on the dimension actually asked about.
DIMENSION_EXAMPLES: dict[str, list[str]] = {
    "PERFORMANCE": [
        "which is faster",
        "top speed and acceleration",
        "how quick is it",
        "lap time and track performance",
        "power and torque output",
        "0-100 acceleration",
    ],
    "ENGINEERING": [
        "which is better engineered",
        "engineering philosophy and design approach",
        "how the drivetrain is built",
        "construction and materials",
        "chassis and monocoque design",
        "technical sophistication",
    ],
    "AERODYNAMICS": [
        "downforce and drag",
        "aerodynamic design",
        "active aero and wings",
        "airflow management",
    ],
    "WEIGHT": [
        "which is lighter",
        "kerb weight and mass",
        "power to weight ratio",
        "weight distribution",
    ],
    "PRACTICALITY": [
        "which is more practical",
        "daily usability and comfort",
        "luggage space and interior",
        "ride quality on normal roads",
    ],
    "DRIVER_INVOLVEMENT": [
        "which is more engaging to drive",
        "driver feedback and feel",
        "how involving the driving experience is",
        "analogue versus digital feel",
    ],
    "PRICE": [
        "which is cheaper",
        "cost and value for money",
        "price comparison",
        "how much they cost",
    ],
    "RELIABILITY": [
        "which is more reliable",
        "durability and build quality",
        "maintenance and running costs",
    ],
}

# Abbreviation/shorthand -> expansion, applied to the NORMALIZED query only
# (the user's original text is always preserved and displayed unchanged).
# Deliberately domain-specific and small: these are expansions that genuinely
# help retrieval match spec-sheet wording, not a general spellcheck.
ABBREVIATIONS: dict[str, str] = {
    "hp": "horsepower",
    "bhp": "brake horsepower",
    "ps": "metric horsepower",
    "rpm": "revolutions per minute",
    "nm": "newton-metres of torque",
    "kw": "kilowatts",
    "awd": "all-wheel drive",
    "rwd": "rear-wheel drive",
    "fwd": "front-wheel drive",
    "vmax": "top speed",
    "0-60": "0-60 mph acceleration",
    "0-100": "0-100 km/h acceleration",
    "dct": "dual-clutch transmission",
    "cc": "cubic centimetres displacement",
    "mpg": "miles per gallon",
    "tl;dr": "summary",
    "tldr": "summary",
    "specs": "specifications",
    "spec": "specification",
}

# Known entity vocabulary for fuzzy correction ("Bugati" -> "Bugatti"). Only
# used with a high similarity threshold - see nlp.py - because silently
# rewriting a word the user actually meant is worse than leaving a typo.
KNOWN_ENTITIES: tuple[str, ...] = (
    "Bugatti",
    "Bugatti Chiron",
    "Chiron",
    "Chiron Sport",
    "Chiron Super Sport",
    "Centodieci",
    "Bugatti Tourbillon",
    "Tourbillon",
    "Bugatti Mistral",
    "W16 Mistral",
    "Divo",
    "Veyron",
    "Koenigsegg",
    "Koenigsegg Jesko",
    "Jesko",
    "Jesko Absolut",
    "Gemera",
    "Regera",
    "Pagani",
    "Pagani Utopia",
    "Utopia",
    "Huayra",
    "Zonda",
    "Ferrari",
    "Lamborghini",
    "Revuelto",
    "Aventador",
    "Huracan",
    "McLaren",
    "Rimac",
    "Nevera",
    "Porsche",
    "Mercedes",
    "Tesla",
)

# --- Marque scoping -----------------------------------------------------------
# Which marque each known vehicle belongs to. A question naming only Bugatti
# cars should be answered from Bugatti documents; naming a Bugatti and a
# Ferrari should search both. Without this, BM25 happily returns Ferrari
# revenue tables for "what is the Chiron's top speed" simply because the
# corpus contains far more Ferrari pages than Chiron pages - see
# retrieval.py's brand filtering.
BRAND_OF_ENTITY: dict[str, str] = {
    "Bugatti": "bugatti",
    "Bugatti Chiron": "bugatti",
    "Chiron": "bugatti",
    "Chiron Sport": "bugatti",
    "Chiron Super Sport": "bugatti",
    "Centodieci": "bugatti",
    "Bugatti Tourbillon": "bugatti",
    "Tourbillon": "bugatti",
    "Bugatti Mistral": "bugatti",
    "W16 Mistral": "bugatti",
    "Divo": "bugatti",
    "Veyron": "bugatti",
    "Ferrari": "ferrari",
    "Pagani": "pagani",
    "Pagani Utopia": "pagani",
    "Utopia": "pagani",
    "Huayra": "pagani",
    "Zonda": "pagani",
    "Koenigsegg": "koenigsegg",
    "Koenigsegg Jesko": "koenigsegg",
    "Jesko": "koenigsegg",
    "Jesko Absolut": "koenigsegg",
    "Gemera": "koenigsegg",
    "Regera": "koenigsegg",
    "Lamborghini": "lamborghini",
    "Revuelto": "lamborghini",
    "Aventador": "lamborghini",
    "Huracan": "lamborghini",
    "McLaren": "mclaren",
    "Rimac": "rimac",
    "Nevera": "rimac",
    "Porsche": "porsche",
    "Mercedes": "mercedes",
    "Tesla": "tesla",
}

BRAND_LABEL: dict[str, str] = {
    "bugatti": "Bugatti",
    "ferrari": "Ferrari",
    "pagani": "Pagani",
    "koenigsegg": "Koenigsegg",
    "lamborghini": "Lamborghini",
    "mclaren": "McLaren",
    "rimac": "Rimac",
    "porsche": "Porsche",
    "mercedes": "Mercedes",
    "tesla": "Tesla",
}

# Filename fragments that identify which marque a document belongs to.
# Filenames are what's available: the corpus is manufacturer press material
# whose names are inconsistent ("211122_BU_Chiron ENG.pdf",
# "tourbillon-screen-to-track.pdf"), so model names have to be matched too,
# not just marque names. Documents matching nothing here are treated as
# unattributed and are NEVER filtered out - a wrong exclusion silently hides
# evidence, which is worse than a loose match.
BRAND_FILENAME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bugatti": ("bugatti", "chiron", "centodieci", "tourbillon", "mistral", "w16", "divo", "veyron", "_bu_"),
    "ferrari": ("ferrari",),
    "pagani": ("pagani", "huayra", "zonda", "utopia"),
    "koenigsegg": ("koenigsegg", "jesko", "gemera", "regera"),
    "lamborghini": ("lamborghini", "revuelto", "aventador", "huracan"),
    "mclaren": ("mclaren",),
    "rimac": ("rimac", "nevera"),
    "porsche": ("porsche",),
}


def brands_for_entities(values) -> list[str]:
    """Marques named (directly or via one of their models) by a question,
    in first-mentioned order."""
    brands = []
    for value in values:
        brand = BRAND_OF_ENTITY.get(value)
        if brand and brand not in brands:
            brands.append(brand)
    return brands


def brand_for_filename(name: str) -> str | None:
    """Marque a document belongs to, or None when its filename says nothing."""
    lowered = (name or "").lower()
    for brand, keywords in BRAND_FILENAME_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return brand
    return None


# Component/system vocabulary, used for typed entity extraction so a query
# about "the transmission" can be routed/retrieved as a component question
# even when no vehicle is named in that turn.
KNOWN_COMPONENTS: tuple[str, ...] = (
    "engine",
    "transmission",
    "gearbox",
    "turbocharger",
    "aerodynamics",
    "chassis",
    "monocoque",
    "suspension",
    "brakes",
    "tires",
    "tyres",
    "differential",
    "exhaust",
    "intercooler",
    "cooling",
    "battery",
    "hybrid system",
    "electric motor",
    "wing",
    "diffuser",
    "steering",
    "interior",
    "bodywork",
)
