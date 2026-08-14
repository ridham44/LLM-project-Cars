// EXAMPLE / DEMO DATA ONLY.
//
// The real backend (Groups B-E of IMPLEMENTATION_PLAN.md) is not built yet, so
// there is nothing live to query. This fixture exists purely so every UI state
// in this workspace can be inspected and QA'd before the backend exists. It is
// never shown unless the user explicitly clicks "View example report" in the
// empty state, and the UI always labels it with an EXAMPLE DATA badge -- it is
// never used as a silent fallback for a real, failed request.
export const EXAMPLE_REPORT = {
  id: "example-chiron-vs-jesko",
  isExample: true,
  question: "Compare the engineering philosophy of Bugatti Chiron and Koenigsegg Jesko.",
  status: "completed",
  routing: {
    intent: ["COMPARE"],
    complexity: "HIGH",
    modelsUsed: [
      { role: "heavy_researcher", model: "qwen2.5:3b", ran: true },
      { role: "analyst", model: "deepseek-r1:1.5b", ran: true },
      { role: "critic", model: "gemma3:4b", ran: true },
      { role: "judge", model: "qwen2.5:1.5b", ran: true },
    ],
    explanation: "Classified as COMPARE (HIGH complexity) - routed to heavy_researcher, analyst, critic, judge for independent cross-checking and verification.",
    evidenceCount: 8,
    confidence: 0.89,
    confidenceLabel: "High",
    escalated: false,
  },
  startedAt: "2026-08-12T14:02:00Z",
  completedAt: "2026-08-12T14:02:18Z",
  summary:
    "Bugatti and Koenigsegg pursue different hypercar philosophies. The Chiron prioritizes " +
    "refined, high-mass grand-touring performance built around a quad-turbo W16 and a " +
    "dual-clutch transmission, while the Jesko is a lighter, more track-oriented platform " +
    "built around a twin-turbo V8 and a purpose-built multi-clutch gearbox. Both exceed " +
    "1,500 horsepower, but they reach it through markedly different engineering trade-offs " +
    "around weight, cylinder count, and transmission design.",
  findings: [
    {
      id: "f1",
      text: "Koenigsegg's V8 architecture prioritizes a lower engine mass and higher redline over the Chiron's larger-displacement W16.",
      evidenceCount: 3,
      confidence: 0.94,
    },
    {
      id: "f2",
      text: "Bugatti's dual-clutch transmission favors seamless power delivery for grand-touring use, while Koenigsegg's Light Speed Transmission targets rapid gear changes for track use.",
      evidenceCount: 4,
      confidence: 0.91,
    },
    {
      id: "f3",
      text: "Top speed figures differ across sources depending on whether the value is manufacturer-claimed or independently measured.",
      evidenceCount: 2,
      confidence: 0.68,
    },
  ],
  comparison: {
    entities: ["Bugatti Chiron", "Koenigsegg Jesko"],
    rows: [
      { category: "Engine", values: ["8.0L quad-turbo W16", "5.0L twin-turbo V8"], evidenceIds: ["e1", "e2"] },
      { category: "Power", values: ["1,500 hp", "1,600 hp (E85)"], evidenceIds: ["e2", "e3"] },
      { category: "Torque", values: ["1,600 Nm", "1,500 Nm"], evidenceIds: ["e1", "e3"] },
      { category: "Transmission", values: ["7-speed dual-clutch", "9-speed Light Speed Transmission"], evidenceIds: ["e4", "e5"] },
      { category: "Weight", values: ["~1,995 kg", "~1,420 kg"], evidenceIds: ["e6"] },
      { category: "Top Speed", values: ["~490 km/h (claimed)", "~482 km/h (claimed) / independently unverified"], evidenceIds: ["e7", "e8"] },
    ],
  },
  evidence: [
    {
      id: "e1",
      sourceType: "official",
      documentTitle: "Chiron Technical Information",
      manufacturer: "Bugatti",
      page: 14,
      excerpt: "The Chiron is powered by an 8.0-litre quad-turbocharged W16 engine producing 1,500 PS and 1,600 Nm of torque.",
      score: 0.94,
      url: null,
    },
    {
      id: "e2",
      sourceType: "official",
      documentTitle: "Jesko Technical Information",
      manufacturer: "Koenigsegg",
      page: 6,
      excerpt: "The Jesko's twin-turbo 5.0-litre V8 delivers up to 1,600 hp on E85 fuel, with a dry weight of approximately 1,420 kg.",
      score: 0.92,
      url: null,
    },
    {
      id: "e3",
      sourceType: "official",
      documentTitle: "Jesko Powertrain Overview",
      manufacturer: "Koenigsegg",
      page: 3,
      excerpt: "Peak torque of 1,500 Nm is available from 5,100 rpm on E85.",
      score: 0.9,
      url: null,
    },
    {
      id: "e4",
      sourceType: "official",
      documentTitle: "Chiron Technical Information",
      manufacturer: "Bugatti",
      page: 16,
      excerpt: "Power is transmitted via a 7-speed dual-clutch gearbox developed specifically for the Chiron.",
      score: 0.88,
      url: null,
    },
    {
      id: "e5",
      sourceType: "official",
      documentTitle: "Jesko Transmission Overview",
      manufacturer: "Koenigsegg",
      page: 4,
      excerpt: "The Light Speed Transmission (LST) is a 9-speed multi-clutch system designed for near-instant gear changes.",
      score: 0.9,
      url: null,
    },
    {
      id: "e6",
      sourceType: "official",
      documentTitle: "Jesko Technical Information",
      manufacturer: "Koenigsegg",
      page: 2,
      excerpt: "Dry weight is approximately 1,420 kg, roughly 575 kg lighter than comparable quad-turbo W16 hypercars.",
      score: 0.85,
      url: null,
    },
    {
      id: "e7",
      sourceType: "official",
      documentTitle: "Chiron Super Sport 300+ Press Release",
      manufacturer: "Bugatti",
      page: 1,
      excerpt: "A specially prepared Chiron prototype reached 490.484 km/h under closed-course conditions.",
      score: 0.81,
      url: null,
    },
    {
      id: "e8",
      sourceType: "media",
      documentTitle: "Independent Top Speed Test Coverage",
      manufacturer: "Koenigsegg",
      page: null,
      excerpt: "Koenigsegg's claimed 482 km/h top speed for the Jesko Absolut has not been independently verified on a public test track.",
      score: 0.62,
      url: null,
    },
  ],
  claims: [
    {
      id: "c1",
      text: "Bugatti Chiron produces 1,500 PS from an 8.0-litre quad-turbo W16.",
      status: "supported",
      supportingSources: 1,
      confidence: 0.94,
      evidenceIds: ["e1"],
    },
    {
      id: "c2",
      text: "Koenigsegg Jesko produces up to 1,600 hp on E85 fuel.",
      status: "supported",
      supportingSources: 1,
      confidence: 0.92,
      evidenceIds: ["e2"],
    },
    {
      id: "c3",
      text: "The Jesko is roughly 575 kg lighter than the Chiron.",
      status: "partially_supported",
      supportingSources: 1,
      confidence: 0.71,
      evidenceIds: ["e6"],
    },
    {
      id: "c4",
      text: "The Koenigsegg Jesko has a higher top speed than the Bugatti Chiron.",
      status: "contradicted",
      supportingSources: 2,
      confidence: 0.45,
      evidenceIds: ["e7", "e8"],
    },
    {
      id: "c5",
      text: "The Jesko's Light Speed Transmission uses 9 gears.",
      status: "supported",
      supportingSources: 1,
      confidence: 0.9,
      evidenceIds: ["e5"],
    },
  ],
  contradictions: [
    {
      id: "x1",
      topic: "Top speed",
      sourceA: { name: "Bugatti Chiron Super Sport 300+ Press Release", value: "490.484 km/h" },
      sourceB: { name: "Independent Top Speed Test Coverage (Jesko)", value: "482 km/h claimed, unverified" },
      explanation:
        "The discrepancy is not a direct conflict between two figures for the same car, but a difference in " +
        "evidence quality: the Chiron figure comes from a manufacturer-run closed-course record attempt, while " +
        "the Jesko figure is a manufacturer claim that has not been independently tested. Treat the two numbers " +
        "as measured under different conditions rather than as contradicting the same claim.",
    },
  ],
  sources: [
    { id: "s1", manufacturer: "Bugatti", title: "Chiron Technical Information", type: "official", date: "2024-01-01", page: 14, url: null },
    { id: "s2", manufacturer: "Koenigsegg", title: "Jesko Technical Information", type: "official", date: "2024-06-01", page: 6, url: null },
    { id: "s3", manufacturer: "Bugatti", title: "Chiron Super Sport 300+ Press Release", type: "official", date: "2019-09-02", page: 1, url: null },
    { id: "s4", manufacturer: "Koenigsegg", title: "Independent Top Speed Test Coverage", type: "media", date: "2025-03-11", page: null, url: null },
  ],
  metrics: {
    documentsSearched: 184,
    documentsSelected: 37,
    evidenceChunks: 61,
    claimsExtracted: 23,
    claimsVerified: 20,
    contradictionsCount: 2,
    confidence: 0.89,
    confidenceLabel: "High",
    executionTimeSeconds: 18.4,
    sourceAgreement: 0.92,
    evidenceCoverage: 0.87,
    modelAgreement: { agreed: 3, total: 3 },
  },
  trace: [
    { step: "Query Understanding", status: "done", timestamp: "00:01" },
    { step: "Research Planning", status: "done", timestamp: "00:02" },
    { step: "Document Retrieval", status: "done", timestamp: "00:03" },
    { step: "Hybrid Search", status: "done", timestamp: "00:05" },
    { step: "Evidence Ranking", status: "done", timestamp: "00:07" },
    { step: "Researcher Model", status: "done", timestamp: "00:11" },
    { step: "Critic Model", status: "done", timestamp: "00:14" },
    { step: "Claim Verification", status: "done", timestamp: "00:16" },
    { step: "Final Synthesis", status: "done", timestamp: "00:18" },
  ],
  error: null,
};

export const EXAMPLE_HISTORY = [
  { id: "example-chiron-vs-jesko", question: "Compare Chiron vs Jesko", mode: "compare", timestamp: "2026-08-12T14:02:00Z" },
  { id: "example-revuelto", question: "Lamborghini Revuelto hybrid technology", mode: "deep", timestamp: "2026-08-11T09:30:00Z" },
  { id: "example-w1", question: "McLaren W1 aerodynamics", mode: "standard", timestamp: "2026-08-11T08:10:00Z" },
];

export const EXAMPLE_PROMPTS = [
  "Compare Bugatti Chiron vs Koenigsegg Jesko",
  "Analyze Lamborghini Revuelto hybrid technology",
  "Explain McLaren W1 aerodynamics",
  "Compare Pagani Utopia and Bugatti Tourbillon",
];
