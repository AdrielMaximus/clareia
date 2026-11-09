import { useEffect, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import {
  ResultSegmentCard,
  type ResultSegment,
} from '@/components/result-segment';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  Copy,
  FileText,
  Feather,
  Info,
  LoaderCircle,
  RotateCcw,
  Sparkles,
  Sun,
  Moon,
  Coffee,
} from 'lucide-react';
import {
  Route,
  Switch,
  useLocation,
  Router as WouterRouter,
} from 'wouter';

const queryClient = new QueryClient();

const sampleOriginal = `apague este texto e comece a escrever.`;
const LEVEL_STORAGE_KEY = 'clareia-simplification-level';
const TERMS_STORAGE_KEY = 'clareia-term-strategy';
const levelValues = ['leve', 'media', 'forte'] as const;
const termValues = ['manter', 'explicar'] as const;

type SimplificationLevel = (typeof levelValues)[number];
type TermStrategy = (typeof termValues)[number];

function isResultSegment(value: unknown): value is ResultSegment {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.indice === 'number' &&
    Number.isInteger(candidate.indice) &&
    typeof candidate.original === 'string' &&
    typeof candidate.simplificado === 'string' &&
    typeof candidate.explicacao === 'string'
  );
}

function isResultSegmentList(value: unknown): value is ResultSegment[] {
  return Array.isArray(value) && value.every(isResultSegment);
}

function readStoredChoice<T extends string>(
  key: string,
  choices: readonly T[],
  fallback: T,
): T {
  const stored = window.localStorage.getItem(key);
  return stored && choices.includes(stored as T) ? (stored as T) : fallback;
}

const levelOptions: {
  value: SimplificationLevel;
  label: string;
  description: string;
}[] = [
  { value: 'leve', label: 'Leve', description: 'Mudanças discretas.' },
  { value: 'media', label: 'Média', description: 'Equilíbrio entre clareza e fidelidade.' },
  { value: 'forte', label: 'Forte', description: 'Simplificação mais intensa.' },
];

const termOptions: {
  value: TermStrategy;
  label: string;
  description: string;
}[] = [
  { value: 'manter', label: 'Manter', description: 'Preserva os termos técnicos.' },
  { value: 'explicar', label: 'Explicar', description: 'Mantém e explica os termos.' },
];

const loadingMessages = [
  'Lendo o texto com atenção',
  'Organizando as ideias em partes menores',
  'Preparando uma versão mais clara',
];

function Home() {
  const [theme, setTheme] = useState<'light' | 'dark' | 'sepia'>(() => {
    const saved = window.localStorage.getItem('clareia-theme');
    return saved === 'dark' || saved === 'sepia' ? saved : 'light';
  });
  const [level, setLevel] = useState<SimplificationLevel>(() =>
    readStoredChoice(LEVEL_STORAGE_KEY, levelValues, 'media'),
  );
  const [terms, setTerms] = useState<TermStrategy>(() =>
    readStoredChoice(TERMS_STORAGE_KEY, termValues, 'explicar'),
  );
  const [step, setStep] = useState<'input' | 'loading' | 'result'>('input');
  const [text, setText] = useState(sampleOriginal);
  const [simplifiedText, setSimplifiedText] = useState('');
  const [resultSegments, setResultSegments] = useState<ResultSegment[]>([]);
  const [inputError, setInputError] = useState('');
  const [copied, setCopied] = useState(false);
  const [loadingPhase, setLoadingPhase] = useState(0);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('clareia-theme', theme);
  }, [theme]);

  useEffect(() => {
    window.localStorage.setItem(LEVEL_STORAGE_KEY, level);
  }, [level]);

  useEffect(() => {
    window.localStorage.setItem(TERMS_STORAGE_KEY, terms);
  }, [terms]);

  useEffect(() => {
    if (step !== 'loading') return;

    const phaseTimers = [700, 1400, 2100].map((delay, index) =>
      window.setTimeout(() => setLoadingPhase(index + 1), delay),
    );

    return () => {
      phaseTimers.forEach(window.clearTimeout);
    };
  }, [step]);

  const openResult = () => setStep('result');
  const openInput = () => setStep('input');
  const isLoading = step === 'loading';
  const simplifyText = async () => {
    if (!text.trim()) {
      setInputError('Digite ou cole um texto para simplificar.');
      return;
    }

    setInputError('');
    setSimplifiedText('');
    setResultSegments([]);
    setCopied(false);
    setLoadingPhase(0);
    setStep('loading');

    try {
      const apiBase = import.meta.env.BASE_URL.replace(/\/?$/, '/');
      const response = await fetch(`${apiBase}api/simplify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, level, terms }),
      });
      const payload: unknown = await response.json().catch(() => null);

      if (!response.ok) {
        const message =
          payload &&
          typeof payload === 'object' &&
          'error' in payload &&
          typeof payload.error === 'string'
            ? payload.error
            : 'Não foi possível simplificar o texto agora. Tente novamente.';
        throw new Error(message);
      }

      if (
        !payload ||
        typeof payload !== 'object' ||
        !('simplified' in payload) ||
        typeof payload.simplified !== 'string' ||
        !payload.simplified.trim()
      ) {
        throw new Error('Não foi possível gerar uma versão simplificada desse texto.');
      }

      const segments =
        'segments' in payload && isResultSegmentList(payload.segments)
          ? payload.segments
          : [];
      setSimplifiedText(payload.simplified.trim());
      setResultSegments(segments);
      setStep('result');
    } catch (error) {
      setInputError(
        error instanceof Error
          ? error.message
          : 'Não foi possível conectar à Clareia. Verifique sua conexão e tente novamente.',
      );
      setStep('input');
    }
  };

  const copyResult = async () => {
    try {
      await navigator.clipboard.writeText(simplifiedText);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="app-shell">
      <div className="content-wrap mx-auto flex min-h-[100dvh] w-full max-w-6xl flex-col px-5 pb-8 sm:px-8 lg:px-12">
        <header className="flex items-center justify-between py-6 sm:py-8">
          <div className="brand-mark" aria-label="Clareia">
            <svg className="brand-symbol" viewBox="0 0 40 40" fill="none" aria-hidden="true">
              <path d="M30.2 10.7a13 13 0 1 0 .2 18.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
              <path d="M20 27V13m0 7 7-7m-7 7-7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="30.5" cy="10.2" r="2.3" fill="hsl(var(--accent))" />
            </svg>
            <span className="brand-word">clareia</span>
          </div>
          <div className="theme-picker" role="group" aria-label="Tema de aparência">
            <button type="button" className="theme-option" aria-label="Tema claro" aria-pressed={theme === 'light'} onClick={() => setTheme('light')} data-testid="button-theme-light"><Sun size={16} aria-hidden="true" /><span className="theme-label">Claro</span></button>
            <button type="button" className="theme-option" aria-label="Tema escuro" aria-pressed={theme === 'dark'} onClick={() => setTheme('dark')} data-testid="button-theme-dark"><Moon size={16} aria-hidden="true" /><span className="theme-label">Escuro</span></button>
            <button type="button" className="theme-option" aria-label="Tema sépia" aria-pressed={theme === 'sepia'} onClick={() => setTheme('sepia')} data-testid="button-theme-sepia"><Coffee size={16} aria-hidden="true" /><span className="theme-label">Sépia</span></button>
          </div>
        </header>

        <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col pb-8 pt-8 sm:pt-14">
          <section className="reveal mb-9 max-w-2xl">
            <div className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary">
              <Feather size={15} strokeWidth={1.8} aria-hidden="true" />
              <span>Leitura com mais leveza</span>
            </div>
            <h1 className="font-display text-[2.65rem] leading-[1.06] tracking-[-0.045em] text-foreground sm:text-5xl">
              Simplifique e interprete textos com mais clareza.
            </h1>
            <p className="mt-5 max-w-xl text-[1.02rem] leading-7 text-muted-foreground sm:text-lg">
              Cole um trecho e siga no seu ritmo. Sem pressa, sem julgamento.
            </p>
          </section>

          <nav
            className="stepper reveal mb-5 flex w-full rounded-2xl p-1"
            aria-label="Etapas da leitura"
            style={{ animationDelay: '80ms' }}
            aria-busy={step === 'loading'}
          >
            <button
              type="button"
              className="step flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-3 text-sm font-semibold sm:justify-start sm:px-5"
              data-active={step === 'input'}
              aria-current={step === 'input' ? 'step' : undefined}
              onClick={openInput}
              disabled={step === 'loading'}
              data-testid="button-step-input"
            >
              <span>Inserir texto</span>
            </button>
            <button
              type="button"
              className="step flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-3 text-sm font-semibold text-muted-foreground sm:justify-start sm:px-5"
              data-active={step === 'result'}
              aria-current={step === 'result' ? 'step' : undefined}
              onClick={openResult}
              disabled={step === 'loading'}
              data-testid="button-step-result"
            >
              <span>Resultado</span>
            </button>
          </nav>

          {step === 'loading' ? (
            <section
              className="workspace-card reveal flex min-h-[440px] flex-col items-center justify-center rounded-[1.35rem] px-5 py-12 text-center sm:px-8"
              style={{ animationDelay: '140ms' }}
              aria-labelledby="loading-title"
              aria-live="polite"
              role="status"
              data-testid="loading-state"
            >
              <div className="loading-icon mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary">
                <LoaderCircle size={30} strokeWidth={1.7} className="animate-spin" aria-hidden="true" />
              </div>
              <p className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-primary">
                Clareia está trabalhando
              </p>
              <h2 id="loading-title" className="font-display text-3xl tracking-[-0.035em]">
                Só um instante…
              </h2>
              <p className="mt-3 max-w-md text-sm leading-6 text-muted-foreground">
                Estamos organizando as ideias para deixar o texto mais fácil de acompanhar.
              </p>

              <div
                className="loading-progress-track mt-8 w-full max-w-sm overflow-hidden rounded-full"
                role="progressbar"
                aria-label="Progresso da preparação do texto"
                aria-valuemin={0}
                aria-valuemax={3}
                aria-valuenow={loadingPhase}
              >
                <span
                  className="loading-progress-fill block h-full rounded-full"
                  style={{ width: `${Math.round((loadingPhase / 3) * 100)}%` }}
                />
              </div>

              <ul className="loading-stages mt-7 flex w-full max-w-sm flex-col gap-3 text-left">
                {loadingMessages.map((message, index) => {
                  const complete = loadingPhase > index;
                  const current = loadingPhase === index;
                  return (
                    <li
                      key={message}
                      className="loading-stage flex items-center gap-3 text-sm"
                      data-state={complete ? 'complete' : current ? 'current' : 'waiting'}
                    >
                      <span className="loading-stage-marker flex h-6 w-6 shrink-0 items-center justify-center rounded-full" aria-hidden="true">
                        {complete ? <Check size={13} strokeWidth={2.5} /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
                      </span>
                      <span>{message}</span>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : step === 'input' ? (
            <section
              className="workspace-card reveal rounded-[1.35rem] p-5 sm:p-8"
              style={{ animationDelay: '140ms' }}
              aria-labelledby="input-title"
            >
              <div className="mb-7 flex items-start justify-between gap-4">
                <div>
                  <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-[hsl(171_44%_35%_/_0.10)] text-primary">
                    <FileText size={19} strokeWidth={1.8} aria-hidden="true" />
                  </div>
                  <h2 id="input-title" className="font-display text-2xl tracking-[-0.025em] sm:text-[1.75rem]">
                    O que você quer entender?
                  </h2>
                  <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
                    Protótipo de prova de conceito, ainda não avaliado com usuários.
                    Não substitui acompanhamento clínico ou pedagógico.
                  </p>
                </div>
              </div>

              <div className="editor-panel rounded-2xl p-4 sm:p-5">
                <label htmlFor="source-text" className="sr-only">
                  Texto para clarear
                </label>
                <textarea
                  id="source-text"
                  className="editor-textarea w-full border-0 p-0 text-[1rem] leading-7 outline-none placeholder:leading-7 sm:text-[1.04rem]"
                  placeholder="Não insira dados pessoais, sensíveis ou sigilosos. O texto será enviado à API do Gemini."
                  value={text}
                  onChange={(event) => {
                    setText(event.target.value);
                    setInputError('');
                    setSimplifiedText('');
                    setResultSegments([]);
                  }}
                  maxLength={5000}
                  data-testid="textarea-source-text"
                  aria-describedby="text-counter text-hint"
                />
                <div className="mt-4 flex items-center justify-between gap-4 border-t border-border/70 pt-3 text-xs text-muted-foreground">
                  <span id="text-hint" className="flex items-center gap-1.5">
                    <Info size={14} aria-hidden="true" />
                    Não inclua dados pessoais, sensíveis ou sigilosos; o texto será enviado à API do Gemini.
                  </span>
                  <span id="text-counter" className="shrink-0 tabular-nums" data-testid="text-character-count">
                    {text.length.toLocaleString('pt-BR')} / 5.000
                  </span>
                </div>
              </div>

              <div className="option-groups">
                <fieldset className="option-group" aria-describedby="level-hint">
                  <legend className="option-legend">Nível de simplificação</legend>
                  <p id="level-hint" className="option-hint">
                    Escolha quanto o texto deve mudar.
                  </p>
                  <div className="option-list">
                    {levelOptions.map((option) => (
                      <label className="option-card" key={option.value}>
                        <input
                          type="radio"
                          name="level"
                          value={option.value}
                          checked={level === option.value}
                          onChange={() => setLevel(option.value)}
                          data-testid={`radio-level-${option.value}`}
                        />
                        <span className="option-card-copy">
                          <span className="option-card-title">{option.label}</span>
                          <span className="option-card-description">{option.description}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </fieldset>

                <fieldset className="option-group" aria-describedby="terms-hint">
                  <legend className="option-legend">Termos técnicos</legend>
                  <p id="terms-hint" className="option-hint">
                    Escolha como lidar com palavras específicas.
                  </p>
                  <div className="option-list">
                    {termOptions.map((option) => (
                      <label className="option-card" key={option.value}>
                        <input
                          type="radio"
                          name="terms"
                          value={option.value}
                          checked={terms === option.value}
                          onChange={() => setTerms(option.value)}
                          data-testid={`radio-terms-${option.value}`}
                        />
                        <span className="option-card-copy">
                          <span className="option-card-title">{option.label}</span>
                          <span className="option-card-description">{option.description}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              </div>

              {inputError && (
                <div
                  className="mt-4 rounded-xl border border-[hsl(13_50%_58%_/_0.35)] bg-[hsl(13_50%_58%_/_0.08)] px-4 py-3 text-sm leading-6 text-foreground"
                  role="alert"
                  data-testid="text-api-error"
                >
                  {inputError}
                </div>
              )}

              <div className="mt-8 flex flex-col items-stretch justify-between gap-4 border-t border-border/70 pt-6 sm:flex-row sm:items-center">
                <button
                  type="button"
                  className="primary-button inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-bold text-primary-foreground"
                  onClick={simplifyText}
                  disabled={!text.trim() || isLoading}
                  data-testid="button-simplify"
                >
                  Simplificar texto
                  <ArrowRight size={17} aria-hidden="true" />
                </button>
              </div>
            </section>
          ) : (
            <section
              className="workspace-card reveal rounded-[1.35rem] p-5 sm:p-8"
              style={{ animationDelay: '140ms' }}
              aria-labelledby="result-title"
            >
              <div className="mb-7 flex items-start justify-between gap-4">
                <div>
                  <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-[hsl(13_50%_58%_/_0.13)] text-accent">
                    <BookOpen size={19} strokeWidth={1.8} aria-hidden="true" />
                  </div>
                  <h2 id="result-title" className="font-display text-2xl tracking-[-0.025em] sm:text-[1.75rem]">
                    Resultado
                  </h2>
                  <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
                    {simplifiedText
                      ? 'O mesmo conteúdo, em parágrafos mais curtos. Clique em um trecho para ver o original.'
                      : 'A versão mais fácil de acompanhar vai aparecer aqui.'}
                  </p>
                </div>
              </div>

              {simplifiedText ? (
                <div
                  className="result-copy rounded-2xl px-5 py-6 sm:px-7 sm:py-8"
                  data-testid="text-simplified-result"
                >
                  {resultSegments.length > 0
                    ? resultSegments.map((segment) => (
                        <ResultSegmentCard
                          key={segment.indice}
                          segment={segment}
                        />
                      ))
                    : simplifiedText
                        .split(/\n\s*\n/)
                        .map((paragraph) => paragraph.trim())
                        .filter(Boolean)
                        .map((paragraph, index) => (
                          <article
                            key={index}
                            className="paragraph-card"
                            data-testid={`card-result-paragraph-${index}`}
                          >
                            <span className="paragraph-index" aria-hidden="true">
                              {String(index + 1).padStart(2, '0')}
                            </span>
                            <p>{paragraph}</p>
                          </article>
                        ))}
                </div>
              ) : (
                <div className="result-empty flex min-h-[320px] flex-col items-center justify-center rounded-2xl px-6 py-12 text-center">
                  <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-full border border-primary/20 bg-primary/10 text-primary">
                    <Sparkles size={24} strokeWidth={1.6} aria-hidden="true" />
                  </div>
                  <h3 className="font-display text-2xl tracking-[-0.025em]" data-testid="text-result-empty-title">
                    Seu texto vai aparecer aqui
                  </h3>
                  <p className="mt-3 max-w-sm text-sm leading-6 text-muted-foreground" data-testid="text-result-empty-description">
                    Volte para inserir o texto e selecionar “Simplificar texto”.
                  </p>
                  <div className="mt-7 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-primary/75">
                    <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
                    Clareza no seu tempo
                  </div>
                </div>
              )}

              <div className="mt-6 flex flex-col justify-between gap-4 border-t border-border/70 pt-6 sm:flex-row sm:items-center">
                <p className="text-xs leading-5 text-muted-foreground">
                  O que fazer agora?
                </p>
                <div className="flex flex-col gap-3 sm:flex-row">
                  {simplifiedText && (
                    <button
                      type="button"
                      onClick={copyResult}
                      className="inline-flex items-center justify-center gap-2 self-start rounded-xl border border-border bg-background/50 px-4 py-2.5 text-sm font-bold text-foreground transition-colors hover:bg-secondary sm:self-auto"
                      data-testid="button-copy-result"
                    >
                      {copied ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
                      {copied ? 'Copiado' : 'Copiar resultado'}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={openInput}
                    className="inline-flex items-center justify-center gap-2 self-start rounded-xl border border-border bg-background/50 px-4 py-2.5 text-sm font-bold text-foreground transition-colors hover:bg-secondary sm:self-auto"
                    data-testid="button-back-to-input"
                  >
                    <ArrowLeft size={16} aria-hidden="true" />
                    Voltar ao texto
                  </button>
                </div>
              </div>
            </section>
          )}

          <aside className="reveal mt-6 flex items-start gap-3 rounded-2xl border border-border/70 bg-card/45 px-4 py-4 sm:px-5" style={{ animationDelay: '210ms' }}>
            <div className="mt-0.5 rounded-lg bg-accent/10 p-2 text-accent">
              <RotateCcw size={15} aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-sm font-semibold">Uma coisa de cada vez.</h2>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Você não precisa entender tudo de uma vez. A Clareia existe para
                abrir uma porta, não para correr por você.
              </p>
            </div>
          </aside>
        </main>

        <footer className="flex flex-col gap-2 border-t border-border/60 py-5 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>Clareia — leitura sem peso extra.</span>
          <span className="flex items-center gap-2">
            Feito para dias que pedem um pouco mais de espaço.
          </span>
        </footer>
      </div>
    </div>
  );
}

function Router() {
  return (
    // Keep a shared shell (sidebar, navbar) outside the boundary so it
    // survives a page crash.
    <RoutedErrorBoundary>
      <Switch>
        <Route path="/" component={Home} />
        <Route component={NotFound} />
      </Switch>
    </RoutedErrorBoundary>
  );
}

function RoutedErrorBoundary({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
