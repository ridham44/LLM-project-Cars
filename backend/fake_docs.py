import random

from faker import Faker

import config

fake = Faker()

TOPICS = {
    "hypercar-performance": [
        "Hybrid hypercars now pair turbocharged V6 engines with multiple electric motors for instant torque.",
        "Active aerodynamics adjust wing angles in real time to balance downforce against top-speed runs.",
        "Carbon fiber monocoque chassis construction keeps curb weight down despite added battery mass.",
        "Some hypercars now exceed 1,500 horsepower while meeting increasingly strict emissions regulations.",
    ],
    "supercar-manufacturers": [
        "Italian marques continue to compete with British and American builders for the fastest production lap times.",
        "Limited production runs of under 100 units keep exclusivity high for flagship models.",
        "Bespoke customization programs let buyers spec unique paint, interior, and trim combinations.",
        "Manufacturers are opening dedicated test tracks to validate handling before customer delivery.",
    ],
    "track-and-lap-records": [
        "The Nurburgring Nordschleife remains the benchmark circuit for supercar lap time records.",
        "Slick tires and stripped interiors shave crucial seconds off track-focused variants.",
        "Traction control and torque vectoring systems help drivers extract lap time safely.",
        "Manufacturers frequently release track-only editions to chase record-setting lap times.",
    ],
    "ev-hypercars": [
        "All-electric hypercars are achieving sub-two-second 0-60 mph times using quad-motor setups.",
        "Battery thermal management is critical to sustaining peak power output on long straights.",
        "Regenerative braking systems recover energy while still delivering track-level stopping power.",
        "Solid-state battery development could unlock even higher power density for future EV hypercars.",
    ],
    "design-and-engineering": [
        "Wind tunnel testing shapes body panels to minimize drag while maximizing downforce.",
        "Active suspension systems adjust ride height and damping based on driving mode.",
        "Lightweight forged wheels reduce unsprung mass for sharper cornering response.",
        "Butterfly and scissor doors remain signature design elements for flagship supercar models.",
    ],
    "collector-market": [
        "Auction prices for limited-edition supercars have climbed as collectors chase rarity.",
        "Low-mileage examples with full service history command significant price premiums.",
        "Some hypercar allocations are resold at multiples of their original list price.",
        "Provenance and ownership history heavily influence resale value at major auctions.",
    ],
}


def generate_document(doc_id: int) -> str:
    topic = random.choice(list(TOPICS.keys()))
    sentences = TOPICS[topic]
    title = f"{topic.replace('-', ' ').title()} Report {doc_id}"

    paragraphs = []
    for _ in range(random.randint(3, 5)):
        picked = random.sample(sentences, k=min(2, len(sentences)))
        filler = fake.paragraph(nb_sentences=3)
        paragraphs.append(" ".join(picked) + " " + filler)

    author = fake.name()
    date = fake.date_this_year()

    body = "\n\n".join(paragraphs)
    return f"{title}\nAuthor: {author}\nDate: {date}\nTopic: {topic}\n\n{body}\n"


def main():
    config.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    for i in range(1, config.NUM_FAKE_DOCUMENTS + 1):
        content = generate_document(i)
        path = config.DOCUMENTS_DIR / f"doc_{i:03d}.txt"
        path.write_text(content, encoding="utf-8")
    print(f"Generated {config.NUM_FAKE_DOCUMENTS} documents in {config.DOCUMENTS_DIR}")


if __name__ == "__main__":
    main()
