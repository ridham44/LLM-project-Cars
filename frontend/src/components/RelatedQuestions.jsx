import { DEFAULT_RELATED_QUESTIONS } from "../constants";

export function RelatedQuestions({ onSelect }) {
  return (
    <div className="related-questions" aria-label="Related questions">
      <span className="related-questions__label">Related Questions</span>
      <div className="related-questions__list">
        {DEFAULT_RELATED_QUESTIONS.map((question) => (
          <button key={question} type="button" className="related-question-chip" onClick={() => onSelect(question)}>
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
