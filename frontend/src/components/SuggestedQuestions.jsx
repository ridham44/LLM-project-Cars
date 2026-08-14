import { SUGGESTED_QUESTIONS } from "../constants";

export function SuggestedQuestions({ onSelect }) {
  return (
    <section className="suggested-questions" aria-label="Suggested questions">
      <h2>Start With a Question</h2>
      <div className="suggested-questions__grid">
        {SUGGESTED_QUESTIONS.map((item) => (
          <button key={item.question} type="button" className="question-card" onClick={() => onSelect(item.question)}>
            <span className="question-card__question">{item.question}</span>
            <span className="muted question-card__description">{item.description}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
