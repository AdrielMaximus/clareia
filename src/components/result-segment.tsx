import { useId, useState, type KeyboardEvent } from 'react';
import { Info } from 'lucide-react';

export type ResultSegment = {
  indice: number;
  original: string;
  simplificado: string;
  explicacao: string;
  contexto?: string;
  ressalvas?: string[];
};

export function ResultSegmentCard({ segment }: { segment: ResultSegment }) {
  const originalId = useId();
  const contextId = useId();
  const [contextOpen, setContextOpen] = useState(false);
  const explanationId = useId();
  const [originalOpen, setOriginalOpen] = useState(false);
  const [explanationOpen, setExplanationOpen] = useState(false);

  const closePopoversOnEscape = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Escape') return;
    setOriginalOpen(false);
    setExplanationOpen(false);
    setContextOpen(false);
  };
  const lostCaveats = Array.isArray(segment.ressalvas) ? segment.ressalvas : [];
  const hasLostCaveats = lostCaveats.length > 0;
  const anyOpen = originalOpen || explanationOpen || contextOpen;
  return (
    <article
      className={`paragraph-card segment-card${hasLostCaveats ? ' segment-card--caveat' : ''}${anyOpen ? ' segment-card--open' : ''}`}
      data-testid={`card-result-paragraph-${segment.indice - 1}`}
      onKeyDown={closePopoversOnEscape}
    >
      <span className="paragraph-index" aria-hidden="true">
        {String(segment.indice).padStart(2, '0')}
      </span>

      <div className="segment-content">
        <div className="segment-original-trigger-wrap">
          <button
            type="button"
            className="segment-text-trigger"
            aria-expanded={originalOpen}
            aria-controls={originalId}
            onClick={() => {
              setOriginalOpen((open) => !open);
              setExplanationOpen(false);
              setContextOpen(false);
            }}
            onBlur={() => setOriginalOpen(false)}
          >
            {segment.simplificado}
          </button>

          <div
            id={originalId}
            className="segment-popover"
            role="tooltip"
            hidden={!originalOpen}
          >
            <span className="segment-popover-title">Trecho original</span>
            <p>{segment.original}</p>
            {hasLostCaveats && (
              <p className="segment-caveat">
                Possível alteração de sentido: {lostCaveats.join(', ')}
              </p>
            )}
          </div>
        </div>
        {hasLostCaveats && (
          <p className="segment-caveat" data-testid={`caveat-warning-${segment.indice}`}>
            Possível alteração de sentido: {lostCaveats.join(', ')}
          </p>
        )}

        <div className="segment-actions">
          <button
            type="button"
            className="segment-explanation-trigger"
            aria-label="Gerado por IA, confira com o original"
            aria-expanded={explanationOpen}
            aria-controls={explanationId}
            onClick={() => {
              setExplanationOpen((open) => !open);
              setOriginalOpen(false);
            }}
          >
            <Info size={14} aria-hidden="true" />
            <span>Gerado por IA, confira com o original</span>
          </button>

          <div
            id={explanationId}
            className="segment-popover segment-explanation-popover"
            role="tooltip"
            hidden={!explanationOpen}
          >
            <span className="segment-popover-title">Por que este trecho mudou</span>
            <p>{segment.explicacao}</p>
          </div>

          {segment.contexto ? (
            <>
              <button
                type="button"
                className="segment-explanation-trigger"
                aria-expanded={contextOpen}
                aria-controls={contextId}
                onClick={() => {
                  setContextOpen((open) => !open);
                  setExplanationOpen(false);
                  setOriginalOpen(false);
                }}
              >
                <Info size={14} aria-hidden="true" />
                <span>Contexto (gerado por IA)</span>
              </button>
              <div
                id={contextId}
                className="segment-popover"
                role="tooltip"
                hidden={!contextOpen}
              >
                <span className="segment-popover-title">Contexto</span>
                <p>{segment.contexto}</p>
                <p>Gerado por IA. Confira em uma fonte confiável.</p>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </article>
  );
}